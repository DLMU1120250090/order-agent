import asyncio
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud import trip as trip_crud
from app.models.enums import BudgetTier, TransportMode
from app.models.schemas import (
    PlanDecision, PlanOption, TransportLeg, TravelSlotBundle, UserProfile,
)
from app.services.collector import DataCollectorService

log = logging.getLogger("travel.planner")

# 中转枢纽候选（真实查询两段车次/航班，按可达性自动过滤）
TRANSFER_HUBS = [
    "北京", "上海", "广州", "武汉", "郑州", "南京", "杭州", "西安",
    "成都", "长沙", "沈阳", "济南", "石家庄", "合肥", "南昌", "太原",
]


class ItineraryPlanner:
    """
    行程编排约束求解器（B2 定稿）。
    ① 查班次（collector）
    ② 枚举直连 + 常见中转组合
    ③ 硬过滤：衔接时间（缓冲 30min）/ 预算 > 1.5×(档位参考价)
    ④ 打分：0.4·price + 0.3·duration + 0.2·schedule + 0.1·preference
    ⑤ Top3 PlanOption 落库
    """

    TRANSFER_BUFFER_MIN = 30

    def __init__(self, collector: DataCollectorService):
        self.collector = collector

    async def plan(
        self,
        db: AsyncSession,
        user_id: int,
        slots: TravelSlotBundle,
        profile: Optional[UserProfile] = None,
    ) -> PlanDecision:
        origin = (slots.origin or [None])[0] or (profile.home_city if profile and profile.home_city else "北京")
        destination = (slots.destination or ["上海"])[0]
        trip_date = (slots.tripDate or [datetime.now().strftime("%Y-%m-%d")])[0]

        flights = await self.collector.search_flights(db, origin, destination, trip_date)
        trains = await self.collector.search_trains(db, origin, destination, trip_date)
        # 统一为"段列表"：直连 = 单段，中转 = 多段
        raw_legs: List[List[dict]] = [[f] for f in flights] + [[t] for t in trains]
        raw_legs += await self._transfers(db, origin, destination, trip_date)

        # 当日报价分布（全部候选方案总价），用于预算档位 P30/P70 动态映射
        candidate_totals = [round(sum(float(leg["price"]) for leg in raw), 2) for raw in raw_legs]
        ref_price = self._budget_reference(slots, candidate_totals)
        preferred_modes = self._preferred_modes(slots)
        early_bird = bool(profile and profile.preferences and profile.preferences.get("early_bird"))

        options: List[PlanOption] = []
        for raw, total in zip(raw_legs, candidate_totals):
            if ref_price and total > ref_price * 1.5:
                continue  # 硬过滤：预算超 1.5×

            legs = [TransportLeg(
                leg_no=i + 1,
                mode=leg["mode"],
                from_city=leg["from_city"],
                to_city=leg["to_city"],
                from_station=leg.get("from_station"),
                to_station=leg.get("to_station"),
                arrive_day=int(leg.get("arrive_day") or leg.get("day") or 1),
                depart=leg["depart"],
                arrive=leg["arrive"],
                price=float(leg["price"]),
                vehicle_no=leg.get("vehicle_no", ""),
                seat=leg.get("seat"),
                carrier=leg.get("carrier"),
            ) for i, leg in enumerate(raw)]

            duration_h = self._duration_h(legs)
            schedule = self._schedule_score(legs[0].depart, early_bird)
            pref = self._preference_score(legs, preferred_modes)
            options.append(PlanOption(
                legs=legs,
                total_price=total,
                total_duration_h=duration_h,
                meets_budget=total <= (ref_price * 1.5) if ref_price else True,
                score=0.0,
                budget_deviation=round(total - ref_price, 2) if ref_price else None,
            ))

        if not options:
            return PlanDecision(options=[], recommended=None, reason="没有满足约束的出行方案，请调整日期或预算。")

        # 打分
        prices = [o.total_price for o in options]
        durations = [o.total_duration_h for o in options]
        p_min, p_max = min(prices), max(prices)
        d_min, d_max = min(durations), max(durations)
        for o in options:
            price_score = 1.0 if p_max == p_min else (p_max - o.total_price) / (p_max - p_min)
            duration_score = 1.0 if d_max == d_min else (d_max - o.total_duration_h) / (d_max - d_min)
            schedule_score = self._schedule_score(o.legs[0].depart, early_bird)
            pref_score = self._preference_score(o.legs, preferred_modes)
            o.score = round(0.4 * price_score + 0.3 * duration_score + 0.2 * schedule_score + 0.1 * pref_score, 4)

        options.sort(key=lambda o: o.score, reverse=True)
        top = options[:3]

        # 落库 travel_plan
        trip = await trip_crud.create_or_get_trip(db, user_id, slots)
        for opt in top:
            opt.trip_id = trip.id
            opt.plan_id = str(await trip_crud.save_plan(db, trip.id, opt))

        reason = "已按价格(40%)、耗时(30%)、时刻(20%)、偏好(10%)综合排序，供你选择。"
        return PlanDecision(options=top, recommended=top[0], reason=reason)

    async def replan(
        self,
        db: AsyncSession,
        user_id: int,
        slots: TravelSlotBundle,
        exclude_plan_ids: List[str],
        profile: Optional[UserProfile] = None,
    ) -> PlanDecision:
        """PLAN_ADJUST 级联重排：排除历史已推荐方案（换一批）。"""
        decision = await self.plan(db, user_id, slots, profile)
        exclude = set(exclude_plan_ids or [])
        kept = [o for o in decision.options if o.plan_id not in exclude]
        if kept:
            return PlanDecision(options=kept, recommended=kept[0], reason="已排除上一批方案，重新生成。")
        return decision

    async def _transfers(self, db: AsyncSession, origin: str, destination: str, date: str) -> List[List[dict]]:
        """
        中转组合：火车/航班 → 枢纽 → 火车/航班 → 目的地（限 4 个枢纽，衔接缓冲校验）。
        每段查询使用独立 DB 会话，枢纽之间与段之间并行，控制整体耗时。
        """
        from app.database import async_session_maker

        hubs = [c for c in TRANSFER_HUBS if c not in (origin, destination)][:4]

        async def search_one(fn, a: str, b: str):
            async with async_session_maker() as session:
                return await fn(session, a, b, date)

        async def query_hub(hub: str):
            first_t = asyncio.create_task(search_one(self.collector.search_trains, origin, hub))
            first_f = asyncio.create_task(search_one(self.collector.search_flights, origin, hub))
            second_t = asyncio.create_task(search_one(self.collector.search_trains, hub, destination))
            second_f = asyncio.create_task(search_one(self.collector.search_flights, hub, destination))
            first_trains, first_flights, second_trains, second_flights = await asyncio.gather(
                first_t, first_f, second_t, second_f
            )
            return hub, first_trains + first_flights, second_trains + second_flights

        hub_results = await asyncio.gather(*(query_hub(h) for h in hubs))
        combos: List[List[dict]] = []
        seen = set()
        for _hub, first_legs, second_legs in hub_results:
            for f in first_legs[:3]:
                for s in second_legs[:3]:
                    if not self._gap_ok(
                        f["arrive"], s["depart"],
                        int(f.get("arrive_day") or 1), int(s.get("arrive_day") or 1),
                    ):
                        continue
                    key = (f.get("vehicle_no"), f.get("depart"), s.get("vehicle_no"), s.get("depart"))
                    if key in seen:
                        continue
                    seen.add(key)
                    combos.append([dict(f), dict(s)])
                    if len(combos) >= 40:
                        return combos
        return combos

    def _budget_reference(self, slots: TravelSlotBundle, prices: Optional[List[float]] = None) -> Optional[float]:
        if not slots.budget:
            return None
        label = slots.budget[0]
        tier = {"经济型": BudgetTier.economy, "舒适型": BudgetTier.comfort, "高端型": BudgetTier.premium}.get(label)
        if not tier:
            return None
        # 动态映射（B2 定稿）：经济型 ≤ 当日 P30、舒适型 ≤ P70、高端型 = 当日最高价；
        # 无报价时回退静态参考价（.env TRAVEL_BUDGET_REFERENCE）
        if prices:
            sorted_prices = sorted(float(p) for p in prices)
            if sorted_prices:
                def percentile(q: float) -> float:
                    idx = round(q * (len(sorted_prices) - 1))
                    return sorted_prices[idx]

                if tier is BudgetTier.economy:
                    return percentile(0.30)
                if tier is BudgetTier.comfort:
                    return percentile(0.70)
                return sorted_prices[-1]
        return settings.budget_tiers().get(tier.value)

    def _preferred_modes(self, slots: TravelSlotBundle) -> set:
        mapping = {"飞机": TransportMode.FLIGHT, "高铁": TransportMode.TRAIN, "火车": TransportMode.TRAIN, "大巴": TransportMode.BUS}
        return {mapping[m].value for m in slots.transportMode if m in mapping}

    def _preference_score(self, legs: List[TransportLeg], preferred: set) -> float:
        if not preferred:
            return 0.8
        hits = sum(1 for leg in legs if leg.mode in preferred)
        return hits / len(legs)

    def _schedule_score(self, depart: str, early_bird: bool) -> float:
        try:
            hour = int(depart.split(":")[0])
        except Exception:  # noqa: BLE001
            return 0.5
        if 9 <= hour <= 20:
            return 1.0
        if 5 <= hour < 9:
            return 0.8 if early_bird else 0.7
        return 0.5

    @staticmethod
    def _duration_h(legs: List[TransportLeg]) -> float:
        def to_min(t: str, day: int = 1) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m) + (day - 1) * 1440

        start = to_min(legs[0].depart, legs[0].arrive_day)
        end = to_min(legs[-1].arrive, legs[-1].arrive_day)
        if end < start:
            end += 24 * 60
        # 每段中转增加缓冲时间（Mock 固定 60 分钟通勤 + 30 分钟缓冲）
        buffer = (len(legs) - 1) * (60 + ItineraryPlanner.TRANSFER_BUFFER_MIN)
        return round((end - start + buffer) / 60.0, 1)

    @staticmethod
    def _gap_ok(arrive: str, depart: str, arrive_day: int = 1, depart_day: int = 1) -> bool:
        def to_min(t: str, day: int = 1) -> int:
            h, m = t.split(":")
            return int(h) * 60 + int(m) + (day - 1) * 1440

        gap = to_min(depart, depart_day) - to_min(arrive, arrive_day)
        if gap < 0:
            gap += 24 * 60
        return gap >= (60 + ItineraryPlanner.TRANSFER_BUFFER_MIN)

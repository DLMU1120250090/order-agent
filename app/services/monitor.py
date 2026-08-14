import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud import order as order_crud
from app.models.database import TravelOrderRow, TravelTripRow
from app.models.enums import ChangeScenario, OrderStatus, TaskType
from app.models.schemas import ChangeDecision, ChangeRequest, OutboundMessage
from app.services.change_decision import ChangeDecisionService
from app.services.collector import DataCollectorService
from app.services.push import PushService

log = logging.getLogger("travel.monitor")


class PriceMonitorService:
    """
    价格监控（两阶段，默认开启 + feature flag）：
    阶段1（下单确认前）：每 1 小时扫描 → 较首次查询明显下降(>5%) → 推送更低价
    阶段2（下单后出发前）：每 6 小时扫描出发日 ±2 天窗口 → ChangeDecisionService 计算净节省
      → 净节省 > 阈值(默认50元) 且新航班可行 → 推送"退票重买"方案
    """

    def __init__(
        self,
        collector: DataCollectorService,
        change_decision: ChangeDecisionService,
        push: PushService,
    ):
        self.collector = collector
        self.change_decision = change_decision
        self.push = push

    async def scan_phase1(self, db: AsyncSession, trip: TravelTripRow) -> Optional[dict]:
        """下单确认前：对比首次查询价（存于 trip 对应方案），下降 >5% 推送。"""
        if not trip.start_date:
            return None
        from app.crud import trip as trip_crud
        plans = await trip_crud.list_plans(db, trip.id)
        if not plans:
            return None
        plan = plans[0]
        base_price = float(plan.plan_json.get("total_price", 0))
        if base_price <= 0:
            return None
        raw = await self.collector.search_transport(db, "北京", trip.destination, trip.start_date)
        if not raw:
            return None
        current_min = min(float(r["price"]) for r in raw)
        if (base_price - current_min) / base_price > 0.05:
            await self.push.push(
                trip.user_id,
                OutboundMessage(
                    kind="TEXT",
                    text=f"📉 更低价出现：{trip.destination} 当前最低 ¥{current_min:.0f}（原方案 ¥{base_price:.0f}），下降超过 5%，是否按此下单？",
                ),
            )
            return {"trip_id": trip.id, "base_price": base_price, "current_min": current_min}
        return None

    async def scan_phase2(self, db: AsyncSession, order: TravelOrderRow) -> Optional[ChangeDecision]:
        """下单后出发前：出发日 ±2 天窗口计算退票重买净节省。"""
        legs = (order.legs or {}).get("legs", [])
        if not legs:
            return None
        target_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
        request = ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.PRICE_DROP, target_date=target_date)
        decision = await self.change_decision.decide(db, request, order)
        rec = decision.recommended
        if rec and rec.kind.value == "CANCEL_REBOOK" and rec.total_loss < -settings.TRAVEL_PRICE_DROP_THRESHOLD:
            await self.push.push(
                order.user_id,
                OutboundMessage(
                    kind="CARD",
                    text=f"📉 退票重买可节省 ¥{-rec.total_loss:.0f}：{decision.reason}。确认后我来执行。",
                    blocks=[o.model_dump() for o in decision.options],
                    correlation_id=order.order_no,
                ),
            )
            return decision
        return None


class FlightMonitorService:
    """航变监控（P6）：检测到航变 → ChangeDecisionService → 推送改签方案。"""

    def __init__(self, change_decision: ChangeDecisionService, push: PushService):
        self.change_decision = change_decision
        self.push = push

    async def scan(self, db: AsyncSession, order: TravelOrderRow) -> Optional[ChangeDecision]:
        # Mock 航变：仅演示流程（不真实调航变 API，接入后替换为航班动态查询）
        if order.status != OrderStatus.PAID.value:
            return None
        request = ChangeRequest(
            order_no=order.order_no,
            scenario=ChangeScenario.FLIGHT_CHANGE,
            target_date=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"),
        )
        decision = await self.change_decision.decide(db, request, order)
        if decision.recommended and decision.recommended.kind.value in ("CHANGE", "CANCEL_REBOOK"):
            await self.push.push(
                order.user_id,
                OutboundMessage(
                    kind="CARD",
                    text=f"⚠️ 检测到航变：{decision.reason}。确认后我来执行改签。",
                    blocks=[o.model_dump() for o in decision.options],
                    correlation_id=order.order_no,
                ),
            )
            return decision
        return None

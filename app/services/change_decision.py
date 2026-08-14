import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TravelOrderRow
from app.models.enums import ChangeKind, ChangeScenario
from app.models.schemas import (
    ChangeDecision, ChangeOption, ChangeRequest, PlanOption, TransportLeg,
    UserProfile,
)
from app.services.collector import DataCollectorService
from app.services.refund_rule import RefundRuleService

log = logging.getLogger("travel.change_decision")


class ChangeDecisionService:
    """
    改签/退票/降价/航变决策服务（B1 定稿）。
    成本模型：
      改签     总损失 = change_fee（与票价差无关，多不退少补）
      取消重买 总损失 = refund_fee + (new_price - old_price)   # 可为负 = 省钱
      取消不买 总损失 = refund_fee
      保持     总损失 = 0（需求未满足）
    打分：score = 0.5·cost + 0.3·requirement + 0.2·preference − riskPenalty
    """

    def __init__(self, collector: DataCollectorService, refund_rules: Optional[RefundRuleService] = None):
        self.collector = collector
        self.refund_rules = refund_rules or RefundRuleService()

    async def decide(
        self,
        db: AsyncSession,
        request: ChangeRequest,
        order: TravelOrderRow,
        profile: Optional[UserProfile] = None,
    ) -> ChangeDecision:
        now = datetime.now()
        legs = (order.legs or {}).get("legs", [])
        depart_at = self._mock_depart_at(now)
        rules = self.refund_rules.fee(order.price, depart_at, now, order.type)

        origin = legs[0].get("from_city") if legs else "北京"
        destination = legs[-1].get("to_city") if legs else "上海"

        options: List[ChangeOption] = []

        # 候选 KEEP：需求未满足
        keep = ChangeOption(
            kind=ChangeKind.KEEP,
            original_leg=legs[0] if legs else None,
            old_price=order.price,
            new_price=order.price,
            total_loss=0.0,
            satisfies_need=False,
            time_pref_match=True,
            risks=[],
            detail={"说明": "保持原行程"},
        )
        options.append(keep)

        # 候选 CANCEL：取消不买
        cancel = ChangeOption(
            kind=ChangeKind.CANCEL,
            original_leg=legs[0] if legs else None,
            old_price=order.price,
            new_price=0.0,
            refund_fee=rules["refund_fee"],
            total_loss=rules["refund_fee"],
            satisfies_need=False,
            risks=["退票后行程取消，出行需求未满足"],
            detail={"退票费": rules["refund_fee"]},
        )
        options.append(cancel)

        # 查目标班次（有目标日期才枚举 CHANGE / CANCEL_REBOOK）
        candidates: List[TransportLeg] = []
        if request.target_date:
            raw = await self.collector.search_transport(db, origin, destination, request.target_date)
            candidates = [TransportLeg(**r) for r in raw]

        if candidates:
            new_price = min(c.price for c in candidates)
            best_leg = min(candidates, key=lambda c: c.price).model_dump()

            change = ChangeOption(
                kind=ChangeKind.CHANGE,
                original_leg=legs[0] if legs else None,
                new_leg=best_leg,
                old_price=order.price,
                new_price=new_price,
                change_fee=rules["change_fee"],
                total_loss=rules["change_fee"],
                satisfies_need=True,
                time_pref_match=True,
                risks=["改签费多不退少补", "新时刻以实际票面为准"],
                detail={"改签费": rules["change_fee"], "新票价": new_price},
            )
            options.append(change)

            rebook_loss = rules["refund_fee"] + (new_price - order.price)
            rebook = ChangeOption(
                kind=ChangeKind.CANCEL_REBOOK,
                original_leg=legs[0] if legs else None,
                new_leg=best_leg,
                old_price=order.price,
                new_price=new_price,
                refund_fee=rules["refund_fee"],
                total_loss=round(rebook_loss, 2),
                satisfies_need=True,
                time_pref_match=True,
                risks=["新票为估算价，实际以支付为准", "建议先锁新票再退旧票"],
                detail={"退票费": rules["refund_fee"], "新票价": new_price, "价差": round(new_price - order.price, 2)},
            )
            options.append(rebook)

        # 打分排序（B1 公式）
        for opt in options:
            opt.score = self._score(opt, profile)

        # 推荐：满足需求且总损失最小的方案（KEEP/CANCEL 不满足需求，仅兜底）
        satisfying = [o for o in options if o.satisfies_need and o.kind != ChangeKind.KEEP]
        if satisfying:
            recommended = min(satisfying, key=lambda o: (o.total_loss, -o.score))
        else:
            recommended = min(options, key=lambda o: o.total_loss)

        reason = self._build_reason(recommended, order.price)
        return ChangeDecision(request=request, options=options, recommended=recommended, reason=reason)

    def _score(self, opt: ChangeOption, profile: Optional[UserProfile]) -> float:
        cost_score = 1.0 - min(1.0, max(0.0, opt.total_loss) / 1000.0)
        requirement_score = 1.0 if opt.satisfies_need else 0.3
        preference_score = 0.8
        if profile and profile.preferences:
            tolerate = profile.preferences.get("tolerate_change", True)
            if not tolerate and opt.kind == ChangeKind.CHANGE:
                preference_score = 0.3
        risk_penalty = 0.1 if opt.risks else 0.0
        return round(0.5 * cost_score + 0.3 * requirement_score + 0.2 * preference_score - risk_penalty, 4)

    def _build_reason(self, recommended: ChangeOption, old_price: float) -> str:
        kind_label = {
            ChangeKind.CHANGE: "改签",
            ChangeKind.CANCEL_REBOOK: "取消重买",
            ChangeKind.CANCEL: "取消退票",
            ChangeKind.KEEP: "保持原行程",
        }[recommended.kind]
        loss = recommended.total_loss
        if loss < 0:
            loss_text = f"可节省 ¥{-loss:.0f}"
        else:
            loss_text = f"总损失 ¥{loss:.0f}"
        return f"推荐方案：{kind_label}（{loss_text}，原票价 ¥{old_price:.0f}）"

    @staticmethod
    def _mock_depart_at(now: datetime) -> datetime:
        """Mock 出发时间：当前 +3 天 10:00（演示退改分档用）。"""
        depart = now + timedelta(days=3)
        return depart.replace(hour=10, minute=0, second=0, microsecond=0)

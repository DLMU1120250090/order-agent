"""Memory Context Builder / Resolver（Commit 2）。

把 L1/L3 记忆变成带来源标记的结构化槽位输入：
- EXPLICIT：用户本次明确表达；
- CONFIRMED：用户确认过的记忆推断值；
- INFERRED_FROM_MEMORY：来自记忆的推断值（高影响字段必须先确认）；
- DEFAULT：无记忆时的兜底（仍由 planner 原有逻辑处理，本组件不额外打断）。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from app.models.schemas import TravelSlotBundle, UserProfile


class SlotStatus(str, Enum):
    EXPLICIT = "EXPLICIT"
    CONFIRMED = "CONFIRMED"
    INFERRED_FROM_MEMORY = "INFERRED_FROM_MEMORY"
    DEFAULT = "DEFAULT"


# 高影响字段：记忆推断值必须显式确认后才进入规划
HIGH_IMPACT_CONFIRM_FIELDS = ["origin", "budget", "transportMode"]

# budget_level(tier) → 槽位中文标签
BUDGET_LABEL_BY_TIER = {"economy": "经济型", "comfort": "舒适型", "premium": "高端型"}
# preferences_v2 transport 值 → 槽位中文标签
TRANSPORT_LABEL_BY_VALUE = {"train": "高铁", "flight": "飞机", "bus": "大巴"}


@dataclass
class ResolvedSlotInfo:
    """单个推断字段的解析结果。"""
    value: Any
    source: str = ""  # l1_home_city / l1_budget_level / l3_preference
    status: SlotStatus = SlotStatus.INFERRED_FROM_MEMORY
    confidence: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "status": self.status.value,
            "confidence": self.confidence,
        }


@dataclass
class MemoryResolveResult:
    """一次解析的结果：补全后的槽位 + 推断字段明细 + 待确认字段。"""
    slots: TravelSlotBundle
    inferred: Dict[str, ResolvedSlotInfo] = field(default_factory=dict)
    pending_confirm: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "inferredFields": {k: v.to_dict() for k, v in self.inferred.items()},
            "pendingConfirm": list(self.pending_confirm),
        }


class MemoryResolver:
    """解析当前槽位 + L1/L3 记忆 → 决策输入（Commit 2）。"""

    def resolve(
        self,
        slots: TravelSlotBundle,
        profile: Optional[UserProfile],
        confirmed_fields: Optional[List[str]] = None,
    ) -> MemoryResolveResult:
        confirmed = set(confirmed_fields or [])
        resolved_slots = slots.model_copy(deep=True)
        inferred: Dict[str, ResolvedSlotInfo] = {}

        if profile:
            # L1：常驻城市补 origin
            if not resolved_slots.origin and profile.home_city:
                resolved_slots.origin = [profile.home_city]
                inferred["origin"] = ResolvedSlotInfo(profile.home_city, source="l1_home_city")
            # L1：预算档位补 budget（tier → 中文标签）
            if not resolved_slots.budget and profile.budget_level:
                label = BUDGET_LABEL_BY_TIER.get(profile.budget_level)
                if label:
                    resolved_slots.budget = [label]
                    inferred["budget"] = ResolvedSlotInfo(profile.budget_level, source="l1_budget_level")
            # L3（preferences_v2.user）：交通方式软偏好补 transportMode
            v2_user = (profile.preferences_v2 or {}).get("user") or {}
            transport_entry = v2_user.get("transport")
            if not resolved_slots.transportMode and transport_entry:
                value = str(transport_entry.get("value", "")).lower()
                label = TRANSPORT_LABEL_BY_VALUE.get(value)
                if label:
                    resolved_slots.transportMode = [label]
                    inferred["transportMode"] = ResolvedSlotInfo(
                        value,
                        source="l3_preference",
                        confidence=transport_entry.get("confidence"),
                    )

        for name, info in inferred.items():
            if name in confirmed:
                info.status = SlotStatus.CONFIRMED

        pending = [
            name
            for name in HIGH_IMPACT_CONFIRM_FIELDS
            if name in inferred and inferred[name].status == SlotStatus.INFERRED_FROM_MEMORY
        ]
        return MemoryResolveResult(slots=resolved_slots, inferred=inferred, pending_confirm=pending)


class MemoryContextBuilder:
    """按业务阶段构建结构化记忆上下文（Commit 2 先提供规划/澄清视图，Commit 7/8 扩展）。"""

    @staticmethod
    def build_for_planning(profile: Optional[UserProfile], result: MemoryResolveResult) -> dict:
        return {
            "user_context": {
                "home_city": profile.home_city if profile else None,
                "budget_level": profile.budget_level if profile else None,
            },
            "resolved": result.to_dict(),
        }

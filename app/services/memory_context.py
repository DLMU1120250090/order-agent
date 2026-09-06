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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import profile as profile_crud
from app.models.database import TripSummaryRow
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


def _v2_user_prefs(profile: Optional[UserProfile]) -> dict:
    return ((profile.preferences_v2 or {}) if profile else {}).get("user") or {}


def _entry_value(entry, cast=float):
    try:
        return cast((entry or {}).get("value"))
    except (TypeError, ValueError):
        return None


def monitor_context_from_profile(profile: Optional[UserProfile]) -> dict:
    """Monitor 场景记忆：降价触发比例 + 净节省阈值（未设置返回 None，服务端用默认常量）。"""
    user_prefs = _v2_user_prefs(profile)
    ratio = _entry_value(user_prefs.get("price_drop_ratio"))
    saving = _entry_value(user_prefs.get("saving_threshold_yuan"))
    return {
        "priceDropRatio": ratio if (ratio and 0 < ratio < 0.5) else None,
        "savingThresholdYuan": saving if (saving and saving > 0) else None,
    }


def reminder_context_from_profile(profile: Optional[UserProfile]) -> dict:
    """Reminder 场景记忆：提前提醒窗口（小时，默认 24，限 1~168）。"""
    hours = _entry_value(_v2_user_prefs(profile).get("remind_lead_hours"), cast=int)
    return {"remindLeadHours": hours if hours and 1 <= hours <= 168 else 24}


def change_context_from_profile(profile: Optional[UserProfile], passengers: list) -> dict:
    """Change 场景记忆：容忍变动 + 首个乘客的个性化偏好（时间/交通等）。"""
    flat = (profile.preferences or {}) if profile else {}
    passenger_prefs = {}
    if profile:
        v2_passengers = (profile.preferences_v2 or {}).get("passengers") or {}
        for p in passengers or []:
            pid = p.get("passenger_id") or p.get("id_no") or p.get("name")
            if not pid:
                continue
            entries = v2_passengers.get(str(pid)) or {}
            passenger_prefs[str(pid)] = {
                key: (entry or {}).get("value")
                for key, entry in entries.items()
            }
            break  # 本轮只取首个乘客，避免上下文膨胀
    return {
        "tolerateChange": bool(flat.get("tolerate_change", True)),
        "passengerPrefs": passenger_prefs,
    }


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

    async def build_for_planning(
        self,
        db: AsyncSession,
        user_id: int,
        result: MemoryResolveResult,
    ) -> dict:
        """规划视图：user_context + resolved + 相似历史 Episode（L2，仅解释不排序）。"""
        slots = result.slots
        origin = (slots.origin or [None])[0]
        destination = (slots.destination or [None])[0]
        res = await db.execute(
            select(TripSummaryRow)
            .where(TripSummaryRow.user_id == user_id)
            .order_by(TripSummaryRow.created_at.desc())
            .limit(20)
        )
        similar = []
        for r in res.scalars().all():
            ep = r.episode_json or {}
            ctx = ep.get("context") or {}
            if origin and ctx.get("origin") != origin:
                continue
            if destination and ctx.get("destination") != destination:
                continue
            plan = ep.get("selected_plan") or {}
            similar.append({
                "orderNo": plan.get("order_no"),
                "mode": plan.get("mode"),
                "depart": plan.get("depart"),
                "price": plan.get("price"),
                "reason": (ep.get("decision_reason") or [])[:1],
            })
            if len(similar) >= 3:
                break
        return {
            "userContext": {
                "homeCity": (slots.origin or [None])[0],
                "budget": (slots.budget or [None])[0],
            },
            "resolved": result.to_dict(),
            "similarEpisodes": similar,
        }

    async def build_for_monitoring(self, db: AsyncSession, user_id: int) -> dict:
        profile = await profile_crud.get_profile(db, user_id)
        return monitor_context_from_profile(profile)

    async def build_for_reminder(self, db: AsyncSession, user_id: int) -> dict:
        profile = await profile_crud.get_profile(db, user_id)
        return reminder_context_from_profile(profile)

    async def build_for_change(self, db: AsyncSession, user_id: int, order) -> dict:
        """Change 场景：容忍变动 + 乘客偏好 + 同路线相似历史（仅解释，不参与成本计算）。"""
        profile = await profile_crud.get_profile(db, user_id)
        legs = (order.legs or {}).get("legs", []) if order else []
        passengers = (order.passengers or {}).get("list", []) if order else []
        origin = legs[0].get("from_city") if legs else None
        destination = legs[-1].get("to_city") if legs else None

        similar = []
        if origin and destination:
            res = await db.execute(
                select(TripSummaryRow)
                .where(TripSummaryRow.user_id == user_id)
                .order_by(TripSummaryRow.created_at.desc())
                .limit(20)
            )
            for r in res.scalars().all():
                ep = r.episode_json or {}
                ctx = ep.get("context") or {}
                if ctx.get("origin") != origin or ctx.get("destination") != destination:
                    continue
                plan = ep.get("selected_plan") or {}
                similar.append({
                    "mode": plan.get("mode"),
                    "depart": plan.get("depart"),
                    "price": plan.get("price"),
                    "decisionReason": (ep.get("decision_reason") or [])[:1],
                })
                if len(similar) >= 2:
                    break

        context = change_context_from_profile(profile, passengers)
        context["similarTrips"] = similar
        return context

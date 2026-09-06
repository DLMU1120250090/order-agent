"""离线 Replay（Commit 3 最小版）。

从历史 Trace 提取 case（intent / slots / 原结果摘要），对规则层做 dry-run 重放：
1. Clarify 规则：missing_slots → READY / ASK；
2. ItineraryPlanner：_plan_candidates（不落库，避免污染业务数据）；
3. ChangeDecisionService：按 trace 中记录的场景与目标日期重算（订单仍存在时）。

确定性：重放不调用任何 LLM；外部数据优先命中 data_cache（mock 模式下为固定数据）。
对比：before（Trace 原结果）与 after（重放结果）的字段级 diff 摘要。
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import order as order_crud
from app.crud import profile as profile_crud
from app.models.database import RequestTraceRow
from app.models.enums import Intent
from app.models.schemas import ChangeRequest, TravelSlotBundle
from app.services.change_decision import ChangeDecisionService
from app.services.clarify_rule import ClarifyRuleService
from app.services.collector import DataCollectorService
from app.services.planner import ItineraryPlanner

log = logging.getLogger("travel.replay")

_SLOT_FIELDS = [
    "origin", "destination", "tripDate", "returnDate",
    "budget", "travelStyle", "transportMode", "companion",
]

_PLAN_INTENTS = {
    Intent.PLAN_RECOMMENDATION.value,
    Intent.PLAN_ADJUST.value,
    Intent.CLARIFY_NEEDED.value,
}


def _events_of(row: RequestTraceRow) -> list:
    raw = row.trace_json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
    if not isinstance(raw, dict):
        return []
    return raw.get("events") or []


def _output_of(events: list, event_type: str) -> Optional[dict]:
    for e in events:
        if e.get("eventType") != event_type:
            continue
        out = e.get("outputPayload")
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except Exception:  # noqa: BLE001
                out = None
        if isinstance(out, dict):
            return out
    return None


def _extract_case(row: RequestTraceRow) -> dict:
    """从一条 Trace 提取重放 case（原始结果摘要，供 before 对比）。"""
    events = _events_of(row)
    intent_out = _output_of(events, "INTENT_REVISED") or _output_of(events, "INTENT_RECOGNIZED") or {}
    merged_out = _output_of(events, "SLOTS_MERGED") or {}
    clarify_out = _output_of(events, "CLARIFY_DECISION") or {}
    plan_out = _output_of(events, "PLAN_RANKED") or {}
    change_out = _output_of(events, "ORDER_CHANGE_DECISION") or {}

    slots = {name: (merged_out.get(name) or []) for name in _SLOT_FIELDS}
    if not any(slots.values()):
        intent_slots = intent_out.get("slots") or {}
        slots = {name: (intent_slots.get(name) or []) for name in _SLOT_FIELDS}

    return {
        "intent": intent_out.get("intent"),
        "slots": slots,
        "clarifyAction": clarify_out.get("action"),
        "missingSlots": clarify_out.get("missingSlots") or [],
        "planCount": plan_out.get("optionCount"),
        "planIds": plan_out.get("options") or [],
        "change": change_out,
    }


def _top_plan_summary(options) -> List[dict]:
    out = []
    for opt in options:
        first = opt.legs[0] if opt.legs else None
        out.append({
            "price": opt.total_price,
            "duration": opt.total_duration_h,
            "firstMode": first.mode if first else None,
            "depart": first.depart if first else None,
            "score": opt.score,
        })
    return out


def _flatten(prefix: str, obj: Any, out: dict) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}.{k}" if prefix else str(k), v, out)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _flatten(f"{prefix}[{i}]", v, out)
    else:
        out[prefix] = obj


def diff_maps(before: dict, after: dict) -> dict:
    """字段级 diff：拍平两层 dict 后比较，返回变化清单。"""
    flat_b, flat_a = {}, {}
    _flatten("", before or {}, flat_b)
    _flatten("", after or {}, flat_a)
    changes = []
    for path in sorted(set(flat_b) | set(flat_a)):
        vb, va = flat_b.get(path, "<missing>"), flat_a.get(path, "<missing>")
        if vb != va:
            changes.append({"path": path, "before": vb, "after": va})
    return {"identical": not changes, "changes": changes}


class ReplayService:
    """Trace → 规则层重放 → before/after 对比（Commit 3）。"""

    def __init__(self):
        self.collector = DataCollectorService()
        self.clarify_rules = ClarifyRuleService()
        self.planner = ItineraryPlanner(self.collector)
        self.change_decision = ChangeDecisionService(self.collector)

    async def replay_trace(self, db: AsyncSession, trace_id: str, user_id: int) -> dict:
        res = await db.execute(
            select(RequestTraceRow).where(
                RequestTraceRow.trace_id == trace_id,
                RequestTraceRow.user_id == user_id,
            )
        )
        row = res.scalars().first()
        if not row:
            raise LookupError(f"Trace 不存在或无权访问: {trace_id}")

        case = _extract_case(row)
        slots = TravelSlotBundle(**case["slots"])

        # ---------- 1) Clarify 规则层 ----------
        clarify_before = {
            "clarifyAction": case.get("clarifyAction"),
            "missingSlots": case.get("missingSlots") or [],
        }
        try:
            missing_after = self.clarify_rules.missing_slots(slots, fuzzy_date=False)
            clarify_after = {
                "clarifyAction": "ASK" if missing_after else "READY",
                "missingSlots": missing_after,
            }
        except Exception as e:  # noqa: BLE001
            clarify_after = {"error": f"{e.__class__.__name__}: {e}"}

        # ---------- 2) Planner 规则层（dry-run 不落库） ----------
        planner_before = {
            "planCount": case.get("planCount"),
            "planIds": case.get("planIds") or [],
        }
        planner_after = {"skipped": "原 Trace 非规划意图或槽位不足"}
        run_planner = (
            case.get("intent") in _PLAN_INTENTS
            and clarify_after.get("clarifyAction") == "READY"
            and bool(slots.destination and slots.tripDate)
        )
        if run_planner:
            try:
                profile = await profile_crud.get_profile(db, user_id)
                decision = await self.planner._plan_candidates(db, slots, profile)
                planner_after = {
                    "planCount": len(decision.options),
                    "topPlans": _top_plan_summary(decision.options),
                    "reason": decision.reason,
                }
            except Exception as e:  # noqa: BLE001
                planner_after = {"error": f"{e.__class__.__name__}: {e}"}

        # ---------- 3) ChangeDecision 规则层 ----------
        change_before = {}
        change_after = {"skipped": "原 Trace 无改签/退票决策记录"}
        change_out = case.get("change") or {}
        request_info = change_out.get("request") or {}
        if request_info.get("order_no"):
            order = await order_crud.get_order_by_no(db, user_id, request_info.get("order_no"))
            if not order:
                change_after = {"skipped": "订单已不存在，无法重放"}
            else:
                try:
                    req = ChangeRequest(
                        order_no=request_info["order_no"],
                        scenario=request_info.get("scenario") or "USER_CHANGE",
                        target_date=request_info.get("target_date"),
                    )
                    profile = await profile_crud.get_profile(db, user_id)
                    decision = await self.change_decision.decide(db, req, order, profile)
                    rec = decision.recommended
                    change_before = {
                        "scenario": request_info.get("scenario"),
                        "recommendedKind": (change_out.get("recommended") or {}).get("kind"),
                        "recommendedLoss": (change_out.get("recommended") or {}).get("total_loss"),
                    }
                    change_after = {
                        "scenario": getattr(req.scenario, "value", req.scenario),
                        "recommendedKind": rec.kind.value if rec else None,
                        "recommendedLoss": rec.total_loss if rec else None,
                        "reason": decision.reason,
                    }
                except Exception as e:  # noqa: BLE001
                    change_after = {"error": f"{e.__class__.__name__}: {e}"}

        layers = {
            "clarify": {"before": clarify_before, "after": clarify_after},
            "planner": {"before": planner_before, "after": planner_after},
            "change": {"before": change_before, "after": change_after},
        }
        diffs = {name: diff_maps(l["before"], l["after"]) for name, l in layers.items()}
        return {
            "traceId": trace_id,
            "sessionId": row.session_id,
            "userId": user_id,
            "intent": case.get("intent"),
            "replayedAt": datetime.utcnow().isoformat(),
            "layers": layers,
            "diff": diffs,
            "note": "规则层重放不调用 LLM；外部数据命中 data_cache；planner 为 dry-run 不落库。",
        }

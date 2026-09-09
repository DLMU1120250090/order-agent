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
from app.services.memory_context import MemoryContextBuilder
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


def _parse_payload(value) -> Optional[dict]:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:  # noqa: BLE001
            return None
    return value if isinstance(value, dict) else None


def llm_golden_of(row: RequestTraceRow) -> dict:
    """LLM golden（Commit 10）：默认不重跑，取 trace 内记录的当时 LLM/Agent 输出。"""
    events = _events_of(row)
    golden_intent = None
    agent_outputs = []
    final_reply = ""
    for e in events:
        event_type = e.get("eventType")
        out = _parse_payload(e.get("outputPayload")) or {}
        if event_type == "INTENT_REVISED" and out.get("intent"):
            golden_intent = out["intent"]
        elif event_type == "AGENT_CALL":
            text = e.get("outputPayload") or e.get("errorMessage") or ""
            if text:
                agent_outputs.append(str(text)[:300])
        elif event_type == "RESPONSE_READY" and out.get("speechText"):
            final_reply = str(out["speechText"])[:200]
    return {
        "goldenIntent": golden_intent,
        "agentOutputs": agent_outputs[:2],
        "finalReply": final_reply,
    }


def _find_event(events: list, event_type: str) -> Optional[dict]:
    for e in events:
        if e.get("eventType") == event_type:
            return e
    return None


def _extract_case(row: RequestTraceRow) -> dict:
    """从一条 Trace 提取重放 case（原始结果摘要，供 before 对比）。"""
    events = _events_of(row)
    intent_ev = _find_event(events, "INTENT_REVISED") or _find_event(events, "INTENT_RECOGNIZED")
    intent_out = _parse_payload(intent_ev.get("outputPayload")) if intent_ev else {}

    merged_ev = _find_event(events, "SLOTS_MERGED")
    merged_out = _parse_payload(merged_ev.get("outputPayload")) if merged_ev else {}

    clarify_ev = _find_event(events, "CLARIFY_DECISION")
    clarify_out = _parse_payload(clarify_ev.get("outputPayload")) if clarify_ev else {}

    plan_ev = _find_event(events, "PLAN_RANKED")
    plan_out = _parse_payload(plan_ev.get("outputPayload")) if plan_ev else {}

    change_ev = _find_event(events, "ORDER_CHANGE_DECISION")
    change_out = _parse_payload(change_ev.get("outputPayload")) if change_ev else {}
    change_in = _parse_payload(change_ev.get("inputPayload")) if change_ev else {}

    resp_ev = _find_event(events, "RESPONSE_READY")
    resp_out = _parse_payload(resp_ev.get("outputPayload")) if resp_ev else {}

    top_plans = []
    if resp_out and isinstance(resp_out.get("blocks"), list):
        for b in resp_out["blocks"]:
            if isinstance(b, dict) and b.get("planId") is not None:
                first_leg = (b.get("legs") or [{}])[0] if isinstance(b.get("legs"), list) and b.get("legs") else {}
                top_plans.append({
                    "price": b.get("totalPrice") or b.get("price"),
                    "duration": b.get("totalDurationH") or b.get("duration"),
                    "firstMode": first_leg.get("mode"),
                    "depart": first_leg.get("depart"),
                    "score": b.get("score"),
                })

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
        "topPlans": top_plans,
        "change": change_out,
        "changeReq": change_in or change_out.get("request") or {},
        "sourceEvents": {
            "clarify": clarify_ev,
            "planner": plan_ev,
            "change": change_ev,
        },
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
        self.memory_builder = MemoryContextBuilder()

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
        clarify_ev = case.get("sourceEvents", {}).get("clarify")
        is_plan_scope = (case.get("intent") in _PLAN_INTENTS) or (clarify_ev is not None)

        if not is_plan_scope:
            clarify_before = {"skipped": "原 Trace 非出行规划意图，无需澄清"}
            clarify_after = {"skipped": "原 Trace 非出行规划意图，无需澄清"}
        elif clarify_ev is None:
            clarify_before = {"skipped": "原 Trace 未经历澄清判定阶段"}
            clarify_after = {"skipped": "原 Trace 未经历澄清判定阶段"}
        else:
            clarify_before = {
                "clarifyAction": case.get("clarifyAction"),
                "missingSlots": sorted(case.get("missingSlots") or []),
            }
            try:
                missing_after = self.clarify_rules.missing_slots(slots, fuzzy_date=False)
                clarify_after = {
                    "clarifyAction": "ASK" if missing_after else "READY",
                    "missingSlots": sorted(missing_after),
                }
            except Exception as e:  # noqa: BLE001
                clarify_after = {"error": f"{e.__class__.__name__}: {e}"}

        # ---------- 2) Planner 规则层（dry-run 不落库） ----------
        plan_ev = case.get("sourceEvents", {}).get("planner")
        is_planner_scope = (case.get("intent") in _PLAN_INTENTS) or (plan_ev is not None)

        if not is_planner_scope:
            planner_before = {"skipped": "原 Trace 非出行规划意图，跳过方案排序"}
            planner_after = {"skipped": "原 Trace 非出行规划意图，跳过方案排序"}
        else:
            run_planner = (
                clarify_after.get("clarifyAction") == "READY"
                and bool(slots.destination and slots.tripDate)
            )

            # 生产与重放双向均未进入规划阶段
            if plan_ev is None and not run_planner:
                planner_before = {"skipped": "原 Trace 规划槽位不足，未进入方案规划阶段"}
                planner_after = {"skipped": "原 Trace 规划槽位不足，未进入方案规划阶段"}
            else:
                if plan_ev is not None:
                    planner_before = {
                        "planCount": case.get("planCount"),
                        "planIds": [str(x) for x in (case.get("planIds") or [])],
                    }
                    if case.get("topPlans"):
                        planner_before["topPlans"] = case.get("topPlans")
                else:
                    planner_before = {"skipped": "原 Trace 停留在澄清阶段，未执行方案规划"}

                if run_planner:
                    try:
                        profile = await profile_crud.get_profile(db, user_id)
                        decision = await self.planner._plan_candidates(db, slots, profile)
                        planner_after = {
                            "planCount": len(decision.options),
                            "planIds": [str(o.plan_id) for o in decision.options],
                        }
                        if case.get("topPlans"):
                            planner_after["topPlans"] = _top_plan_summary(decision.options)
                    except Exception as e:  # noqa: BLE001
                        planner_after = {"error": f"{e.__class__.__name__}: {e}"}
                else:
                    planner_after = {"skipped": "原 Trace 规划槽位不足，跳过方案规划"}

        # ---------- 3) ChangeDecision 规则层 ----------
        change_ev = case.get("sourceEvents", {}).get("change")
        change_out = case.get("change") or {}
        request_info = case.get("changeReq") or change_out.get("request") or {}
        order_no = request_info.get("order_no") or request_info.get("orderNo")

        if not change_ev and not order_no:
            change_before = {"skipped": "原 Trace 无改签/退票决策记录"}
            change_after = {"skipped": "原 Trace 无改签/退票决策记录"}
        else:
            scenario_raw = request_info.get("scenario") or "USER_CHANGE"
            scenario_val = scenario_raw.value if hasattr(scenario_raw, "value") else str(scenario_raw)
            rec_before = change_out.get("recommended") or {}

            change_before = {
                "orderNo": order_no,
                "scenario": scenario_val,
                "targetDate": request_info.get("target_date") or request_info.get("targetDate"),
                "recommendedKind": rec_before.get("kind"),
                "recommendedLoss": rec_before.get("total_loss"),
                "reason": change_out.get("reason"),
            }

            order = await order_crud.get_order_by_no(db, user_id, order_no) if order_no else None
            if not order:
                change_after = {"skipped": f"订单 {order_no} 已不存在，无法重放"}
            else:
                try:
                    req = ChangeRequest(
                        order_no=order_no,
                        scenario=scenario_val,
                        target_date=request_info.get("target_date") or request_info.get("targetDate"),
                    )
                    profile = await profile_crud.get_profile(db, user_id)
                    change_ctx = await self.memory_builder.build_for_change(db, user_id, order)
                    decision = await self.change_decision.decide(db, req, order, profile, context=change_ctx)
                    rec = decision.recommended
                    change_after = {
                        "orderNo": req.order_no,
                        "scenario": getattr(req.scenario, "value", req.scenario),
                        "targetDate": req.target_date,
                        "recommendedKind": rec.kind.value if rec else None,
                        "recommendedLoss": rec.total_loss if rec else None,
                        "reason": decision.reason,
                    }
                except Exception as e:  # noqa: BLE001
                    change_after = {"error": f"{e.__class__.__name__}: {e}"}

        def _build_source(ev: Optional[dict], default_type: str, friendly_name: str) -> dict:
            if not ev:
                return {
                    "hasEvent": False,
                    "stepOrder": None,
                    "eventType": default_type,
                    "agentName": None,
                    "rawEvent": None,
                    "summary": f"原 Trace 未经历【{friendly_name}】阶段（无对应事件节点）",
                }
            return {
                "hasEvent": True,
                "stepOrder": ev.get("stepOrder"),
                "eventType": ev.get("eventType") or default_type,
                "agentName": ev.get("agentName"),
                "timestamp": ev.get("timestamp"),
                "rawEvent": {
                    "stepOrder": ev.get("stepOrder"),
                    "eventType": ev.get("eventType"),
                    "agentName": ev.get("agentName"),
                    "inputPayload": _parse_payload(ev.get("inputPayload")),
                    "outputPayload": _parse_payload(ev.get("outputPayload")),
                },
                "summary": f"来源于节点 #{ev.get('stepOrder')} [{ev.get('eventType')}]",
            }

        src_map = case.get("sourceEvents") or {}
        layers = {
            "clarify": {
                "before": clarify_before,
                "after": clarify_after,
                "source": _build_source(src_map.get("clarify"), "CLARIFY_DECISION", "澄清判定"),
            },
            "planner": {
                "before": planner_before,
                "after": planner_after,
                "source": _build_source(src_map.get("planner"), "PLAN_RANKED", "多方案规划与排序"),
            },
            "change": {
                "before": change_before,
                "after": change_after,
                "source": _build_source(src_map.get("change"), "ORDER_CHANGE_DECISION", "改签退票决策"),
            },
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

    async def collect_cases(self, db: AsyncSession, user_id: int, topic: str = "recovery", limit: int = 10) -> dict:
        """按失败主题收集回归 case 集（Commit 10）：recovery / recommendation_reject / failed。"""
        safe_limit = max(1, min(200, limit or 10))
        trace_ids = None
        if topic == "recommendation_reject":
            from app.models.database import FeedbackRow

            fb_res = await db.execute(
                select(FeedbackRow.trace_id)
                .where(
                    FeedbackRow.user_id == user_id,
                    FeedbackRow.trace_id.is_not(None),
                    FeedbackRow.action.in_(["DISLIKE", "REJECT", "SWITCH", "REFRESH"]),
                )
                .order_by(FeedbackRow.id.desc())
                .limit(safe_limit)
            )
            trace_ids = [str(t) for t in fb_res.scalars().all() if t]
            if not trace_ids:
                return {"topic": topic, "total": 0, "cases": []}

        query = select(RequestTraceRow).where(RequestTraceRow.user_id == user_id)
        if topic == "recovery":
            query = query.where(RequestTraceRow.status == "FAILED")
        if trace_ids:
            query = query.where(RequestTraceRow.trace_id.in_(trace_ids))
        query = query.order_by(RequestTraceRow.id.desc()).limit(safe_limit)
        rows = list((await db.execute(query)).scalars().all())

        cases = []
        for row in rows:
            case = _extract_case(row)
            replay = await self.replay_trace(db, row.trace_id, user_id)
            cases.append({
                "traceId": row.trace_id,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
                "intent": case.get("intent"),
                "golden": llm_golden_of(row),
                "replay": replay,
            })
        return {"topic": topic, "total": len(cases), "cases": cases}

"""Commit 5：TraceEventSchema / EventType / 老事件兼容 单元测试。

运行：cd order-agent && python -m pytest tests/test_trace_schema.py -q
"""
import json
from types import SimpleNamespace

from app.services.evaluation import EvaluationService
from app.services.trace import TraceContext
from app.services.trace_schema import EventType, TraceEventSchema


def _payload(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_schema_accepts_new_fields_and_drops_none():
    event = TraceEventSchema(
        eventType=EventType.MEMORY_RESOLVED,
        phase="MEMORY",
        stateBefore="DRAFT",
        stateAfter="PAID",
        memorySources=["l1_home_city", "l1_budget_level"],
        inferredFields={"origin": {"value": "北京"}},
        toolName="memory_resolver",
    )
    data = event.model_dump(exclude_none=True)
    assert data["stateBefore"] == "DRAFT"
    assert data["stateAfter"] == "PAID"
    assert data["memorySources"] == ["l1_home_city", "l1_budget_level"]
    assert data["inferredFields"]["origin"]["value"] == "北京"
    assert data["toolName"] == "memory_resolver"
    assert "eventId" in data
    assert "retryNo" not in data


def test_schema_compatible_with_old_minimal_event():
    old = {"stepOrder": 1, "eventType": "PLAN_RANKED", "phase": "PLAN"}
    event = TraceEventSchema.model_validate(old)
    assert event.eventType == "PLAN_RANKED"
    assert event.stateBefore is None
    assert event.memorySources is None
    assert event.eventId


def test_record_event_writes_structured_fields():
    ctx = TraceContext("t1", "s1", 1)
    ctx.record_event(
        EventType.ORDER_STATUS_CHANGED,
        "ORDER",
        {"orderNo": "ORD1"},
        {"statusAfter": "PAID"},
        state_before="CHANGING",
        state_after="PAID",
        memory_sources=["l1_home_city"],
        inferred_fields={"origin": {"value": "北京"}},
    )
    data = ctx.events[0].to_dict()
    assert data["eventId"].startswith("ev_")
    assert data["stateBefore"] == "CHANGING"
    assert data["stateAfter"] == "PAID"
    assert data["memorySources"] == ["l1_home_city"]


def test_evaluation_parses_old_trace_without_regression():
    row = SimpleNamespace(
        status="SUCCESS",
        trace_json={
            "events": [
                {
                    "stepOrder": 1,
                    "eventType": EventType.INTENT_REVISED,
                    "phase": "INTENT",
                    "outputPayload": _payload({"intent": "PLAN_RECOMMENDATION", "slots": {"destination": ["上海"]}}),
                },
                {
                    "stepOrder": 2,
                    "eventType": EventType.SLOTS_MERGED,
                    "phase": "SLOT",
                    "outputPayload": _payload({
                        "destination": ["上海"], "tripDate": ["2026-09-20"], "budget": ["经济型"],
                    }),
                },
                {
                    "stepOrder": 3,
                    "eventType": EventType.CLARIFY_DECISION,
                    "phase": "CLARIFY",
                    "outputPayload": _payload({"action": "READY", "missingSlots": []}),
                },
                {
                    "stepOrder": 4,
                    "eventType": EventType.PLAN_RANKED,
                    "phase": "PLAN",
                    "outputPayload": _payload({"optionCount": 3, "options": ["1", "2", "3"]}),
                },
            ]
        },
    )
    snapshot = EvaluationService(judge_agent=None)._parse_trace_json(row)
    assert snapshot["intent"] == "PLAN_RECOMMENDATION"
    assert snapshot["slots"]["destination"] == ["上海"]
    assert snapshot["clarifyAction"] == "READY"
    assert snapshot["planRanked"] is True

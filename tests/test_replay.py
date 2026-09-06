"""Commit 3：离线 Replay——case 提取与 diff 工具单元测试。

运行：cd order-agent && python -m pytest tests/test_replay.py -q
"""
import json
from types import SimpleNamespace

from app.services.replay import _extract_case, diff_maps


def _payload(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _fake_row(events: list):
    return SimpleNamespace(trace_json={"events": events})


def test_extract_case_from_plan_trace():
    events = [
        {
            "eventType": "INTENT_REVISED",
            "outputPayload": _payload({
                "intent": "PLAN_RECOMMENDATION",
                "slots": {"destination": ["上海"]},
                "confidence": 0.9,
            }),
        },
        {
            "eventType": "SLOTS_MERGED",
            "outputPayload": _payload({
                "origin": [], "destination": ["上海"], "tripDate": ["2026-09-20"],
                "returnDate": [], "budget": ["经济型"], "travelStyle": [],
                "transportMode": [], "companion": [],
            }),
        },
        {
            "eventType": "CLARIFY_DECISION",
            "outputPayload": _payload({"action": "READY", "missingSlots": []}),
        },
        {
            "eventType": "PLAN_RANKED",
            "outputPayload": _payload({"optionCount": 3, "options": ["1", "2", "3"]}),
        },
    ]
    case = _extract_case(_fake_row(events))
    assert case["intent"] == "PLAN_RECOMMENDATION"
    assert case["slots"]["destination"] == ["上海"]
    assert case["slots"]["tripDate"] == ["2026-09-20"]
    assert case["clarifyAction"] == "READY"
    assert case["planCount"] == 3
    assert case["planIds"] == ["1", "2", "3"]


def test_extract_case_falls_back_to_intent_slots():
    events = [
        {
            "eventType": "INTENT_REVISED",
            "outputPayload": _payload({
                "intent": "PLAN_RECOMMENDATION",
                "slots": {"destination": ["杭州"]},
                "confidence": 0.8,
            }),
        },
    ]
    case = _extract_case(_fake_row(events))
    assert case["slots"]["destination"] == ["杭州"]


def test_diff_maps_identical_and_changes():
    before = {"planCount": 3, "top": {"price": 100, "ok": True}}
    after = {"planCount": 3, "top": {"price": 90, "ok": True}}
    same = diff_maps({"a": 1, "b": [1, 2]}, {"a": 1, "b": [1, 2]})
    assert same["identical"] is True
    assert same["changes"] == []
    changed = diff_maps(before, after)
    assert changed["identical"] is False
    assert any(c["path"] == "top.price" and c["before"] == 100 and c["after"] == 90 for c in changed["changes"])

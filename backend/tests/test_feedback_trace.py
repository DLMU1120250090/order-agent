"""Commit 9：Failure Taxonomy 分类器 单元测试。

运行：cd order-agent && python -m pytest tests/test_feedback_trace.py -q
"""
from types import SimpleNamespace

from app.services.evaluation import EvaluationService
from app.services.trace_schema import EventType

svc = EvaluationService(judge_agent=None)


def _fb(action):
    return SimpleNamespace(action=action)


def _row(status="SUCCESS", events=None):
    return SimpleNamespace(status=status, trace_json={"events": events or []})


def test_classify_understanding_and_planning():
    metrics = {"intentAccuracy": 0.0, "slotAccuracy": 1.0, "planGenerated": 1.0, "planConstraintSatisfied": 0.0}
    types = svc._classify_failures(metrics, {}, [], _row())
    assert "Understanding" in types
    assert "Planning" in types


def test_classify_recommendation_from_feedback():
    metrics = {"intentAccuracy": None, "planGenerated": 1.0, "planConstraintSatisfied": 1.0}
    types = svc._classify_failures(metrics, {}, [_fb("DISLIKE")], _row())
    assert types == ["Recommendation"]


def test_classify_tool_and_recovery():
    metrics = {}
    assert "Tool" in svc._classify_failures(metrics, {}, [], _row(status="SUCCESS", events=[{"eventType": EventType.TASK_FAILED}]))
    assert "Recovery" in svc._classify_failures(metrics, {}, [], _row(status="FAILED", events=[{"eventType": EventType.REQUEST_FAILED}]))


def test_recovered_agent_error_is_not_recovery():
    """Commit 10：Agent 调用报错但已兜底恢复（INTENT_FALLBACK + REQUEST_FINISHED）不应算请求失败。"""
    events = [
        {"eventType": EventType.AGENT_CALL, "errorMessage": "APIConnectionError"},
        {"eventType": "INTENT_FALLBACK"},
        {"eventType": EventType.REQUEST_FINISHED},
    ]
    types = svc._classify_failures({}, {}, [], _row(status="FAILED", events=events))
    assert "Recovery" not in types


def test_classify_policy_and_clean():
    metrics = {}
    assert "Policy" in svc._classify_failures(metrics, {"safetyCompliance": False}, [], _row())
    assert svc._classify_failures(metrics, {"safetyCompliance": True}, [], _row()) == []

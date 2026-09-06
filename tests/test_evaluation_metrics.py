"""Commit 6：Evaluation 2.0——链路聚合工具与新指标语义 单元测试。

运行：cd order-agent && python -m pytest tests/test_evaluation_metrics.py -q
"""
from types import SimpleNamespace

from app.services.evaluation import EvaluationService

svc = EvaluationService(judge_agent=None)


def _row(run_id=None, task_id=None, session_id="s1", status="SUCCESS", events=None, created_at=None):
    from datetime import datetime
    return SimpleNamespace(
        run_id=run_id,
        task_id=task_id,
        session_id=session_id,
        user_id=1,
        status=status,
        trace_id=f"trace_{id(events or [])}",
        duration_ms=100,
        error_message=None,
        trace_json={"events": events or []},
        created_at=created_at or datetime(2026, 9, 6),
        expected_intent=None,
        expected_slots=None,
        expected_clarify_action=None,
    )


def test_link_key_prefers_run_then_task_then_session():
    assert EvaluationService._link_key(_row(run_id="r1", task_id="t1", session_id="s1")) == "r1"
    assert EvaluationService._link_key(_row(task_id="t1", session_id="s1")) == "t1"
    assert EvaluationService._link_key(_row(session_id="s1")) == "s1"
    assert EvaluationService._link_key(_row(session_id="")) .startswith("trace:")


def test_merge_trace_rows_concats_events_and_fails_if_any_failed():
    a = _row(run_id="r1", events=[{"eventType": "A", "phase": "X"}])
    b = _row(run_id="r1", events=[{"eventType": "B", "phase": "Y"}], status="FAILED")
    merged = EvaluationService._merge_trace_rows([a, b])
    assert len(merged.trace_json["events"]) == 2
    assert merged.status == "FAILED"
    assert merged.trace_id == "link_r1"


def test_user_confirm_means_selection_not_payment():
    assert svc._user_confirm({"bookingStarted": True}) == 1.0
    assert svc._user_confirm({"bookingStarted": False}) is None


def test_payment_success_prefers_ground_truth():
    snap = {"bookingStarted": True, "paymentConfirmed": True}
    assert svc._payment_success(snap, {"paid": False}) == 0.0
    assert svc._payment_success(snap, {"paid": True}) == 1.0
    assert svc._payment_success(snap, None) == 1.0
    assert svc._payment_success({"bookingStarted": False}, {"paid": True}) is None
    assert svc._payment_success({"bookingStarted": True, "paymentConfirmed": False}, None) == 0.0


def test_plan_metrics_split_semantics():
    assert svc._plan_constraint_satisfied({"planRanked": True, "planOptionCount": 0}) == 0.0
    assert svc._plan_constraint_satisfied({"planRanked": True, "planOptionCount": 3}) == 1.0
    assert svc._plan_constraint_satisfied({"planRanked": False}) is None
    assert svc._plan_selected({"planRanked": True, "bookingStarted": True}) == 1.0
    assert svc._plan_selected({"planRanked": True, "bookingStarted": False}) == 0.0

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


def test_feedback_score_scheme_a():
    from types import SimpleNamespace

    # 1. 只有显式 5 星反馈
    fb_5star = [SimpleNamespace(rating=5, action="LIKE", reason=None)]
    score, exp, imp = svc._feedback_score(fb_5star, {})
    assert exp == 1.0
    assert imp is None
    assert score == 1.0

    # 2. 只有隐式下单转化（未显式打分）-> 80 分基准 × 0.85 折损 = 68 分
    score, exp, imp = svc._feedback_score([], {"bookingStarted": True})
    assert exp is None
    assert imp == 0.80
    assert round(score, 4) == round(0.80 * 0.85, 4)

    # 3. 显式打 2 星差评，但仍有隐式下单 -> 70% 显式(40分) + 30% 隐式(80分) = 52分
    fb_2star = [SimpleNamespace(rating=2, action="DISLIKE", reason="时刻不理想")]
    score, exp, imp = svc._feedback_score(fb_2star, {"bookingStarted": True})
    assert exp == 0.4
    assert imp == 0.8
    assert round(score, 2) == 0.52

    # 4. 显式 5 星好评 + 隐式下单 -> 70% 显式(100分) + 30% 隐式(80分) = 94分
    score, exp, imp = svc._feedback_score(fb_5star, {"bookingStarted": True})
    assert exp == 1.0
    assert imp == 0.8
    assert round(score, 2) == 0.94

    # 5. 纯闲聊或未发生反馈与转化 -> None
    score, exp, imp = svc._feedback_score([], {})
    assert score is None and exp is None and imp is None

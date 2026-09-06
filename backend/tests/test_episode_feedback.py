"""Commit 5（R2）：出行后评分 单元测试。

运行：cd order-agent && python -m pytest tests/test_episode_feedback.py -q
"""
from app.services.episode_feedback import apply_post_trip_rating


def test_apply_rating_preserves_episode_structure():
    ep = {
        "trip_id": 6, "user_id": 1, "passengers": ["0"],
        "context": {}, "constraints": {},
        "selected_plan": {"order_no": "ORD1"},
        "decision_reason": [], "outcome": {"booking_success": True, "rating": None},
        "trace_refs": [],
    }
    updated = apply_post_trip_rating(ep, 5, "很满意")
    assert updated["outcome"]["rating"] == 5
    assert updated["outcome"]["feedback"] == "很满意"
    assert updated["selected_plan"]["order_no"] == "ORD1"
    assert len(updated) == len(ep)


def test_apply_rating_without_reason():
    updated = apply_post_trip_rating({"outcome": {}}, 3)
    assert updated["outcome"]["rating"] == 3
    assert "feedback" not in updated["outcome"]

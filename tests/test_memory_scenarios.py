"""Commit 8：Memory 接入 Monitor / Change / Reminder 单元测试。

运行：cd order-agent && python -m pytest tests/test_memory_scenarios.py -q
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.models.schemas import UserProfile
from app.services.memory_context import (
    change_context_from_profile,
    monitor_context_from_profile,
    reminder_context_from_profile,
)
from app.services.monitor import _drop_exceeds, _saving_exceeds
from app.services.reminder import ReminderService


def _profile(v2_user=None, flat=None, passengers=None) -> UserProfile:
    return UserProfile(
        user_id=1,
        passengers=passengers or [],
        preferences=flat or {},
        preferences_v2={"user": v2_user or {}},
    )


def test_monitor_context_parses_preferences():
    p = _profile(v2_user={
        "price_drop_ratio": {"value": 0.03, "confidence": 0.9, "source": "rule"},
        "saving_threshold_yuan": {"value": 30, "source": "rule"},
    })
    ctx = monitor_context_from_profile(p)
    assert ctx == {"priceDropRatio": 0.03, "savingThresholdYuan": 30.0}
    assert monitor_context_from_profile(None) == {"priceDropRatio": None, "savingThresholdYuan": None}


def test_reminder_context_lead_hours_default_and_clamp():
    assert reminder_context_from_profile(None)["remindLeadHours"] == 24
    p = _profile(v2_user={"remind_lead_hours": {"value": 48, "source": "rule"}})
    assert reminder_context_from_profile(p)["remindLeadHours"] == 48
    p_bad = _profile(v2_user={"remind_lead_hours": {"value": 999, "source": "rule"}})
    assert reminder_context_from_profile(p_bad)["remindLeadHours"] == 24


def test_change_context_keeps_tolerance_and_passenger_prefs():
    passengers = [{"passenger_id": "P_A", "name": "张三"}]
    p = _profile(
        flat={"tolerate_change": False},
        v2_user={},
        passengers=passengers,
    )
    p.preferences_v2["passengers"] = {
        "P_A": {"time_window": {"value": "morning", "source": "distilled"}},
    }
    ctx = change_context_from_profile(p, passengers)
    assert ctx["tolerateChange"] is False
    assert ctx["passengerPrefs"] == {"P_A": {"time_window": "morning"}}
    assert "similarTrips" not in ctx  # similarTrips 由 async builder 追加


def test_monitor_threshold_boundaries():
    assert _drop_exceeds(100, 94, 0.05) is True
    assert _drop_exceeds(100, 94.99, 0.05) is True
    assert _drop_exceeds(100, 95, 0.05) is False  # 恰好 5% 不触发（严格大于）
    assert _drop_exceeds(100, 96.99, 0.03) is True
    assert _drop_exceeds(100, 96, 0.05) is False
    assert _drop_exceeds(100, 96, 0.08) is False
    assert _saving_exceeds(-60, 50) is True
    assert _saving_exceeds(-30, 50) is False


def test_reminder_departing_window_boundary():
    now = datetime(2026, 9, 6, 12, 0)
    # 出发时刻 = updated_at + 24h：updated 24h 前 → depart = now，落在 24h 窗口内
    order2 = SimpleNamespace(updated_at=now - timedelta(hours=24))
    assert ReminderService._departing_within(order2, hours=24) is True
    order3 = SimpleNamespace(updated_at=now - timedelta(hours=25))
    assert ReminderService._departing_within(order3, hours=24) is False

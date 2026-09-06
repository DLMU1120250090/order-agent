"""Commit 4（R2）：L3 蒸馏扩展 + conditions 预留 单元测试。

运行：cd order-agent && python -m pytest tests/test_distill_scope.py -q
"""
from types import SimpleNamespace

from app.models.schemas import TravelSlotBundle, UserProfile
from app.services.memory import (
    passenger_preferences_from_episodes,
    price_sensitivity_from_events,
)
from app.services.memory_context import MemoryResolver
from app.services.user_memory_events import UserEventType


def _ep(passengers, mode="TRAIN", depart="07:30"):
    return {"passengers": passengers, "selected_plan": {"mode": mode, "depart": depart, "price": 100}}


def test_passenger_preferences_group_by_passenger():
    eps = [
        _ep(["0"], "TRAIN", "07:30"),
        _ep(["0"], "TRAIN", "08:00"),
        _ep(["0"], "TRAIN", "09:00"),
        _ep(["P_M"], "FLIGHT", "16:00"),
    ]
    result = passenger_preferences_from_episodes(eps)
    assert result["0"]["transport"]["value"] == "train"
    assert result["0"]["time_window"]["value"] == "morning"
    assert "P_M" not in result  # 样本不足不硬造


def test_insufficient_or_mixed_not_distilled():
    assert passenger_preferences_from_episodes([_ep(["P_A"], "TRAIN")]) == {}
    mixed = [
        _ep(["P_A"], "TRAIN", "10:00"),
        _ep(["P_A"], "FLIGHT", "10:00"),
        _ep(["P_A"], "TRAIN", "10:00"),
        _ep(["P_A"], "FLIGHT", "10:00"),
    ]
    assert passenger_preferences_from_episodes(mixed) == {}


def test_price_sensitivity_thresholds():
    def ev(event_type):
        return SimpleNamespace(event_type=event_type)

    high = [ev(UserEventType.PRICE_DROP_ACCEPTED)] * 3
    assert price_sensitivity_from_events(high)["value"] == "high"
    low = [ev(UserEventType.PRICE_DROP_IGNORED)] * 3
    assert price_sensitivity_from_events(low)["value"] == "low"
    assert price_sensitivity_from_events([high[0], low[0]]) is None


def test_conditions_do_not_break_resolve():
    profile = UserProfile(user_id=1, passengers=[{"passenger_id": "P_A", "name": "家人", "role": "others"}])
    profile.preferences_v2 = {
        "passengers": {
            "P_A": {
                "transport": {
                    "value": "train", "source": "distilled",
                    "conditions": {"business_trip": True},
                },
            },
        },
    }
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(slots, profile, current_passenger_id="P_A")
    assert result.slots.transportMode == ["高铁"]
    assert result.passenger_preferences["transport"] == "train"

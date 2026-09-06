"""Commit 7：L3 规则蒸馏 + Planner 软偏好接入 单元测试。

运行：cd order-agent && python -m pytest tests/test_memory_planner.py -q
"""
from app.models.schemas import TravelSlotBundle
from app.services.memory import majority_transport_from_episodes
from app.services.planner import ItineraryPlanner


def _episode(mode: str) -> dict:
    return {"selected_plan": {"mode": mode, "depart": "09:00", "price": 100}}


def test_majority_transport_forms_preference():
    episodes = [_episode("TRAIN") for _ in range(6)] + [_episode("FLIGHT") for _ in range(2)]
    pref = majority_transport_from_episodes(episodes)
    assert pref == {"value": "train", "confidence": 0.75, "count": 6, "total": 8}


def test_majority_transport_needs_enough_samples():
    assert majority_transport_from_episodes([]) is None
    assert majority_transport_from_episodes([_episode("TRAIN"), _episode("FLIGHT")]) is None


def test_majority_transport_requires_clear_majority():
    mixed = [_episode("TRAIN") for _ in range(4)] + [_episode("FLIGHT") for _ in range(3)]
    assert majority_transport_from_episodes(mixed) is None


def test_planner_preferred_modes_accepts_l3_labels():
    planner = ItineraryPlanner(collector=None)
    assert planner._preferred_modes(TravelSlotBundle(transportMode=["高铁"])) == {"TRAIN"}
    assert planner._preferred_modes(TravelSlotBundle(transportMode=["飞机"])) == {"FLIGHT"}
    assert planner._preferred_modes(TravelSlotBundle(transportMode=[])) == set()

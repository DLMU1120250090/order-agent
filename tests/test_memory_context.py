"""Commit 2：Memory Resolver / 确认流程 单元测试。

运行：cd order-agent && python -m pytest tests/test_memory_context.py -q
"""
from app.models.schemas import TravelSlotBundle, UserProfile
from app.crud.session import parse_slots_and_meta, serialize_slots_and_meta
from app.models.enums import Channel, Intent, SessionPhase
from app.models.schemas import SessionState
from app.services.memory_context import MemoryResolver, SlotStatus
from app.services.orchestrator import MEMORY_CONFIRM_PATTERN, TravelOrchestratorService


def _profile(home_city=None, budget_level=None, prefs_v2=None) -> UserProfile:
    return UserProfile(user_id=1, home_city=home_city, budget_level=budget_level, preferences_v2=prefs_v2 or {})


def test_resolve_without_profile_no_change():
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(slots, None)
    assert result.slots.origin == []
    assert result.pending_confirm == []


def test_resolve_fills_origin_and_budget_from_l1():
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(slots, _profile(home_city="北京", budget_level="economy"))
    assert result.slots.origin == ["北京"]
    assert result.slots.budget == ["经济型"]
    assert result.pending_confirm == ["origin", "budget"]
    assert result.inferred["origin"].source == "l1_home_city"
    assert result.inferred["budget"].source == "l1_budget_level"


def test_resolve_confirmed_fields_no_pending():
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(
        slots, _profile(home_city="北京", budget_level="comfort"), confirmed_fields=["origin", "budget"]
    )
    assert result.slots.origin == ["北京"]
    assert result.slots.budget == ["舒适型"]
    assert result.inferred["origin"].status == SlotStatus.CONFIRMED
    assert result.inferred["budget"].status == SlotStatus.CONFIRMED
    assert result.pending_confirm == []


def test_resolve_explicit_slots_win():
    slots = TravelSlotBundle(origin=["上海"], destination=["杭州"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(slots, _profile(home_city="北京", budget_level="economy"))
    assert result.slots.origin == ["上海"]
    assert "origin" not in result.inferred
    assert result.pending_confirm == ["budget"]


def test_resolve_l3_transport_preference():
    v2 = {"user": {"transport": {"value": "train", "confidence": 0.91, "source": "distilled"}}}
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"], budget=["经济型"])
    result = MemoryResolver().resolve(slots, _profile(home_city="北京", prefs_v2=v2))
    assert result.slots.transportMode == ["高铁"]
    assert result.pending_confirm == ["origin", "transportMode"]
    assert result.inferred["transportMode"].confidence == 0.91


def test_confirm_question_template():
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-09-10"])
    result = MemoryResolver().resolve(slots, _profile(home_city="北京", budget_level="economy"))
    q = TravelOrchestratorService._memory_confirm_question(result)
    assert "从北京出发" in q
    assert "经济型预算" in q
    assert "回复“好”即可" in q


def test_confirm_pattern_full_match():
    for ok in ["好", "好的", "可以", "行", "行吧", "嗯嗯", "对", "OK", "okay", "按这个", "就这样"]:
        assert MEMORY_CONFIRM_PATTERN.match(ok), ok
    for no in ["出行", "好的，但预算低一点", "重新规划", "不是"]:
        assert not MEMORY_CONFIRM_PATTERN.match(no), no


def test_pending_confirms_state_roundtrip():
    state = SessionState(
        sessionId="s1",
        userId=1,
        phase=SessionPhase.CLARIFY,
        channel=Channel.web,
        currentIntent=Intent.CLARIFY_NEEDED,
        slots=TravelSlotBundle(destination=["上海"]),
        pendingConfirms=["origin", "budget"],
    )
    dumped = serialize_slots_and_meta(state)
    assert dumped["_meta"]["pendingConfirms"] == ["origin", "budget"]
    bundle, meta = parse_slots_and_meta(dumped)
    assert meta.get("pendingConfirms") == ["origin", "budget"]
    assert bundle.destination == ["上海"]

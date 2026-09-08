import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.schemas import (
    TravelSlotBundle,
    SessionState,
    SessionPhase,
    Intent,
    Channel,
    OrderStatus,
)
from app.models.database import TravelOrderRow
from app.crud.session import parse_slots_and_meta, serialize_slots_and_meta
from app.services.orchestrator import TravelOrchestratorService


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_orchestrator():
    return TravelOrchestratorService(
        MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
    )


def test_merge_slots_incremental_overwrite_and_retain():
    orchestrator = _make_orchestrator()

    history = TravelSlotBundle(
        origin=["北京"],
        destination=["上海"],
        tripDate=["2026-10-01"],
        budget=["经济型"],
        passengers=["张三"],
    )

    # Current turn updates destination and passengers, leaves others blank
    current = TravelSlotBundle(
        destination=["广州"],
        passengers=["张三", "李四"],
    )

    merged = orchestrator._merge_slots(history, current)

    # Destination is overwritten
    assert merged.destination == ["广州"]
    # Passengers is overwritten
    assert merged.passengers == ["张三", "李四"]
    # Origin, tripDate, and budget are retained from history
    assert merged.origin == ["北京"]
    assert merged.tripDate == ["2026-10-01"]
    assert merged.budget == ["经济型"]


def test_parse_slots_and_meta_passengers_roundtrip():
    state = SessionState(
        sessionId="sess_test_1",
        userId=1,
        phase=SessionPhase.CLARIFY,
        slots=TravelSlotBundle(
            destination=["上海"],
            tripDate=["2026-10-01"],
            passengers=["张三", "本人"],
        ),
    )

    serialized = serialize_slots_and_meta(state)
    assert serialized["passengers"] == ["张三", "本人"]

    bundle, meta = parse_slots_and_meta(serialized)
    assert bundle.destination == ["上海"]
    assert bundle.tripDate == ["2026-10-01"]
    assert bundle.passengers == ["张三", "本人"]


def test_fallback_slots_extracts_passengers():
    slots1 = TravelOrchestratorService._fallback_slots("我选择：张三(本人)")
    assert slots1.passengers == ["张三"]

    slots2 = TravelOrchestratorService._fallback_slots("去上海，就我一个人")
    assert "上海" in slots2.destination
    assert slots2.passengers == ["本人"]


@pytest.mark.anyio
async def test_finalize_payment_clears_slots():
    orchestrator = _make_orchestrator()

    # Mock dependencies of _finalize_payment
    orchestrator._write_profile_after_booking = AsyncMock()
    orchestrator._write_summary_async = AsyncMock()
    orchestrator.task_service = MagicMock()
    orchestrator.task_service.create = AsyncMock()
    orchestrator._save_state = AsyncMock()

    mock_db = AsyncMock()
    mock_order = TravelOrderRow(
        id=101,
        order_no="ORD20260908001",
        user_id=1,
        channel="web",
        status=OrderStatus.PAID.value,
        price=350.0,
    )

    initial_state = SessionState(
        sessionId="sess_100",
        userId=1,
        phase=SessionPhase.BOOKING,
        orderNo="ORD20260908001",
        orderId=101,
        slots=TravelSlotBundle(
            destination=["上海"],
            tripDate=["2026-09-10"],
            passengers=["张三"],
        ),
        lastRecommendations=["plan_1", "plan_2"],
        currentBatch=["plan_1"],
        selectedPlanId="plan_1",
    )

    new_state = await orchestrator._finalize_payment(
        mock_db, user_id=1, order=mock_order, state=initial_state
    )

    # State phase transitioned to ORDER
    assert new_state.phase == SessionPhase.ORDER
    assert new_state.orderNo == "ORD20260908001"
    # Slots should be cleared to empty bundle
    assert new_state.slots.destination == []
    assert new_state.slots.tripDate == []
    assert new_state.slots.passengers == []
    # Recommendations should be cleared
    assert new_state.lastRecommendations == []
    assert new_state.currentBatch == []
    assert new_state.selectedPlanId is None

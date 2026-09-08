"""Commit 1（R2）：乘客选择流程 单元测试。

运行：cd order-agent && python -m pytest tests/test_passenger_selection.py -q
"""
from app.crud.session import parse_slots_and_meta, serialize_slots_and_meta
from app.models.enums import Channel, Intent, SessionPhase
from app.models.schemas import SessionState, TravelSlotBundle, UserProfile
from app.services.orchestrator import (
    passenger_selection_gate,
    passenger_selection_question,
    resolve_passenger_choice,
    resolve_passenger_choices,
    resolve_passenger_ids_from_slots,
)


def _profile(passengers) -> UserProfile:
    return UserProfile(user_id=1, passengers=passengers)


def _state(pending=False, done=False, current="0"):
    return SessionState(
        sessionId="s1",
        userId=1,
        phase=SessionPhase.PLAN,
        channel=Channel.web,
        currentIntent=Intent.PLAN_BOOK,
        slots=TravelSlotBundle(),
        passengerSelectionPending=pending,
        passengerSelectionDone=done,
        currentPassengerId=current,
    )


def test_gate_single_self_no_ask():
    profile = _profile([{"name": "本人", "id_no": "S1", "role": "self", "passenger_id": "0"}])
    assert passenger_selection_gate(profile, _state()) == "0"


def test_gate_multi_requires_selection_once():
    profile = _profile([
        {"name": "本人", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "妈妈", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
    ])
    assert passenger_selection_gate(profile, _state()) == "ASK"
    assert passenger_selection_gate(profile, _state(pending=True)) == "ASK"
    assert passenger_selection_gate(profile, _state(done=True, current="P_M1")) == "P_M1"
    assert passenger_selection_gate(profile, _state(done=True, current="0")) == "0"


def test_resolve_choice():
    profile = _profile([
        {"name": "本人", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "妈妈", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
        {"name": "爸爸", "id_no": "D1", "role": "others", "passenger_id": "P_D1"},
    ])
    assert resolve_passenger_choice("本人", profile) == "0"
    assert resolve_passenger_choice("妈妈", profile) == "P_M1"
    assert resolve_passenger_choice("第2个", profile) == "P_D1"
    assert resolve_passenger_choice("2", profile) == "P_D1"
    assert resolve_passenger_choice("爷爷", profile) is None
    assert resolve_passenger_choice("", profile) is None


def test_question_lists_others():
    profile = _profile([
        {"name": "本人", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "妈妈", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
    ])
    q = passenger_selection_question(profile)
    assert "妈妈" in q
    assert "本人" in q


def test_state_roundtrip_passenger_fields():
    state = SessionState(
        sessionId="s1",
        userId=1,
        phase=SessionPhase.CLARIFY,
        channel=Channel.web,
        currentIntent=Intent.PLAN_BOOK,
        slots=TravelSlotBundle(),
        currentPassengerId="P_M1",
        passengerSelectionPending=True,
        passengerSelectionDone=False,
    )
    dumped = serialize_slots_and_meta(state)
    assert dumped["_meta"]["currentPassengerId"] == "P_M1"
    assert dumped["_meta"]["passengerSelectionPending"] is True
    _, meta = parse_slots_and_meta(dumped)
    assert meta.get("currentPassengerId") == "P_M1"
    assert meta.get("passengerSelectionPending") is True
    assert meta.get("passengerSelectionDone") is False


def test_resolve_choices_multi():
    profile = _profile([
        {"name": "本人", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "妈妈", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
        {"name": "爸爸", "id_no": "D1", "role": "others", "passenger_id": "P_D1"},
    ])
    assert resolve_passenger_choices("本人和妈妈", profile) == ["0", "P_M1"]
    assert resolve_passenger_choices("全部", profile) == ["0", "P_M1", "P_D1"]
    assert resolve_passenger_choices("爸爸", profile) == ["P_D1"]


def test_clarify_rule_requires_passengers():
    from app.services.clarify_rule import ClarifyRuleService
    svc = ClarifyRuleService()
    slots = TravelSlotBundle(destination=["上海"], tripDate=["2026-10-01"], budget=["经济型"])
    missing = svc.missing_slots(slots)
    assert "passengers" in missing

    slots_with_p = TravelSlotBundle(
        destination=["上海"], tripDate=["2026-10-01"], budget=["经济型"], passengers=["本人出行 (1人)"]
    )
    assert "passengers" not in svc.missing_slots(slots_with_p)


def test_gate_bypasses_ask_if_slots_contain_passenger():
    profile = _profile([
        {"name": "张三", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "李雷", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
    ])
    # 规划阶段槽位已有本人名字或本人
    state_self_name = _state()
    state_self_name.slots.passengers = ["张三"]
    assert passenger_selection_gate(profile, state_self_name) == "0"

    state_self_keyword = _state()
    state_self_keyword.slots.passengers = ["本人出行 (1人)"]
    assert passenger_selection_gate(profile, state_self_keyword) == "0"

    # 规划阶段槽位指定了同行人李雷
    state_other = _state()
    state_other.slots.passengers = ["李雷"]
    assert passenger_selection_gate(profile, state_other) == "P_M1"


def test_resolve_passenger_by_self_name_and_slots():
    profile = _profile([
        {"name": "张三", "id_no": "S1", "role": "self", "passenger_id": "0"},
        {"name": "李雷", "id_no": "M1", "role": "others", "passenger_id": "P_M1"},
    ])
    # 精确或包含姓名匹配本人
    assert resolve_passenger_choice("张三", profile) == "0"
    assert resolve_passenger_choice("张三(本人)", profile) == "0"
    assert resolve_passenger_choices("张三", profile) == ["0"]

    # 从槽位列表多选解析
    assert resolve_passenger_ids_from_slots(["张三", "李雷"], profile) == ["0", "P_M1"]
    assert resolve_passenger_ids_from_slots(["我选择：张三(本人)"], profile) == ["0"]


from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from app.services.booking import BookingService
from app.models.schemas import PlanOption, TransportLeg


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_create_order_draft_defines_order_no_and_pricing():
    qr = MagicMock()
    push = MagicMock()
    task = MagicMock()
    service = BookingService(qr_capture=qr, push_service=push, task_service=task)

    db = AsyncMock()
    plan = PlanOption(
        plan_id="p1",
        legs=[
            TransportLeg(
                mode="TRAIN",
                from_city="北京",
                to_city="上海",
                depart="08:00",
                arrive="12:00",
                price=553.0,
            )
        ],
        total_price=553.0,
        total_duration_h=4.0,
    )
    passengers = [
        {"name": "张三", "passenger_id": "0"},
        {"name": "李雷", "passenger_id": "P_M1"},
    ]

    with patch("app.crud.profile.get_profile", new_callable=AsyncMock) as mock_prof, \
         patch("app.crud.order.get_order_by_idempotency", new_callable=AsyncMock) as mock_idem:
        mock_prof.return_value = None
        mock_idem.return_value = None
        order = await service.create_order_draft(db, user_id=1, plan=plan, passengers=passengers)
        assert order.order_no is not None
        assert order.order_no.startswith("ORD")
        assert order.price == 553.0 * 2
        assert order.tax_fee == 50.0 * 2
        assert len(order.passengers.get("list", [])) == 2




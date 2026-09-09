import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.models.schemas import OutboundMessage
from app.models.database import TravelOrderRow
from app.services.booking import BookingService
from app.services.mock_supplier import mock_supplier
from app.routers.chat import _to_chat_response


def test_booking_web_channel_does_not_push_redundant_image():
    async def _run():
        qr_mock = MagicMock()
        push_mock = MagicMock()
        push_mock.push = AsyncMock()
        task_mock = MagicMock()
        task_mock.update_progress = AsyncMock()
        task_mock.wait_user = AsyncMock()

        service = BookingService(qr_mock, push_mock, task_mock)
        db = AsyncMock()

        order = TravelOrderRow(
            id=100,
            user_id=1,
            order_no="ORD202609080001",
            channel="web",
            type="FLIGHT",
            price=350.0,
            status="PENDING",
        )

        service._resolve_qr_path = AsyncMock(return_value="/media/test.png")

        with pytest.MonkeyPatch.context() as mp:
            from app.crud import order as order_crud, task as task_crud
            from app.services.booking import browser_order
            mp.setattr(browser_order, "place_and_capture_qr", AsyncMock(return_value="/media/test.png"))
            mp.setattr(order_crud, "update_order", AsyncMock())
            mp.setattr(order_crud, "get_order_by_id", AsyncMock(return_value=order))
            mp.setattr(task_crud, "update_task", AsyncMock())

            result = await service.execute_booking(db, "task_123", order)
            assert result["status"] == "WAITING_PAYMENT"
            image_calls = [
                c for c in push_mock.push.call_args_list
                if len(c[0]) > 1 and getattr(c[0][1], "kind", None) == "IMAGE"
            ]
            assert len(image_calls) == 0, "Web 通道不应主动推送冗余的 IMAGE 消息气泡"

    asyncio.run(_run())


def test_chat_response_extracts_order_no_from_task_progress():
    msg = OutboundMessage(
        channel="web",
        kind="TASK_PROGRESS",
        text="已开始下单…",
        task_progress={"taskId": "task_abc", "status": "RUNNING", "progress": 10, "orderNo": "ORD202609089999"},
        correlation_id="task_abc",
    )
    resp = _to_chat_response(msg, "sess_1")
    assert resp.orderNo == "ORD202609089999"
    assert resp.taskId == "task_abc"


def test_mock_supplier_event_trigger():
    async def _run():
        order_no = "ORD-TEST-INSTANT"
        ev = mock_supplier.get_paid_event(order_no)
        assert not ev.is_set()

        mock_supplier.mark_paid(order_no)
        assert ev.is_set()
        assert mock_supplier.is_paid(order_no)

    asyncio.run(_run())

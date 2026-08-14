import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import order as order_crud
from app.crud import profile as profile_crud
from app.crud import task as task_crud
from app.models.database import TravelOrderRow
from app.models.enums import OrderStatus, OrderType, Supplier, PaymentPending
from app.models.schemas import ChangeDecision, OrderDraftOut, OutboundMessage, PlanOption, TransportLeg
from app.services.browser import browser_order
from app.services.mock_supplier import mock_supplier
from app.services.push import PushService
from app.services.qr_capture import QrCaptureService
from app.services.task import TaskService

log = logging.getLogger("travel.booking")


class BookingService:
    """
    下单/改签/退票执行服务（C3 定稿，Mock 供应商）。
    - 幂等设计：idempotency_key = hash(user_id + plan_id + 日期 + 乘客集合)
    - 支付检测三层：①页面变化 ②订单状态轮询 ③用户确认
    - 资金类失败不自动重试；二维码生成即推
    """

    def __init__(self, qr_capture: QrCaptureService, push_service: PushService, task_service: TaskService):
        self.qr_capture = qr_capture
        self.push_service = push_service
        self.task_service = task_service

    @staticmethod
    def _idempotency_key(user_id: int, plan_id: Optional[str], trip_date: str, passengers: List[dict]) -> str:
        raw = f"{user_id}|{plan_id}|{trip_date}|{sorted(p.get('name', '') for p in passengers or [])}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def create_order_draft(
        self,
        db: AsyncSession,
        user_id: int,
        plan: PlanOption,
        passengers: Optional[List[dict]] = None,
        channel: str = "web",
        task_id: Optional[str] = None,
        trip_id: Optional[int] = None,
    ) -> TravelOrderRow:
        profile = await profile_crud.get_profile(db, user_id)
        if not passengers:
            passengers = (profile.passengers if profile and profile.passengers else []) or [
                {"name": "演示乘客", "id_type": "身份证", "id_no": "110101199001011234", "id_expiry": "2035-12-31"}
            ]

        trip_date = (plan.legs[0].depart if plan.legs else datetime.now().strftime("%Y-%m-%d"))
        idem_key = self._idempotency_key(user_id, plan.plan_id, trip_date, passengers)

        existing = await order_crud.get_order_by_idempotency(db, idem_key)
        if existing:
            return existing

        first_mode = plan.legs[0].mode if plan.legs else "FLIGHT"
        order_no = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{user_id % 100:02d}"
        total_price = round(sum(leg.price for leg in plan.legs), 2)
        tax_fee = round(50.0, 2)

        row = TravelOrderRow(
            user_id=user_id,
            trip_id=trip_id,
            task_id=task_id,
            order_no=order_no,
            supplier=Supplier.mock.value,
            type=OrderType.FLIGHT.value if first_mode == "FLIGHT" else OrderType.TRAIN.value,
            status=OrderStatus.DRAFT.value,
            idempotency_key=idem_key,
            price=total_price,
            tax_fee=tax_fee,
            passengers={"list": passengers},
            legs={"legs": [leg.model_dump() for leg in plan.legs]},
            refund_rule={"kind": "MOCK", "note": "当前为 Mock 分档退改规则"},
            channel=channel,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def execute_booking(self, db: AsyncSession, task_id: str, order: TravelOrderRow) -> Dict[str, Any]:
        """后台协程：下单执行（Playwright Mock 收银台）+ 二维码推送 + 进入 WAITING_USER(PAYMENT)。"""
        await order_crud.update_order(db, order.id, status=OrderStatus.CONFIRMED.value)
        await self.task_service.update_progress(db, task_id, 40, "已确认方案，正在出票…")

        from app.config import settings as _settings

        qr_path = ""
        if _settings.TRAVEL_PLAYWRIGHT_ENABLED:
            try:
                mock_supplier.register(order.order_no)
                qr_path = await browser_order.place_and_capture_qr(order)
            except Exception as e:  # noqa: BLE001
                log.warning("Playwright 下单失败，回退 Mock 二维码: order=%s err=%s", order.order_no, e)
        if not qr_path:
            qr_path = await self._resolve_qr_path(order.order_no)
        await order_crud.update_order(db, order.id, status=OrderStatus.BOOKING.value)
        await self.task_service.update_progress(db, task_id, 70, "收银台已生成支付二维码")
        # 二维码结果先落任务 result，供前端在 WAITING_USER 期间展示
        await task_crud.update_task(
            db,
            task_id,
            result={"status": "WAITING_PAYMENT", "order_no": order.order_no, "qr_image_path": qr_path},
        )

        # 二维码生成即推（有时效）
        await self.push_service.push(
            order.user_id,
            OutboundMessage(
                kind="IMAGE",
                channel=order.channel,
                text=f"订单 {order.order_no} 待支付，请本人扫码完成支付（Agent 绝不代付）。支付后回复『付好了』。",
                image_path=qr_path,
                correlation_id=task_id,
            ),
        )
        await self.task_service.wait_user(db, task_id, PaymentPending.PAYMENT.value, "等待本人扫码支付…")
        return {
            "status": "WAITING_PAYMENT",
            "order_no": order.order_no,
            "qr_image_path": qr_path,
            "waiting": True,
        }

    async def _resolve_qr_path(self, order_no: str) -> str:
        """收银台二维码图片：若配置了测试图片且存在，直接使用；否则自动生成占位二维码。"""
        from app.config import settings

        test_img = (settings.TRAVEL_QR_TEST_IMAGE or "").strip()
        if test_img:
            candidate = test_img if os.path.isabs(test_img) else os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                test_img,
            )
            if os.path.exists(candidate):
                log.info("使用测试二维码图片: %s", candidate)
                return candidate
            log.warning("测试二维码图片不存在，回退自动生成: %s", candidate)
        return await self.qr_capture.capture(order_no=order_no)

    async def confirm_payment(
        self,
        db: AsyncSession,
        task_id: Optional[str],
        order: TravelOrderRow,
        push_success: bool = False,
    ) -> TravelOrderRow:
        """支付确认（三层检测任一命中后调用）：BOOKING → PAID，幂等防重复。"""
        if order.status == OrderStatus.PAID.value:
            return order
        await order_crud.update_order(db, order.id, status=OrderStatus.PAID.value)
        if task_id:
            await self.task_service.succeed(db, task_id, result={"order_no": order.order_no, "status": "PAID"}, notify=False)
        if push_success:
            await self.push_service.push(
                order.user_id,
                OutboundMessage(
                    kind="TEXT",
                    channel=order.channel,
                    text=f"✅ 订单 {order.order_no} 已支付出票（Mock 供应商·页面/轮询检测）。可回复“查订单”查看。",
                    correlation_id=task_id,
                ),
            )
        return order

    async def order_detail(self, db: AsyncSession, user_id: int, order_no: str) -> Optional[OrderDraftOut]:
        row = await order_crud.get_order_by_no(db, user_id, order_no)
        if not row:
            return None
        return self._to_out(row)

    async def list_orders(self, db: AsyncSession, user_id: int) -> List[OrderDraftOut]:
        rows = await order_crud.list_orders(db, user_id)
        return [self._to_out(r) for r in rows]

    async def execute_change(self, db: AsyncSession, task_id: str, order: TravelOrderRow, decision: ChangeDecision) -> TravelOrderRow:
        """改签执行（Mock）：CHANGING → CHANGED，订单 legs 更新为新方案。"""
        await order_crud.update_order(db, order.id, status=OrderStatus.CHANGING.value)
        await self.task_service.update_progress(db, task_id, 50, "正在执行改签…")
        recommended = decision.recommended
        new_leg = recommended.new_leg if recommended else None
        legs = order.legs or {"legs": []}
        if new_leg:
            legs["legs"] = [new_leg]
        await order_crud.update_order(
            db,
            order.id,
            status=OrderStatus.CHANGED.value,
            legs=legs,
            price=float(new_leg.get("price", order.price)) if new_leg else order.price,
        )
        await self.task_service.succeed(db, task_id, result={"order_no": order.order_no, "status": "CHANGED"})
        return order

    async def execute_refund(self, db: AsyncSession, task_id: str, order: TravelOrderRow) -> TravelOrderRow:
        """退票执行（Mock）：REFUNDING → REFUNDED。"""
        await order_crud.update_order(db, order.id, status=OrderStatus.REFUNDING.value)
        await self.task_service.update_progress(db, task_id, 50, "正在执行退票…")
        await order_crud.update_order(db, order.id, status=OrderStatus.REFUNDED.value)
        await self.task_service.succeed(db, task_id, result={"order_no": order.order_no, "status": "REFUNDED"})
        return order

    async def register_manual_order(
        self,
        db: AsyncSession,
        user_id: int,
        order_no: str,
        order_type: str = "FLIGHT",
        channel: str = "web",
    ) -> TravelOrderRow:
        """手动兜底：agent 看不到用户账号订单时，登记订单号 → travel_order。"""
        row = TravelOrderRow(
            user_id=user_id,
            order_no=order_no,
            supplier=Supplier.mock.value,
            type=order_type,
            status=OrderStatus.PAID.value,
            idempotency_key=hashlib.sha256(f"manual:{user_id}:{order_no}".encode()).hexdigest(),
            price=0,
            tax_fee=0,
            passengers={"list": []},
            legs={"legs": []},
            refund_rule={"kind": "MANUAL"},
            channel=channel,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    def _to_out(row: TravelOrderRow) -> OrderDraftOut:
        return OrderDraftOut(
            order_no=row.order_no,
            supplier=row.supplier,
            type=row.type,
            status=row.status,
            price=row.price,
            tax_fee=row.tax_fee,
            passengers=(row.passengers or {}).get("list", []),
            legs=(row.legs or {}).get("legs", []),
        )

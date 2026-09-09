import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TravelOrderRow
from app.models.enums import OrderStatus
from app.services.trace import active_trace_ctx
from app.services.trace_schema import EventType

log = logging.getLogger("travel.order_crud")


async def auto_complete_past_orders(db: AsyncSession, user_id: Optional[int] = None) -> int:
    """自动扫描并将已超过出行时间且未退票/未取消的有效订单流转至 COMPLETED（已出行）。"""
    from datetime import datetime
    from app.models.database import TravelTripRow

    now = datetime.now()

    query = select(TravelOrderRow).where(
        TravelOrderRow.status.in_([
            OrderStatus.PAID.value,
            OrderStatus.CHANGED.value,
            OrderStatus.CONFIRMED.value,
        ])
    )
    if user_id is not None:
        query = query.where(TravelOrderRow.user_id == user_id)

    res = await db.execute(query)
    orders = list(res.scalars().all())
    if not orders:
        return 0

    trip_ids = [o.trip_id for o in orders if o.trip_id]
    trip_map = {}
    if trip_ids:
        t_res = await db.execute(select(TravelTripRow).where(TravelTripRow.id.in_(trip_ids)))
        for t in t_res.scalars().all():
            trip_map[t.id] = t

    completed_count = 0
    for order in orders:
        trip = trip_map.get(order.trip_id)
        trip_date = trip.start_date if (trip and trip.start_date) else order.created_at.date()

        is_passed = False
        if trip_date < now.date():
            is_passed = True
        elif trip_date == now.date():
            legs = (order.legs or {}).get("legs", []) if isinstance(order.legs, dict) else []
            if legs and legs[-1].get("arrive"):
                try:
                    arr_str = str(legs[-1]["arrive"]).strip()
                    parts = arr_str.split(":", 1)
                    arr_time = datetime(now.year, now.month, now.day, int(parts[0]), int(parts[1]))
                    if now >= arr_time:
                        is_passed = True
                except Exception:
                    pass

        if is_passed:
            status_before = order.status
            order.status = OrderStatus.COMPLETED.value
            db.add(order)
            completed_count += 1
            log.info("订单 %s 出行时间(%s)已过，自动标记为已出行(COMPLETED)", order.order_no, trip_date)
            ctx = active_trace_ctx.get()
            if ctx:
                ctx.record_event(
                    EventType.ORDER_STATUS_CHANGED,
                    "ORDER",
                    {"orderNo": order.order_no, "statusBefore": status_before},
                    {"statusAfter": order.status, "reason": "TRIP_TIME_PASSED", "actor": "SYSTEM_SWEEP"},
                    state_before=status_before,
                    state_after=order.status,
                )

    if completed_count > 0:
        await db.commit()
    return completed_count


async def get_order_by_idempotency(db: AsyncSession, idempotency_key: str) -> Optional[TravelOrderRow]:
    res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.idempotency_key == idempotency_key))
    return res.scalars().first()


async def get_order_by_no(db: AsyncSession, user_id: int, order_no: str) -> Optional[TravelOrderRow]:
    await auto_complete_past_orders(db, user_id)
    res = await db.execute(
        select(TravelOrderRow).where(TravelOrderRow.order_no == order_no, TravelOrderRow.user_id == user_id)
    )
    return res.scalars().first()


async def get_order_by_id(db: AsyncSession, order_id: int) -> Optional[TravelOrderRow]:
    res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.id == order_id))
    return res.scalars().first()


async def list_orders(db: AsyncSession, user_id: int) -> List[TravelOrderRow]:
    await auto_complete_past_orders(db, user_id)
    res = await db.execute(
        select(TravelOrderRow).where(TravelOrderRow.user_id == user_id).order_by(TravelOrderRow.created_at.desc())
    )
    return list(res.scalars().all())


async def count_orders(db: AsyncSession, user_id: int, statuses: Optional[List[str]] = None) -> int:
    query = select(TravelOrderRow).where(TravelOrderRow.user_id == user_id)
    if statuses:
        query = query.where(TravelOrderRow.status.in_(statuses))
    res = await db.execute(query)
    return len(list(res.scalars().all()))


async def update_order(db: AsyncSession, order_id: int, **fields):
    res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.id == order_id))
    row = res.scalars().first()
    if not row:
        return None
    status_before = row.status

    # 状态机防倒退守卫：防止异步并发任务将终态逆向覆盖回初态
    new_status = fields.get("status")
    terminal_statuses = (
        OrderStatus.PAID.value,
        OrderStatus.REFUNDED.value,
        OrderStatus.REFUNDING.value,
        OrderStatus.CHANGED.value,
        OrderStatus.CHANGING.value,
        OrderStatus.COMPLETED.value,
        OrderStatus.CANCELLED.value,
    )
    initial_statuses = (
        OrderStatus.DRAFT.value,
        OrderStatus.CONFIRMED.value,
        OrderStatus.BOOKING.value,
    )
    if new_status and status_before in terminal_statuses and new_status in initial_statuses:
        log.warning(
            "订单 %s 状态已处于 %s，拒绝并发任务将其逆向回退至 %s",
            row.order_no, status_before, new_status,
        )
        fields.pop("status")

    # 内部参数：仅用于 Trace 归因，不落库（调用方可传 _actor/_reason）
    actor = fields.pop("_actor", None)
    reason = fields.pop("_reason", None)
    for k, v in fields.items():
        setattr(row, k, v)
    db.add(row)
    await db.commit()
    # Commit 4：订单状态机转移统一记录（后台任务/支付监控/改签退票均经此入口）
    if row.status != status_before:
        ctx = active_trace_ctx.get()
        if ctx:
            ctx.record_event(
                EventType.ORDER_STATUS_CHANGED,
                "ORDER",
                {"orderNo": row.order_no, "statusBefore": status_before},
                {"statusAfter": row.status, "reason": reason, "actor": actor},
                state_before=status_before,
                state_after=row.status,
            )
    return row

"""User L2 决策行为事件（分化方案 P1）。

记录"用户如何处理事情"（降价接受/忽略、改签/退票确认、推荐接受/拒绝、监控开关、提醒设置），
而不是旅行本身；供 Monitor/Change 等读取统计以提高推荐/提醒倾向，绝不自动执行资金操作。
"""
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserMemoryEventRow


class UserEventType:
    """User L2 事件类型（集中登记，写入/读取共用，禁止散落字符串）。"""
    PRICE_DROP_ACCEPTED = "price_drop_accepted"
    PRICE_DROP_IGNORED = "price_drop_ignored"
    CHANGE_CONFIRMED = "change_confirmed"
    CHANGE_REJECTED = "change_rejected"
    REFUND_CONFIRMED = "refund_confirmed"
    RECOMMEND_REJECTED = "recommend_rejected"
    RECOMMEND_ACCEPTED = "recommend_accepted"
    MONITOR_TOGGLED = "monitor_toggled"
    REMINDER_SET = "reminder_set"


async def record_user_event(
    db: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    order_no: Optional[str] = None,
    context: Optional[dict] = None,
    result: Optional[dict] = None,
) -> UserMemoryEventRow:
    """写入一条 User L2 事件（幂等不做去重，重复触发即重复行为记录）。"""
    row = UserMemoryEventRow(
        user_id=user_id,
        event_type=event_type,
        session_id=session_id,
        task_id=task_id,
        trace_id=trace_id,
        order_no=order_no,
        context=context or {},
        result=result or {},
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def recent_user_events(
    db: AsyncSession,
    user_id: int,
    event_types: Sequence[str],
    limit: int = 100,
) -> List[UserMemoryEventRow]:
    res = await db.execute(
        select(UserMemoryEventRow)
        .where(
            UserMemoryEventRow.user_id == user_id,
            UserMemoryEventRow.event_type.in_(list(event_types)),
        )
        .order_by(UserMemoryEventRow.id.desc())
        .limit(max(1, min(500, limit or 100)))
    )
    return list(res.scalars().all())


def summarize_price_events(rows: Sequence[UserMemoryEventRow]) -> dict:
    """价格行为统计：接受/忽略次数与接受率（供 Monitor 参考，不作为阈值本身）。"""
    accepted = sum(1 for r in rows if r.event_type == UserEventType.PRICE_DROP_ACCEPTED)
    ignored = sum(1 for r in rows if r.event_type == UserEventType.PRICE_DROP_IGNORED)
    total = accepted + ignored
    return {
        "accepted": accepted,
        "ignored": ignored,
        "total": total,
        "acceptRatio": round(accepted / total, 2) if total else None,
    }


def summarize_change_events(rows: Sequence[UserMemoryEventRow]) -> dict:
    """改签/退票行为统计（供 Change 推荐解释，不改变成本最优）。"""
    confirmed = sum(1 for r in rows if r.event_type == UserEventType.CHANGE_CONFIRMED)
    rejected = sum(1 for r in rows if r.event_type == UserEventType.CHANGE_REJECTED)
    refunded = sum(1 for r in rows if r.event_type == UserEventType.REFUND_CONFIRMED)
    recent = [
        {
            "eventType": r.event_type,
            "orderNo": r.order_no,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows[:5]
    ]
    return {"confirmed": confirmed, "rejected": rejected, "refunded": refunded, "recent": recent}

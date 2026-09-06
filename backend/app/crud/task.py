from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TravelTaskRow
from app.models.enums import TaskStatus, TaskType


async def create_task(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    task_type: str,
    params: dict,
    channel: str = "web",
    session_id: Optional[str] = None,
    order_id: Optional[int] = None,
) -> TravelTaskRow:
    row = TravelTaskRow(
        task_id=task_id,
        user_id=user_id,
        session_id=session_id,
        type=task_type,
        status=TaskStatus.PENDING.value,
        params=params,
        channel=channel,
        order_id=order_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_task(db: AsyncSession, task_id: str) -> Optional[TravelTaskRow]:
    res = await db.execute(select(TravelTaskRow).where(TravelTaskRow.task_id == task_id))
    return res.scalars().first()


async def update_task(db: AsyncSession, task_id: str, **fields):
    res = await db.execute(select(TravelTaskRow).where(TravelTaskRow.task_id == task_id))
    row = res.scalars().first()
    if not row:
        return None
    for k, v in fields.items():
        setattr(row, k, v)
    db.add(row)
    await db.commit()
    return row


async def list_tasks(
    db: AsyncSession,
    user_id: Optional[int] = None,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[TravelTaskRow]:
    query = select(TravelTaskRow)
    if user_id is not None:
        query = query.where(TravelTaskRow.user_id == user_id)
    if task_type:
        query = query.where(TravelTaskRow.type == task_type)
    if status:
        query = query.where(TravelTaskRow.status == status)
    res = await db.execute(query.order_by(TravelTaskRow.created_at.desc()))
    return list(res.scalars().all())


async def list_retryable(db: AsyncSession, limit: int = 20) -> List[TravelTaskRow]:
    """拉取到期的 RETRYING 任务（retry_worker 使用）。"""
    now = datetime.utcnow()
    res = await db.execute(
        select(TravelTaskRow)
        .where(TravelTaskRow.status == TaskStatus.RETRYING.value, TravelTaskRow.next_run_at <= now)
        .limit(limit)
    )
    return list(res.scalars().all())


async def reset_advisory_tasks(db: AsyncSession, order_id: Optional[int]) -> int:
    """把某订单已成功的提醒任务置为 FAILED，允许重新触发出发提醒（测试/重发用）。"""
    if order_id is None:
        return 0
    res = await db.execute(
        select(TravelTaskRow).where(
            TravelTaskRow.order_id == order_id,
            TravelTaskRow.type == TaskType.advisory.value,
            TravelTaskRow.status == TaskStatus.SUCCEEDED.value,
        )
    )
    rows = list(res.scalars().all())
    for row in rows:
        row.status = TaskStatus.FAILED.value
        db.add(row)
    if rows:
        await db.commit()
    return len(rows)

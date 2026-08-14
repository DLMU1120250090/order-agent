from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TravelOrderRow


async def get_order_by_idempotency(db: AsyncSession, idempotency_key: str) -> Optional[TravelOrderRow]:
    res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.idempotency_key == idempotency_key))
    return res.scalars().first()


async def get_order_by_no(db: AsyncSession, user_id: int, order_no: str) -> Optional[TravelOrderRow]:
    res = await db.execute(
        select(TravelOrderRow).where(TravelOrderRow.order_no == order_no, TravelOrderRow.user_id == user_id)
    )
    return res.scalars().first()


async def get_order_by_id(db: AsyncSession, order_id: int) -> Optional[TravelOrderRow]:
    res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.id == order_id))
    return res.scalars().first()


async def list_orders(db: AsyncSession, user_id: int) -> List[TravelOrderRow]:
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
    for k, v in fields.items():
        setattr(row, k, v)
    db.add(row)
    await db.commit()
    return row

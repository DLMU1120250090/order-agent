from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import DataCacheRow


async def cache_get(db: AsyncSession, cache_key: str) -> Optional[Any]:
    res = await db.execute(select(DataCacheRow).where(DataCacheRow.cache_key == cache_key))
    row = res.scalars().first()
    if row and row.expire_at and row.expire_at > datetime.utcnow():
        return row.payload
    return None


async def cache_put(db: AsyncSession, cache_key: str, payload: Any, ttl_seconds: int = 300):
    res = await db.execute(select(DataCacheRow).where(DataCacheRow.cache_key == cache_key))
    row = res.scalars().first()
    if not row:
        row = DataCacheRow(cache_key=cache_key)
        db.add(row)
    row.payload = payload
    row.expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    await db.commit()

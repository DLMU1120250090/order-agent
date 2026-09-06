from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import PoiStationRow


async def get_stations(db: AsyncSession, city: str, kind: Optional[str] = None) -> List[PoiStationRow]:
    query = select(PoiStationRow).where(PoiStationRow.city == city)
    if kind:
        query = query.where(PoiStationRow.kind == kind)
    res = await db.execute(query)
    return list(res.scalars().all())

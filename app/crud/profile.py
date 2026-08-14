from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserProfileRow
from app.models.schemas import UserProfile


async def get_profile(db: AsyncSession, user_id: int) -> Optional[UserProfile]:
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == user_id))
    row = res.scalars().first()
    if not row:
        return None
    return UserProfile(
        user_id=row.user_id,
        home_city=row.home_city,
        passengers=row.passengers or [],
        budget_level=row.budget_level,
        preferences=row.preferences or {},
    )


async def update_profile(db: AsyncSession, user_id: int, **fields):
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == user_id))
    row = res.scalars().first()
    if not row:
        row = UserProfileRow(user_id=user_id)
        db.add(row)
    if "home_city" in fields:
        row.home_city = fields["home_city"]
    if "passengers" in fields:
        row.passengers = fields["passengers"]
    if "budget_level" in fields:
        row.budget_level = fields["budget_level"]
    if "preferences" in fields:
        prefs = dict(row.preferences or {})
        prefs.update(fields["preferences"])
        row.preferences = prefs
    await db.commit()
    return await get_profile(db, user_id)

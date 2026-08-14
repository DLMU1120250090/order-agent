from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserChannelBindingRow


async def find_user_id(db: AsyncSession, channel: str, channel_user_id: str) -> Optional[int]:
    res = await db.execute(
        select(UserChannelBindingRow).where(
            UserChannelBindingRow.channel == channel,
            UserChannelBindingRow.channel_user_id == channel_user_id,
        )
    )
    row = res.scalars().first()
    return row.user_id if row else None


async def bind_user(db: AsyncSession, user_id: int, channel: str, channel_user_id: str):
    res = await db.execute(
        select(UserChannelBindingRow).where(
            UserChannelBindingRow.channel == channel,
            UserChannelBindingRow.channel_user_id == channel_user_id,
        )
    )
    row = res.scalars().first()
    if row:
        row.user_id = user_id
    else:
        row = UserChannelBindingRow(user_id=user_id, channel=channel, channel_user_id=channel_user_id)
        db.add(row)
    await db.commit()


async def find_channel_user_id(db: AsyncSession, user_id: int, channel: str) -> Optional[str]:
    """反向查询：系统 userId + 通道 -> 通道内用户标识（如钉钉 senderStaffId）。"""
    res = await db.execute(
        select(UserChannelBindingRow).where(
            UserChannelBindingRow.user_id == user_id,
            UserChannelBindingRow.channel == channel,
        ).order_by(UserChannelBindingRow.id.desc())
    )
    row = res.scalars().first()
    return row.channel_user_id if row else None

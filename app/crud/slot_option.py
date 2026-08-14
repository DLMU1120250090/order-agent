from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.database import SlotOptionRow
from app.models.schemas import TravelSlotBundle


TRAVEL_SLOT_NAMES = ["origin", "destination", "tripDate", "budget", "travelStyle", "transportMode", "companion"]
# tripDate 为自由值，不走字典白名单
WHITELIST_SLOT_NAMES = ["origin", "destination", "budget", "travelStyle", "transportMode", "companion"]


async def find_all_slot_options(db: AsyncSession) -> Dict[str, List[str]]:
    """从字典表（diet_slot_option）拉取出行槽位的合法备选词表。"""
    result = await db.execute(
        select(SlotOptionRow)
        .where(SlotOptionRow.enabled == 1)
        .order_by(SlotOptionRow.sort_order.asc())
    )
    rows = result.scalars().all()
    options = {name: [] for name in TRAVEL_SLOT_NAMES}
    for row in rows:
        if row.slot_name in options:
            options[row.slot_name].append(row.option_value)
    return options


async def validate_slots(db: AsyncSession, slots: TravelSlotBundle):
    """防注入/防脏数据：字典槽位白名单校验（tripDate 自由值跳过）。"""
    options = await find_all_slot_options(db)
    slot_dict = slots.model_dump()
    for name in WHITELIST_SLOT_NAMES:
        values = slot_dict.get(name) or []
        allowed = set(options.get(name) or [])
        for val in values:
            if val not in allowed:
                raise HTTPException(status_code=400, detail=f"非法槽位标签: {name}={val}")

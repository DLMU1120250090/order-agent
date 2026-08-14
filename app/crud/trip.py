from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TravelTripRow, TravelPlanRow
from app.models.schemas import PlanOption, TravelSlotBundle


async def create_or_get_trip(
    db: AsyncSession,
    user_id: int,
    slots: TravelSlotBundle,
) -> TravelTripRow:
    """按目的地+日期幂等创建行程主表记录。"""
    destination = (slots.destination or ["未知"])[0]
    dates = slots.tripDate or []
    start_date = dates[0] if dates else None
    end_date = dates[1] if len(dates) > 1 else start_date
    budget = (slots.budget or [None])[0]

    res = await db.execute(
        select(TravelTripRow).where(
            TravelTripRow.user_id == user_id,
            TravelTripRow.destination == destination,
            TravelTripRow.start_date == start_date,
            TravelTripRow.status == "PLANNING",
        ).order_by(TravelTripRow.id.desc()).limit(1)
    )
    row = res.scalars().first()
    if row:
        return row

    row = TravelTripRow(
        user_id=user_id,
        destination=destination,
        start_date=start_date,
        end_date=end_date,
        budget=budget,
        status="PLANNING",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def save_plan(db: AsyncSession, trip_id: Optional[int], option: PlanOption) -> int:
    """落库一个候选方案，返回 plan_id。"""
    row = TravelPlanRow(
        trip_id=trip_id,
        score=option.score,
        plan_json=option.model_dump(),
        budget_deviation=option.budget_deviation,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row.id


async def get_plan(db: AsyncSession, plan_id: int) -> Optional[TravelPlanRow]:
    res = await db.execute(select(TravelPlanRow).where(TravelPlanRow.id == plan_id))
    return res.scalars().first()


async def get_trip(db: AsyncSession, trip_id: Optional[int]) -> Optional[TravelTripRow]:
    """按行程主表 id 查询（订单关联 trip_id 取出行日期等）。"""
    if trip_id is None:
        return None
    res = await db.execute(select(TravelTripRow).where(TravelTripRow.id == trip_id))
    return res.scalars().first()


async def list_plans(db: AsyncSession, trip_id: Optional[int]) -> List[TravelPlanRow]:
    if trip_id is None:
        return []
    res = await db.execute(
        select(TravelPlanRow).where(TravelPlanRow.trip_id == trip_id).order_by(TravelPlanRow.created_at.desc())
    )
    return list(res.scalars().all())


async def update_trip_status(db: AsyncSession, trip_id: int, status: str):
    res = await db.execute(select(TravelTripRow).where(TravelTripRow.id == trip_id))
    row = res.scalars().first()
    if row:
        row.status = status
        db.add(row)
        await db.commit()

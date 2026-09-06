"""Commit 1 存量回填（幂等，可重复执行）：
1) user_profile.passengers 补 passenger_id / role；
2) trip_summary.episode_json IS NULL 时，从关联订单/行程生成基础 Episode。

运行：cd order-agent && python sql/backfills/backfill_memory_v1.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402

from app.crud.profile import normalize_passengers  # noqa: E402
from app.database import async_session_maker, engine  # noqa: E402
from app.models.database import (  # noqa: E402
    TravelOrderRow,
    TravelTripRow,
    TripSummaryRow,
    UserProfileRow,
)
from app.models.enums import OrderStatus  # noqa: E402


async def backfill_passengers(db) -> int:
    res = await db.execute(select(UserProfileRow))
    updated = 0
    for row in res.scalars().all():
        if not row.passengers:
            continue
        normalized = normalize_passengers(row.passengers)
        if normalized != row.passengers:
            row.passengers = normalized
            updated += 1
    return updated


def _episode_from_order(summary, order, trip) -> dict:
    legs = (order.legs or {}).get("legs", []) if order else []
    first = legs[0] if legs else {}
    last = legs[-1] if legs else {}
    passengers = (order.passengers or {}).get("list", []) if order else []
    return {
        "trip_id": summary.trip_id,
        "user_id": summary.user_id,
        "passengers": [
            p.get("passenger_id") or p.get("id_no") or p.get("name")
            for p in passengers
        ],
        "context": {
            "origin": first.get("from_city"),
            "destination": last.get("to_city") or (trip.destination if trip else None),
            "purpose": None,
        },
        "constraints": {},
        "selected_plan": {
            "mode": first.get("mode"),
            "vehicle_no": first.get("vehicle_no", ""),
            "depart": first.get("depart"),
            "price": order.price if order else None,
            "order_no": order.order_no if order else None,
        },
        "decision_reason": [],
        "outcome": {
            "booking_success": bool(order and order.status == OrderStatus.PAID.value),
            "rating": None,
        },
        "trace_refs": [],
    }


async def backfill_episodes(db) -> int:
    res = await db.execute(select(TripSummaryRow).where(TripSummaryRow.episode_json.is_(None)))
    rows = list(res.scalars().all())
    updated = 0
    for summary in rows:
        order = None
        trip = None
        if summary.trip_id:
            o_res = await db.execute(
                select(TravelOrderRow)
                .where(
                    TravelOrderRow.trip_id == summary.trip_id,
                    TravelOrderRow.user_id == summary.user_id,
                )
                .order_by(TravelOrderRow.created_at.desc())
                .limit(1)
            )
            order = o_res.scalars().first()
            t_res = await db.execute(select(TravelTripRow).where(TravelTripRow.id == summary.trip_id))
            trip = t_res.scalars().first()
        summary.episode_json = _episode_from_order(summary, order, trip)
        updated += 1
    return updated


async def main() -> None:
    try:
        async with async_session_maker() as db:
            passengers_updated = await backfill_passengers(db)
            await db.commit()
            episodes_updated = await backfill_episodes(db)
            await db.commit()
        print(f"passengers normalized: {passengers_updated}; episodes backfilled: {episodes_updated}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

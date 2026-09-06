"""分化方案 A1 迁移回填（2026-09-06，幂等）：
1) user_profile.passengers：本人归一为 passenger_id="0" / role=self；companion→others；多乘客不猜本人；
2) trip_summary.episode_json.passengers：引用统一为 passenger_id（本人="0"，其余保留 P_ id）。

运行：cd order-agent && python sql/backfills/backfill_memory_scope_id0.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import select  # noqa: E402

from app.crud.profile import normalize_passengers  # noqa: E402
from app.database import async_session_maker, engine  # noqa: E402
from app.models.database import TripSummaryRow, UserProfileRow  # noqa: E402


def _passenger_lookup(profile) -> dict:
    """构建 证件号/姓名 → passenger_id 映射（本人也映射到 "0"）。"""
    lookup = {}
    for p in profile.passengers or []:
        pid = str(p.get("passenger_id") or "")
        if p.get("id_no"):
            lookup[str(p["id_no"])] = pid
        if p.get("name"):
            lookup.setdefault(str(p["name"]), pid)
    return lookup


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


async def backfill_episode_refs(db) -> int:
    rows = (await db.execute(select(TripSummaryRow).where(TripSummaryRow.episode_json.is_not(None)))).scalars().all()
    profiles = {
        p.user_id: p
        for p in (await db.execute(select(UserProfileRow))).scalars().all()
    }
    updated = 0
    for row in rows:
        ep = row.episode_json or {}
        refs = ep.get("passengers") or []
        if not isinstance(refs, list):
            continue
        profile = profiles.get(row.user_id)
        lookup = _passenger_lookup(profile) if profile else {}
        new_refs = []
        changed = False
        for ref in refs:
            ref_str = str(ref)
            if ref_str in ("0",) or ref_str.startswith("P_"):
                new_refs.append(ref_str)
                continue
            mapped = lookup.get(ref_str)
            if mapped:
                new_refs.append(str(mapped))
                changed = changed or mapped != ref_str
            else:
                new_refs.append(ref_str)
        if changed:
            ep = dict(ep)
            ep["passengers"] = new_refs
            row.episode_json = ep
            updated += 1
    return updated


async def main() -> None:
    async with async_session_maker() as db:
        p = await backfill_passengers(db)
        await db.commit()
        e = await backfill_episode_refs(db)
        await db.commit()
    print(f"passengers_normalized={p}; episode_refs_unified={e}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

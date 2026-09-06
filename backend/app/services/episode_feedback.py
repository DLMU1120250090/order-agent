"""出行后评分最小入口（Commit 5，R2）：把 1~5 星评分落到 Passenger L2 Episode 的 outcome。

复用 FeedbackRow.rating(1-5) 语义；不改推荐反馈链路。
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import FeedbackRow, TripSummaryRow


def apply_post_trip_rating(episode: dict, rating: int, reason: Optional[str] = None) -> dict:
    """返回更新后的 episode_json：outcome.rating + 可选 outcome.feedback。"""
    ep = dict(episode or {})
    outcome = dict(ep.get("outcome") or {})
    outcome["rating"] = int(rating)
    if reason:
        outcome["feedback"] = str(reason)[:200]
    ep["outcome"] = outcome
    return ep


async def find_episode_by_order_no(
    db: AsyncSession, user_id: int, order_no: str,
) -> Optional[TripSummaryRow]:
    rows = (await db.execute(
        select(TripSummaryRow).where(TripSummaryRow.user_id == user_id)
    )).scalars().all()
    for row in rows:
        ep = row.episode_json or {}
        if (ep.get("selected_plan") or {}).get("order_no") == order_no:
            return row
    return None


async def apply_post_trip(
    db: AsyncSession,
    *,
    user_id: int,
    order_no: str,
    session_id: str,
    rating: int,
    reason: Optional[str] = None,
) -> Optional[TripSummaryRow]:
    """为订单对应的 Episode 落评分；找不到 Episode 返回 None。"""
    row = await find_episode_by_order_no(db, user_id, order_no)
    if not row:
        return None
    row.episode_json = apply_post_trip_rating(row.episode_json or {}, rating, reason)
    db.add(row)
    db.add(FeedbackRow(
        user_id=user_id,
        session_id=session_id,
        action="POST_TRIP",
        rating=max(1, min(5, int(rating))),
        reason=(reason or "出行后评分")[:512],
    ))
    await db.commit()
    await db.refresh(row)
    return row

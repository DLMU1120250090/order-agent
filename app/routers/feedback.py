from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.database import FeedbackRow, RequestTraceRow
from app.models.schemas import FeedbackRequest
from app.services.runtime import memory

router = APIRouter(prefix="/api/v1/travel/feedback", tags=["travel-feedback"])


@router.post("")
async def save(
    request: FeedbackRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """提交方案反馈：LIKE/DISLIKE/SWITCH → 评估闭环 + L1 偏好微调。"""
    if not request.sessionId or not request.sessionId.strip():
        raise HTTPException(status_code=400, detail="反馈 sessionId 不能为空")
    if not request.action or not request.action.strip():
        raise HTTPException(status_code=400, detail="action 不能为空")

    # Commit 9：反馈归因到 Trace（前端带 traceId 直接用；没有则按 session 最近一条兜底）
    trace_id = request.traceId
    if not trace_id:
        res = await db.execute(
            select(RequestTraceRow)
            .where(
                RequestTraceRow.session_id == request.sessionId,
                RequestTraceRow.user_id == x_user_id,
            )
            .order_by(desc(RequestTraceRow.created_at))
            .limit(1)
        )
        row = res.scalars().first()
        trace_id = row.trace_id if row else None

    fb = FeedbackRow(
        user_id=x_user_id,
        session_id=request.sessionId,
        item_id=request.itemId,
        plan_id=request.planId,
        trace_id=trace_id,
        action=request.action,
        rating=request.rating,
        reason=request.reason,
    )
    db.add(fb)
    await db.commit()

    # L1 偏好微调（规则确定性写入）
    profile = await memory.get_profile(db, x_user_id)
    prefs = dict(profile.preferences) if profile and profile.preferences else {}
    action = request.action.upper()
    if action in ("LIKE", "ADOPT", "ACCEPT"):
        prefs["positive_feedback"] = int(prefs.get("positive_feedback", 0)) + 1
    elif action in ("DISLIKE", "REJECT"):
        prefs["negative_feedback"] = int(prefs.get("negative_feedback", 0)) + 1
    elif action in ("SWITCH", "REFRESH"):
        prefs["switch_count"] = int(prefs.get("switch_count", 0)) + 1
    await memory.update_profile(db, x_user_id, preferences=prefs)
    return {"status": "success"}

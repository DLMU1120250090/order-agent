import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evaluation import EvaluationJudgeAgent
from app.database import get_db
from app.models.database import RequestTraceRow
from app.models.schemas import (
    EvaluationReport, EvaluationRequest, TraceLabelRequest, TraceRowOut,
)
from app.services.evaluation import EvaluationService

router = APIRouter(tags=["travel-evaluation-debug"])

judge_agent = EvaluationJudgeAgent()
evaluation_service = EvaluationService(judge_agent)


def to_trace_row_out(row: RequestTraceRow) -> TraceRowOut:
    return TraceRowOut(
        traceId=row.trace_id,
        sessionId=row.session_id,
        userId=row.user_id,
        status=row.status,
        eventCount=row.event_count,
        durationMs=row.duration_ms,
        errorMessage=row.error_message,
        traceJson=row.trace_json,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
        expectedIntent=row.expected_intent,
        expectedSlots=row.expected_slots,
        expectedClarifyAction=row.expected_clarify_action,
        labeledBy=row.labeled_by,
        labeledAt=row.labeled_at,
        labelNote=row.label_note,
    )


@router.post("/api/v1/travel/evaluations", response_model=EvaluationReport)
async def evaluate(
    request: EvaluationRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    return await evaluation_service.evaluate(db, x_user_id, request)


@router.get("/api/v1/travel/debug/traces/{traceId}", response_model=TraceRowOut)
async def find_by_trace_id(
    traceId: str = Path(...),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RequestTraceRow).where(
            RequestTraceRow.trace_id == traceId,
            RequestTraceRow.user_id == x_user_id,
        )
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace not found")
    return to_trace_row_out(row)


@router.get("/api/v1/travel/debug/sessions/{sessionId}/traces", response_model=List[TraceRowOut])
async def find_by_session_id(
    sessionId: str = Path(...),
    limit: Optional[int] = Query(default=200),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    safe_limit = max(1, min(1000, limit or 200))
    result = await db.execute(
        select(RequestTraceRow)
        .where(RequestTraceRow.session_id == sessionId, RequestTraceRow.user_id == x_user_id)
        .order_by(desc(RequestTraceRow.created_at))
        .limit(safe_limit)
    )
    return [to_trace_row_out(r) for r in result.scalars().all()]


@router.get("/api/v1/travel/debug/traces", response_model=List[TraceRowOut])
async def find_by_time_range(
    startAt: datetime = Query(...),
    endAt: datetime = Query(...),
    onlyUnlabeled: Optional[bool] = Query(default=False),
    limit: Optional[int] = Query(default=200),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    if startAt >= endAt:
        raise HTTPException(status_code=400, detail="Trace 查询时间范围不合法")
    safe_limit = max(1, min(1000, limit or 200))
    query = select(RequestTraceRow).where(
        RequestTraceRow.user_id == x_user_id,
        RequestTraceRow.created_at >= startAt,
        RequestTraceRow.created_at < endAt,
    )
    if onlyUnlabeled:
        query = query.where(
            RequestTraceRow.expected_intent == None,  # noqa: E711
            RequestTraceRow.expected_slots == None,  # noqa: E711
            RequestTraceRow.expected_clarify_action == None,  # noqa: E711
        )
    result = await db.execute(query.order_by(desc(RequestTraceRow.created_at)).limit(safe_limit))
    return [to_trace_row_out(r) for r in result.scalars().all()]


@router.put("/api/v1/travel/debug/traces/{traceId}/label")
async def update_label(
    traceId: str = Path(...),
    request: TraceLabelRequest = None,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    if not traceId or not traceId.strip():
        raise HTTPException(status_code=400, detail="traceId 不能为空")
    if not request:
        raise HTTPException(status_code=400, detail="标注内容不能为空")
    result = await db.execute(
        select(RequestTraceRow).where(
            RequestTraceRow.trace_id == traceId,
            RequestTraceRow.user_id == x_user_id,
        )
    )
    row = result.scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Trace 不存在或无权限标注")
    row.expected_intent = request.expectedIntent.value if request.expectedIntent else None
    row.expected_slots = json.dumps(request.expectedSlots.model_dump(), ensure_ascii=False) if request.expectedSlots else None
    row.expected_clarify_action = request.expectedClarifyAction.value if request.expectedClarifyAction else None
    row.labeled_by = x_user_id
    row.labeled_at = datetime.utcnow()
    row.label_note = request.labelNote
    row.updated_at = datetime.utcnow()
    db.add(row)
    await db.commit()
    return {"status": "success"}

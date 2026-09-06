from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.runtime import push_service

router = APIRouter(tags=["travel-events"])


@router.get("/api/v1/travel/events")
async def events(userId: int = Query(default=1, description="用户ID")):
    """Web SSE 长连接：异步进度/二维码/降价主动推送。"""
    return StreamingResponse(
        push_service.hub.stream(userId),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

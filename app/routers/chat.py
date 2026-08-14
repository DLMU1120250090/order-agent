from fastapi import APIRouter, Header, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import (
    InboundMessage, OutboundMessage, TravelChatRequest, TravelChatResponse,
)
from app.services.runtime import channel_manager

router = APIRouter(tags=["travel-chat"])


def _to_chat_response(msg: OutboundMessage, session_id: str) -> TravelChatResponse:
    resp_type = {"CLARIFY": "CLARIFY", "TASK_PROGRESS": "TASK_PROGRESS"}.get(msg.kind, "ANSWER")
    return TravelChatResponse(
        sessionId=msg.session_id or session_id,
        responseType=resp_type,
        speechText=msg.text,
        displayBlocks=msg.blocks,
        nextAction="ASK_CLARIFY" if resp_type == "CLARIFY" else "WAIT_USER",
        clarifyQuestion=msg.text if resp_type == "CLARIFY" else None,
        missingSlots=[],
        taskId=msg.task_progress.get("taskId") if msg.task_progress else None,
        orderNo=msg.correlation_id if msg.correlation_id and msg.correlation_id.startswith("ORD") else None,
    )


@router.post("/api/v1/travel/chat", response_model=TravelChatResponse)
async def chat(
    request: TravelChatRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """Web 通道对话接口（A2：同步问答 + 异步 SSE 推送）"""
    inbound = InboundMessage(
        channel="web",
        channel_user_id=str(x_user_id),
        user_id=x_user_id,
        session_key=request.sessionId or f"web:{x_user_id}",
        text=request.message,
    )
    msg = await channel_manager.dispatch(db, inbound)
    if msg is None:
        msg = OutboundMessage(channel="web", text="服务暂不可用")
    return _to_chat_response(msg, request.sessionId or f"web:{x_user_id}")


# 兼容旧前端路径 /api/v1/diet/chat
@router.post("/api/v1/diet/chat", response_model=TravelChatResponse)
async def chat_legacy(
    request: TravelChatRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    return await chat(request, x_user_id, db)

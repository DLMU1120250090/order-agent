from fastapi import APIRouter, Header, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.session import create_session, recent_conversation_turns, latest_session_id
from app.database import get_db
from app.models.enums import Channel
from app.models.schemas import CreateSessionResponse

router = APIRouter(prefix="/api/v1/travel/sessions", tags=["travel-sessions"])


@router.post("", response_model=CreateSessionResponse)
async def create(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    session_id = await create_session(db, x_user_id, Channel.web)
    return CreateSessionResponse(sessionId=session_id)


@router.get("/latest")
async def latest(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """返回该用户最近有消息的 Web 会话，供刷新后恢复上一次对话。"""
    session_id = await latest_session_id(db, x_user_id)
    return {"sessionId": session_id or ""}


@router.get("/{sessionId}/messages")
async def messages(
    sessionId: str,
    limit: int = Query(default=50, ge=1, le=200),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """读取会话历史消息（用户/助手），供 Web 刷新后恢复对话上下文。"""
    return await recent_conversation_turns(db, sessionId, x_user_id, n=limit, max_turns=limit)

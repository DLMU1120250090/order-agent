from fastapi import APIRouter, Header, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.session import (
    create_session,
    recent_conversation_turns,
    latest_session_id,
    list_user_sessions,
    delete_session,
    update_session_title,
)
from app.database import get_db
from app.models.enums import Channel
from app.models.schemas import CreateSessionResponse

router = APIRouter(prefix="/api/v1/travel/sessions", tags=["travel-sessions"])


class SessionTitleUpdateRequest(BaseModel):
    title: str


@router.post("", response_model=CreateSessionResponse)
async def create(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    session_id = await create_session(db, x_user_id, Channel.web)
    return CreateSessionResponse(sessionId=session_id)


@router.get("")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """获取该用户的历史会话列表，用于侧边栏渲染。"""
    return await list_user_sessions(db, x_user_id, limit=limit)


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


@router.delete("/{sessionId}")
async def delete_user_session(
    sessionId: str,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """删除指定的历史会话。"""
    ok = await delete_session(db, sessionId, x_user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权限删除")
    return {"ok": True, "sessionId": sessionId}


@router.put("/{sessionId}")
async def update_session(
    sessionId: str,
    body: SessionTitleUpdateRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """修改会话自定义标题。"""
    ok = await update_session_title(db, sessionId, x_user_id, body.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在或无权限修改")
    return {"ok": True, "sessionId": sessionId, "title": body.title}

"""微信 Mock 桥：HTTP Webhook 模拟微信消息入站，出站消息记录到 outbox 供测试查看。
真实 Wechaty 桥接入后，把这里的消息来源替换为 Wechaty 事件回调即可。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.wechat import wechat_channel
from app.database import get_db
from app.services.runtime import channel_manager

router = APIRouter(tags=["travel-webhook-wechat"])


@router.post("/api/v1/travel/webhook/wechat")
async def wechat_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """模拟微信好友/群消息：{from: 'wx_xxx', text: '...'} → 走统一分发。"""
    try:
        raw = await request.json()
    except Exception:  # noqa: BLE001
        raw = {}
    if not raw.get("text"):
        return {"status": "ok", "reply": ""}
    inbound = wechat_channel.to_inbound(raw)
    msg = await channel_manager.dispatch(db, inbound)
    return {
        "status": "ok",
        "from": inbound.channel_user_id,
        "reply": msg.text if msg else "",
        "outbox_count": wechat_channel.outbox_count(inbound.channel_user_id),
    }


@router.get("/api/v1/travel/debug/wechat/messages")
async def wechat_outbox(
    from_id: Optional[str] = None,
    limit: int = 50,
):
    """查看微信通道出站消息（Mock 测试用）。"""
    rows = wechat_channel.list_outbox(from_id=from_id, limit=limit)
    return {"count": len(rows), "messages": rows}

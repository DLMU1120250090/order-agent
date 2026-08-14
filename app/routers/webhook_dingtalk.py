from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.dingtalk import dingtalk_channel
from app.database import get_db
from app.services.runtime import channel_manager

router = APIRouter(tags=["travel-webhook-dingtalk"])


@router.post("/api/v1/travel/webhook/dingtalk")
async def dingtalk_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """钉钉机器人回调（当前 Mock：解析入站消息并走统一分发）。"""
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    inbound = dingtalk_channel.to_inbound(raw)
    await channel_manager.dispatch(db, inbound)
    return {"status": "ok"}

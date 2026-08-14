import logging

from app.channels.base import ChannelAdapter
from app.models.schemas import InboundMessage, OutboundMessage
from app.services.push import SseHub

log = logging.getLogger("travel.channel.web")


class WebChannel(ChannelAdapter):
    """
    Web 通道：HTTP 同步问答 + SSE 异步推送（A2 定稿）。
    - POST /api/v1/travel/chat 入站（HTTP 响应即同步回复）
    - GET /api/v1/travel/events?userId= SSE 长连接（异步进度/二维码/降价）
    """

    channel_name = "web"

    def __init__(self, hub: SseHub):
        self.hub = hub

    async def send(self, msg: OutboundMessage) -> bool:
        try:
            user_id = int(msg.channel_user_id or "0")
        except (TypeError, ValueError):
            user_id = 0
        event = {
            "kind": msg.kind,
            "text": msg.text,
            "blocks": msg.blocks,
            "imagePath": msg.image_path,
            "taskProgress": msg.task_progress,
            "correlationId": msg.correlation_id,
        }
        # 同步回复已通过 HTTP 响应返回；SSE 只推异步事件，避免前端出现两条回答
        if user_id and not msg.sync_reply:
            self.hub.publish(user_id, event)
        return True

    def to_inbound(self, raw: dict) -> InboundMessage:
        return InboundMessage(
            channel="web",
            channel_user_id=str(raw.get("userId", "1")),
            user_id=int(raw.get("userId", 1)),
            session_key=raw.get("sessionId") or f"web:{raw.get('userId', '1')}",
            text=raw.get("message", ""),
            attachments=raw.get("attachments", []),
        )

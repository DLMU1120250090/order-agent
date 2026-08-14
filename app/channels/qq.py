import logging

from app.channels.base import ChannelAdapter
from app.models.schemas import InboundMessage, OutboundMessage

log = logging.getLogger("travel.channel.qq")


class QQChannel(ChannelAdapter):
    """QQ 通道（官方机器人回调 / Napcat OneBot，可选）。"""

    channel_name = "qq"

    async def send(self, msg: OutboundMessage) -> bool:
        log.info("[QQ->%s] %s %s", msg.channel_user_id, msg.kind, msg.text[:200])
        return True

    def to_inbound(self, raw: dict) -> InboundMessage:
        return InboundMessage(
            channel="qq",
            channel_user_id=str(raw.get("user_id", "qq_unknown")),
            session_key=f"qq:{raw.get('user_id', 'qq_unknown')}",
            text=raw.get("raw_message", ""),
        )

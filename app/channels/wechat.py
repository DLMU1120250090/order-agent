import logging
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from app.channels.base import ChannelAdapter
from app.models.schemas import InboundMessage, OutboundMessage

log = logging.getLogger("travel.channel.wechat")


class WeChatChannel(ChannelAdapter):
    """微信通道（Mock 桥）。
    入站：HTTP Webhook（/api/v1/travel/webhook/wechat）模拟微信消息；
    出站：记录到内存 outbox（按 channel_user_id），供调试接口查看；
    真实 Wechaty 桥接入后，把 to_inbound 的来源换成 Wechaty 事件、send 换成 contact.say() 即可。
    """

    channel_name = "wechat"

    def __init__(self, max_outbox: int = 200):
        self._lock = threading.Lock()
        self._outbox: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=max_outbox))

    async def send(self, msg: OutboundMessage) -> bool:
        entry = {
            "channel": msg.channel,
            "to": msg.channel_user_id,
            "kind": msg.kind,
            "text": (msg.text or "")[:2000],
            "blocks": msg.blocks,
            "image_path": msg.image_path,
            "correlation_id": msg.correlation_id,
        }
        with self._lock:
            self._outbox[msg.channel_user_id].append(entry)
        log.info("[WeChat->%s] %s %s", msg.channel_user_id, msg.kind, msg.text[:200])
        return True

    def to_inbound(self, raw: dict) -> InboundMessage:
        return InboundMessage(
            channel="wechat",
            channel_user_id=str(raw.get("from", "wx_unknown")),
            session_key=f"wechat:{raw.get('from', 'wx_unknown')}",
            text=raw.get("text", ""),
        )

    def outbox_count(self, channel_user_id: str) -> int:
        with self._lock:
            return len(self._outbox.get(channel_user_id, ()))

    def list_outbox(self, from_id: Optional[str] = None, limit: int = 50) -> List[dict]:
        with self._lock:
            if from_id:
                rows = list(self._outbox.get(from_id, ()))
            else:
                rows = [e for q in self._outbox.values() for e in q]
        rows.reverse()
        return rows[: max(1, min(limit, 200))]


wechat_channel = WeChatChannel()

import json
import logging
import os
import threading
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from app.channels.base import ChannelAdapter
from app.models.schemas import InboundMessage, OutboundMessage

log = logging.getLogger("travel.channel.wechat")


class WeChatChannel(ChannelAdapter):
    """微信通道（Mock 桥）。
    入站：HTTP Webhook（/api/v1/travel/webhook/wechat）模拟微信消息；
    出站：记录到内存 outbox（按 channel_user_id）+ 持久化 memory/wechat_outbox.jsonl，
          重启不丢消息，供调试接口查看；
    真实 Wechaty 桥接入后，把 to_inbound 的来源换成 Wechaty 事件、send 换成 contact.say() 即可。
    """

    channel_name = "wechat"

    def __init__(self, max_outbox: int = 200, outbox_path: str = ""):
        self._lock = threading.Lock()
        self._outbox: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=max_outbox))
        if not outbox_path:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            outbox_path = os.path.join(project_dir, "memory", "wechat_outbox.jsonl")
        self._outbox_path = outbox_path
        os.makedirs(os.path.dirname(self._outbox_path), exist_ok=True)
        self._load_outbox()

    def _load_outbox(self):
        """启动时加载历史 outbox（重启不丢消息）。"""
        try:
            with open(self._outbox_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._outbox[str(entry.get("to", "wx_unknown"))].append(entry)
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            log.warning("微信 outbox 加载失败: %s", e)

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
            try:
                with open(self._outbox_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception as e:  # noqa: BLE001
                log.warning("微信 outbox 持久化失败: %s", e)
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

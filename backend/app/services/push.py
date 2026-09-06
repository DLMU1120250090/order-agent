import asyncio
import json
import logging
from collections import defaultdict
from typing import Dict, Optional

from app.crud import binding as binding_crud
from app.database import async_session_maker
from app.models.schemas import InboundMessage, OutboundMessage

log = logging.getLogger("travel.push")


class SseHub:
    """
    Web 通道 SSE 主动推送中枢（A2 定稿）。
    内存：userId → asyncio.Queue；subscribe 建立长连接，publish 往队列塞事件。
    """

    def __init__(self):
        self._queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)

    def subscribe(self, user_id: int) -> asyncio.Queue:
        return self._queues[user_id]

    def publish(self, user_id: int, event: dict):
        q = self._queues.get(user_id)
        if q is not None:
            try:
                q.put_nowait(event)
            except Exception as e:  # noqa: BLE001
                log.warning("SSE publish 失败 user=%s: %s", user_id, e)

    def remove(self, user_id: int):
        self._queues.pop(user_id, None)

    async def stream(self, user_id: int):
        """SSE 事件流生成器：每个事件一行 data: {json}"""
        q = self.subscribe(user_id)
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=25)
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"


class PushService:
    """
    主动推送服务（A2 定稿）。
    - remember：dispatch 时记录 user → 最后活跃通道
    - route：返回最后活跃通道
    - push：填 channel/channel_user_id → 交给对应通道适配器发送
    """

    def __init__(self):
        self.hub = SseHub()
        self.last_channel: Dict[int, str] = {}
        self.channel_user_id: Dict[int, str] = {}
        self._adapters: Dict[str, object] = {}

    def register_adapter(self, channel: str, adapter):
        self._adapters[channel] = adapter

    def remember(self, inbound: InboundMessage):
        if inbound.user_id:
            self.last_channel[inbound.user_id] = inbound.channel
            self.channel_user_id[inbound.user_id] = inbound.channel_user_id

    def route(self, user_id: int) -> str:
        return self.last_channel.get(user_id, "web")

    async def push(self, user_id: int, msg: OutboundMessage) -> bool:
        if not msg.channel:
            msg.channel = self.route(user_id)
        if not msg.channel_user_id:
            cid = self.channel_user_id.get(user_id, "")
            if not cid:
                # 进程重启后内存映射丢失：兜底查绑定表（钉钉等外部通道）
                try:
                    async with async_session_maker() as db:
                        cid = await binding_crud.find_channel_user_id(db, user_id, msg.channel) or ""
                except Exception as e:  # noqa: BLE001
                    log.warning("推送通道绑定查询失败: user=%s channel=%s err=%s", user_id, msg.channel, e)
            msg.channel_user_id = cid or str(user_id)
        adapter = self._adapters.get(msg.channel)
        if not adapter:
            log.warning("未注册通道适配器: %s", msg.channel)
            return False
        try:
            await adapter.send(msg)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("推送失败 channel=%s: %s", msg.channel, e)
            return False

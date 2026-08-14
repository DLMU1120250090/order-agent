import logging
import re
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.base import ChannelAdapter
from app.channels.dingtalk import dingtalk_channel
from app.channels.qq import QQChannel
from app.channels.web import WebChannel
from app.channels.wechat import wechat_channel
from app.config import settings
from app.crud import binding as binding_crud
from app.models.schemas import InboundMessage, OutboundMessage
from app.services.orchestrator import TravelOrchestratorService
from app.services.push import PushService

log = logging.getLogger("travel.channel.manager")


class ChannelManager:
    """
    通道注册/分发/会话映射（A2 定稿）。
    - 身份解析/绑定（绑定方案 A：非 Web 通道回复"绑定 <userId>"）
    - 记录最后活跃通道（PushService）
    - orchestrator.handle_message 处理业务 → 包装 OutboundMessage → adapter.send
    """

    def __init__(self, orchestrator: TravelOrchestratorService, push_service: PushService):
        self.orchestrator = orchestrator
        self.push_service = push_service
        self._channels: Dict[str, ChannelAdapter] = {}
        self._register_defaults()

    def _register_defaults(self):
        self.register("web", WebChannel(self.push_service.hub))
        self.register("dingtalk", dingtalk_channel)
        # 微信 Mock 桥始终注册（HTTP Webhook 模拟入站 + outbox 出站）；
        # TRAVEL_ENABLE_WECHAT 控制是否启用真实 Wechaty 桥（默认关）
        self.register("wechat", wechat_channel)
        self.register("qq", QQChannel())
        for name, adapter in self._channels.items():
            self.push_service.register_adapter(name, adapter)

    def register(self, channel: str, adapter: ChannelAdapter):
        self._channels[channel] = adapter
        self.push_service.register_adapter(channel, adapter)

    def get(self, channel: str) -> Optional[ChannelAdapter]:
        return self._channels.get(channel)

    async def dispatch(self, db: AsyncSession, inbound: InboundMessage) -> Optional[OutboundMessage]:
        """统一分发入口：身份 → 绑定 → 业务 → 发送。"""
        # 绑定命令（非 Web 通道）：绑定 <userId>
        if inbound.channel != "web" and inbound.text.strip().startswith("绑定"):
            m = re.search(r"绑定\s*(\d+)", inbound.text)
            if m:
                user_id = int(m.group(1))
                await binding_crud.bind_user(db, user_id, inbound.channel, inbound.channel_user_id)
                msg = OutboundMessage(
                    channel=inbound.channel,
                    channel_user_id=inbound.channel_user_id,
                    text=f"绑定成功，userId={user_id}。现在可以直接对话了。",
                )
            else:
                msg = OutboundMessage(
                    channel=inbound.channel,
                    channel_user_id=inbound.channel_user_id,
                    text="绑定格式：绑定 <userId>",
                )
            return await self._deliver(inbound, msg)

        # 身份解析
        if inbound.user_id is None:
            if inbound.channel == "web":
                try:
                    inbound.user_id = int(inbound.channel_user_id)
                except (TypeError, ValueError):
                    inbound.user_id = 1
            else:
                inbound.user_id = await binding_crud.find_user_id(db, inbound.channel, inbound.channel_user_id)
                if inbound.user_id is None:
                    msg = OutboundMessage(
                        channel=inbound.channel,
                        channel_user_id=inbound.channel_user_id,
                        text="你还未绑定用户。请在 Web 端确认你的 userId 后回复：绑定 <userId>",
                    )
                    return await self._deliver(inbound, msg)

        self.push_service.remember(inbound)
        msg = await self.orchestrator.handle_message(db, inbound)
        if msg:
            return await self._deliver(inbound, msg)
        return msg

    async def _deliver(self, inbound: InboundMessage, msg: OutboundMessage) -> OutboundMessage:
        """把 OutboundMessage 交给对应通道适配器发送后返回。"""
        if not msg.channel:
            msg.channel = inbound.channel
        if not msg.channel_user_id:
            msg.channel_user_id = inbound.channel_user_id
        # 同步分发链路（HTTP 响应会返回给调用方），SSE 仅用于异步推送，避免前端重复渲染
        msg.sync_reply = True
        adapter = self._channels.get(msg.channel)
        if adapter:
            try:
                await adapter.send(msg)
            except Exception as e:  # noqa: BLE001
                log.warning("通道发送失败 channel=%s err=%s", msg.channel, e)
        return msg

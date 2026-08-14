from abc import ABC, abstractmethod
from typing import Any

from app.models.schemas import InboundMessage, OutboundMessage


class ChannelAdapter(ABC):
    """通道适配器抽象基类（A2 定稿）"""

    channel_name: str = "base"

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> bool:
        """向目标用户发送消息"""

    def to_inbound(self, raw: Any) -> InboundMessage:
        """通道原始报文 → 统一 InboundMessage"""
        raise NotImplementedError

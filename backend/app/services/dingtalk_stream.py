"""钉钉 Stream 模式接入：后台线程连接钉钉长连接，收到机器人消息后桥接主事件循环。"""

import asyncio
import json
import logging
import threading
from typing import Callable, Coroutine, Optional

import dingtalk_stream
from dingtalk_stream import AckMessage, CallbackMessage, ChatbotMessage

from app.config import settings

log = logging.getLogger("travel.dingtalk.stream")


class _BotHandler(dingtalk_stream.ChatbotHandler):
    """机器人消息回调：文本消息 -> 主事件循环处理。"""

    def __init__(self, loop: asyncio.AbstractEventLoop, on_message: Callable[[str, ChatbotMessage], Coroutine]):
        super().__init__()
        self.loop = loop
        self.on_message = on_message

    async def process(self, callback: CallbackMessage):
        log.info("[DingTalk回调] topic=%s data=%s", callback.headers.topic, json.dumps(callback.data, ensure_ascii=False)[:500])
        try:
            data = callback.data
            if isinstance(data, str):
                data = json.loads(data)
            msg = ChatbotMessage.from_dict(data)
            log.info("[DingTalk消息] msgtype=%s sender=%s convType=%s text=%r",
                     msg.message_type, getattr(msg, "sender_staff_id", None),
                     msg.conversation_type, "".join(msg.get_text_list() or []))
            if msg.message_type != "text":
                return AckMessage.STATUS_OK, "ok"
            text = "".join(msg.get_text_list() or []).strip()
            if not text:
                return AckMessage.STATUS_OK, "ok"
            asyncio.run_coroutine_threadsafe(self.on_message(text, msg), self.loop)
        except Exception as e:  # noqa: BLE001
            log.exception("钉钉 Stream 回调处理失败: %s", e)
        return AckMessage.STATUS_OK, "ok"


class DingTalkStreamService:
    """管理钉钉 Stream 客户端生命周期（后台守护线程）。"""

    def __init__(self):
        self._client: Optional[dingtalk_stream.DingTalkStreamClient] = None
        self._thread: Optional[threading.Thread] = None
        self._started = False

    @property
    def started(self) -> bool:
        return self._started

    def start(self, loop: asyncio.AbstractEventLoop, on_message: Callable[[str, ChatbotMessage], Coroutine]):
        if self._started:
            return
        if not (settings.DINGTALK_APP_KEY and settings.DINGTALK_APP_SECRET):
            log.warning("未配置 DINGTALK_APP_KEY/SECRET，钉钉 Stream 不启动")
            return
        self._started = True

        def _run():
            log.info("钉钉 Stream 线程启动，尝试建立长连接...")
            while self._started:
                try:
                    credential = dingtalk_stream.Credential(settings.DINGTALK_APP_KEY, settings.DINGTALK_APP_SECRET)
                    client = dingtalk_stream.DingTalkStreamClient(credential)
                    client.register_callback_handler(
                        ChatbotMessage.TOPIC,
                        _BotHandler(loop, on_message),
                    )
                    self._client = client
                    log.info("已注册回调 topic=%s", ChatbotMessage.TOPIC)
                    client.start_forever()
                except Exception as e:  # noqa: BLE001
                    log.warning("钉钉 Stream 连接异常，3 秒后重连: %s", e)
                    if self._started:
                        import time
                        time.sleep(3)

        self._thread = threading.Thread(target=_run, name="dingtalk-stream", daemon=True)
        self._thread.start()
        log.info("钉钉 Stream 客户端已启动")

    def stop(self):
        self._started = False
        client = self._client
        if client is not None:
            try:
                ws = getattr(client, "websocket", None)
                if ws is not None:
                    ws.close()
            except Exception:  # noqa: BLE001
                pass
        log.info("钉钉 Stream 客户端已停止")


dingtalk_stream_service = DingTalkStreamService()

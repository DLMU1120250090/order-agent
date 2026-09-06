import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

from app.channels.base import ChannelAdapter
from app.config import settings
from app.models.schemas import InboundMessage, OutboundMessage

log = logging.getLogger("travel.channel.dingtalk")


class DingTalkChannel(ChannelAdapter):
    """
    钉钉通道（A2 定稿）。
    收消息：Stream 模式回调 / HTTP 回调 POST /api/v1/travel/webhook/dingtalk。
    发消息：优先使用回调里的 sessionWebhook（无需 accessToken）；
    发图片需先 media/upload 拿 mediaId。
    """

    channel_name = "dingtalk"

    def __init__(self):
        # 会话注册表：channel_user_id -> {session_webhook, conversation_id, conversation_type, expires}
        self._sessions: Dict[str, dict] = {}
        self._access_token: Optional[dict] = None

    # ---------- 会话注册 ----------
    def _remember(self, sender: str, raw: dict):
        webhook = raw.get("sessionWebhook") or ""
        expires = raw.get("sessionWebhookExpiredTime")
        try:
            expires = int(expires) / 1000 if expires else 0
        except (TypeError, ValueError):
            expires = 0
        robot_code = raw.get("robotCode") or ""
        prev_robot_code = (self._sessions.get(sender) or {}).get("robot_code")
        self._sessions[sender] = {
            "session_webhook": webhook,
            "conversation_id": raw.get("conversationId") or "",
            "conversation_type": raw.get("conversationType") or "",
            "robot_code": robot_code,
            "expires": expires,
        }
        if robot_code and not prev_robot_code:
            log.info("钉钉会话注册: user=%s robotCode=%s convType=%s", sender, robot_code, self._sessions[sender]["conversation_type"])

    def session_webhook(self, channel_user_id: str) -> str:
        session = self._sessions.get(channel_user_id) or {}
        webhook = session.get("session_webhook") or ""
        expires = session.get("expires") or 0
        if webhook and expires and time.time() > expires:
            log.warning("钉钉 sessionWebhook 已过期: user=%s", channel_user_id)
            return ""
        return webhook

    # ---------- 入站 ----------
    def to_inbound(self, raw: dict) -> InboundMessage:
        text = ""
        sender = str(raw.get("senderStaffId") or raw.get("senderId") or raw.get("senderNick") or "ding_unknown")
        content = raw.get("text") or {}
        if isinstance(content, dict):
            text = content.get("content", "")
        else:
            text = str(content)
        self._remember(sender, raw)
        return InboundMessage(
            channel="dingtalk",
            channel_user_id=sender,
            session_key=f"dingtalk:{sender}",
            text=text,
            attachments=raw.get("attachments", []),
        )

    def to_inbound_chatbot(self, msg) -> InboundMessage:
        """Stream 模式回调 ChatbotMessage -> 统一 InboundMessage"""
        sender = str(getattr(msg, "sender_staff_id", "") or getattr(msg, "sender_id", "") or "ding_unknown")
        text = "".join(msg.get_text_list() or []).strip()
        self._remember(sender, {
            "sessionWebhook": getattr(msg, "session_webhook", ""),
            "sessionWebhookExpiredTime": getattr(msg, "session_webhook_expired_time", None),
            "conversationId": getattr(msg, "conversation_id", ""),
            "conversationType": getattr(msg, "conversation_type", ""),
            "robotCode": getattr(msg, "robot_code", ""),
        })
        return InboundMessage(
            channel="dingtalk",
            channel_user_id=sender,
            session_key=f"dingtalk:{sender}",
            text=text,
        )

    # ---------- 出站 ----------
    async def send(self, msg: OutboundMessage) -> bool:
        try:
            if msg.kind == "IMAGE" and msg.image_path:
                ok = await self._send_image(msg)
            else:
                webhook = self.session_webhook(msg.channel_user_id)
                if webhook:
                    ok = await self._send_text(webhook, msg)
                else:
                    # 主动推送场景：webhook 缺失/过期时走 OpenAPI 单聊批量发送
                    ok = await self._send_openapi_text(msg)
            log.info("[DingTalk->%s] %s sent=%s", msg.channel_user_id, msg.kind, ok)
            return ok
        except Exception as e:  # noqa: BLE001
            log.warning("钉钉发送失败: user=%s kind=%s err=%s", msg.channel_user_id, msg.kind, e)
            return False

    async def _send_text(self, webhook: str, msg: OutboundMessage) -> bool:
        text = self._render_text(msg)
        return await self._post_webhook(webhook, {"msgtype": "text", "text": {"content": text}})

    async def _send_openapi_text(self, msg: OutboundMessage) -> bool:
        """Webhook 缺失/过期时的文本兜底：POST /v1.0/robot/oToMessages/batchSend。"""
        robot_code = (self._sessions.get(msg.channel_user_id) or {}).get("robot_code") or settings.DINGTALK_ROBOT_CODE
        if not robot_code:
            log.warning("钉钉缺少 robotCode，无法通过 OpenAPI 发送文本: user=%s", msg.channel_user_id)
            return False
        msg_param = json.dumps({"content": self._render_text(msg)}, ensure_ascii=False)
        return await self._send_openapi_batch(robot_code, [msg.channel_user_id], "sampleText", msg_param)

    @staticmethod
    def _render_text(msg: OutboundMessage) -> str:
        text = msg.text or ""
        if msg.blocks:
            try:
                for block in msg.blocks[:5]:
                    title = block.get("title") or block.get("label") or ""
                    desc = block.get("description") or block.get("value") or ""
                    if title or desc:
                        text += f"\n- {title}: {desc}"
            except Exception:  # noqa: BLE001
                pass
        return text

    async def _send_image(self, msg: OutboundMessage) -> bool:
        """图片必须走 OpenAPI（Webhook 只支持文本/Markdown）。
        单聊：POST /v1.0/robot/oToMessages/batchSend，msgKey=sampleImageMsg，photoURL 可填 mediaId。
        """
        media_id = await asyncio.to_thread(self._upload_image, msg.image_path)
        if not media_id:
            log.warning("钉钉图片上传失败: path=%s", msg.image_path)
            return False

        session = self._sessions.get(msg.channel_user_id) or {}
        robot_code = session.get("robot_code") or settings.DINGTALK_ROBOT_CODE
        if not robot_code:
            log.warning("钉钉缺少 robotCode，无法通过 OpenAPI 发送图片: user=%s", msg.channel_user_id)
            return False

        msg_param = json.dumps({"photoURL": media_id}, ensure_ascii=False)
        return await self._send_openapi_batch(robot_code, [msg.channel_user_id], "sampleImageMsg", msg_param)

    async def _send_openapi_batch(self, robot_code: str, user_ids: List[str], msg_key: str, msg_param: str) -> bool:
        """新版 OpenAPI 单聊批量发送（图片/文本等通用）。"""
        import httpx

        token = self._get_access_token()
        if not token:
            log.warning("钉钉 accessToken 获取失败，无法通过 OpenAPI 发送")
            return False
        body = {
            "robotCode": robot_code,
            "userIds": user_ids,
            "msgKey": msg_key,
            "msgParam": msg_param,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend",
                    headers={"x-acs-dingtalk-access-token": token},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:  # noqa: BLE001
            log.warning("钉钉 OpenAPI 发送失败: key=%s user=%s err=%s", msg_key, user_ids, e)
            return False
        if isinstance(data, dict) and data.get("errcode") not in (None, 0):
            log.warning("钉钉 OpenAPI 发送业务错误: %s", data)
            return False
        return True

    @staticmethod
    async def _post_webhook(webhook: str, payload: dict) -> bool:
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json=payload)
            resp.raise_for_status()
            data = resp.json()
        # 旧式 webhook 成功返回 {"errcode":0}；新式返回 200 无错误码
        if isinstance(data, dict) and data.get("errcode") not in (None, 0):
            log.warning("钉钉 webhook 业务错误: %s", data)
            return False
        return True

    def _upload_image(self, path: str) -> str:
        """上传图片到钉钉素材库，返回 mediaId（同步阻塞，调用处用 to_thread）"""
        import requests

        token = self._get_access_token()
        if not token:
            return ""
        with open(path, "rb") as f:
            files = {"media": (path.rsplit("/", 1)[-1] or "image.png", f, "image/png")}
            data = {"type": "image"}
            resp = requests.post(
                f"https://oapi.dingtalk.com/media/upload?access_token={token}",
                data=data, files=files, timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()
        if result.get("errcode") not in (None, 0):
            log.warning("钉钉 media/upload 失败: %s", result)
            return ""
        return result.get("media_id") or ""

    def _get_access_token(self) -> str:
        """获取应用 accessToken（新版 /v1.0/oauth2/accessToken，缓存 2 小时）"""
        import requests

        if self._access_token and time.time() < self._access_token["expire_time"]:
            return self._access_token["accessToken"]
        resp = requests.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": settings.DINGTALK_APP_KEY, "appSecret": settings.DINGTALK_APP_SECRET},
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        self._access_token = {
            "accessToken": result.get("accessToken", ""),
            "expire_time": time.time() + int(result.get("expireIn", 7200)) - 300,
        }
        return self._access_token["accessToken"]


# 全局共享实例：Stream 回调、HTTP webhook、ChannelManager 使用同一会话注册表
dingtalk_channel = DingTalkChannel()

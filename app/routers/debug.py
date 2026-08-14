"""调试/演示接口：主动向用户最近活跃通道推送消息（如把本地图片发到钉钉）。"""

import os

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import binding as binding_crud
from app.crud import order as order_crud
from app.crud import task as task_crud
from app.database import get_db
from app.models.enums import OrderStatus
from app.models.schemas import OutboundMessage
from app.channels.dingtalk import dingtalk_channel
from app.services.runtime import push_service, scheduler

router = APIRouter(tags=["travel-debug"])


@router.post("/api/v1/travel/debug/run-scheduler")
async def debug_run_scheduler(request: Request):
    """手动触发主动推送扫描：departure_reminder / price_watch / flight_monitor。"""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    job = (body.get("job") or "departure_reminder").strip()
    if job == "departure_reminder":
        await scheduler._departure_reminder()
    elif job == "price_watch":
        await scheduler._price_watch()
    elif job == "flight_monitor":
        await scheduler._flight_monitor()
    else:
        return {
            "ok": False,
            "error": f"未知 job: {job}，可选 departure_reminder / price_watch / flight_monitor",
        }
    return {"ok": True, "job": job}


@router.post("/api/v1/travel/debug/test-departure-reminder")
async def debug_test_departure_reminder(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """把订单拨到“24h 内出发”窗口并立即触发出发提醒（可重复测试）。"""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    order_no = (body.get("order_no") or "").strip()
    user_id = int(body.get("user_id") or 1)

    if order_no:
        order = await order_crud.get_order_by_no(db, user_id, order_no)
    else:
        orders = await order_crud.list_orders(db, user_id)
        order = next((o for o in orders if o.status == OrderStatus.PAID.value), None)
    if not order:
        return {"ok": False, "error": "未找到可用的 PAID 订单（可传 order_no 指定）"}

    from datetime import datetime, timedelta
    await order_crud.update_order(db, order.id, updated_at=datetime.now() - timedelta(hours=1))
    # 清除历史已成功的提醒任务，允许重复推送
    reset = await task_crud.reset_advisory_tasks(db, order.id)

    await scheduler._departure_reminder()
    return {
        "ok": True,
        "order_no": order.order_no,
        "channel": order.channel,
        "reset_advisory_tasks": reset,
        "hint": "请到钉钉/日志确认“出行准备包”是否送达",
    }


@router.post("/api/v1/travel/debug/send-image")
async def debug_send_image(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_user_id: int = Header(default=1, alias="X-User-Id"),
):
    """把本地图片作为 IMAGE 消息推送到用户最近活跃的通道（默认 order-agent/qr_code.jpg）。"""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    user_id = int(body.get("user_id") or x_user_id)
    image_path = body.get("image_path") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "qr_code.jpg",
    )
    if not os.path.exists(image_path):
        return {"sent": False, "error": f"文件不存在: {image_path}"}

    msg = OutboundMessage(
        kind="IMAGE",
        image_path=image_path,
        channel=body.get("channel") or "",
        channel_user_id=body.get("channel_user_id") or "",
        text=body.get("text") or "测试二维码",
    )
    # 通道/用户标识兜底：内存记忆 -> 绑定表（钉钉）
    if not msg.channel:
        msg.channel = push_service.last_channel.get(user_id) or "dingtalk"
    if not msg.channel_user_id:
        msg.channel_user_id = push_service.channel_user_id.get(user_id) or await binding_crud.find_channel_user_id(db, user_id, msg.channel) or ""
    ok = await push_service.push(user_id, msg)
    ding_session = dingtalk_channel._sessions.get(msg.channel_user_id) or {}
    return {
        "sent": ok,
        "channel": msg.channel,
        "channel_user_id": msg.channel_user_id,
        "image_path": image_path,
        "dingtalk_robot_code_ready": bool(ding_session.get("robot_code")),
        "remembered_channel": push_service.last_channel.get(user_id),
        "remembered_channel_user_id": push_service.channel_user_id.get(user_id),
    }

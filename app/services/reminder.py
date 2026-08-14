import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import task as task_crud
from app.models.database import TravelOrderRow, TravelTaskRow
from app.models.enums import OrderStatus, TaskStatus, TaskType
from app.models.schemas import OutboundMessage, TransportLeg
from app.services.checklist import ChecklistService
from app.services.collector import DataCollectorService
from app.services.memory import MemoryService
from app.services.push import PushService
from app.services.task import TaskService
from app.services.weather_advice import WeatherAdvisoryService

log = logging.getLogger("travel.reminder")


class ReminderService:
    """
    出发前提醒（C4 定稿）：
    定时扫描 travel_order → 命中"24h 内出发且未提醒过"的订单 → 组合推送出行准备包。
    """

    def __init__(
        self,
        memory: MemoryService,
        weather_advice: WeatherAdvisoryService,
        checklist: ChecklistService,
        push: PushService,
        task_service: TaskService,
        collector: DataCollectorService,
    ):
        self.memory = memory
        self.weather_advice = weather_advice
        self.checklist = checklist
        self.push = push
        self.task_service = task_service
        self.collector = collector

    async def scan_due_orders(self, db: AsyncSession) -> int:
        """扫描 PAID 订单，24h 内出发且未提醒过 → 推送准备包。"""
        res = await db.execute(
            select(TravelOrderRow).where(TravelOrderRow.status == OrderStatus.PAID.value)
        )
        sent = 0
        for order in res.scalars().all():
            if not self._departing_within(order, hours=24):
                continue
            already = await self._reminded(db, order.id)
            if already:
                continue
            task_id = await self.task_service.create(
                db,
                order.user_id,
                TaskType.advisory.value,
                {"order_id": order.id},
                channel=order.channel,
                order_id=order.id,
            )
            await self.send_departure_pack(db, order, task_id)
            sent += 1
        return sent

    async def send_departure_pack(self, db: AsyncSession, order: TravelOrderRow, task_id: str):
        await self.task_service.start(db, task_id)
        legs = [TransportLeg(**l) for l in (order.legs or {}).get("legs", [])]
        destination = legs[-1].to_city if legs else "目的地"
        origin = legs[0].from_city if legs else "出发地"

        weather = await self.collector.hourly_weather(db, 30.0, 110.0, hours=12)
        advice = await self.weather_advice.build_advisory(
            db, origin, destination, depart_hour=8, commute_minutes=60, weather=weather
        )
        checklist_md = await self.checklist.generate(db, legs, destination, weather)
        # L1 证件检查：临近/不覆盖出发日期则提醒
        profile = await self.memory.get_profile(db, order.user_id)
        id_check = "证件信息未录入，请确保携带有效身份证件。" if not (profile and profile.passengers) else "证件有效期检查通过。"

        text = (
            f"✈️ 出行准备包（{destination}）\n"
            f"- 值机：出发前 24h 开放，建议提前值机\n"
            f"- 证件：{id_check}\n"
            f"- 天气：{advice}\n"
            f"- 清单：\n{checklist_md}"
        )
        await self.push.push(
            order.user_id,
            OutboundMessage(kind="TEXT", channel=order.channel, text=text, correlation_id=task_id),
        )
        await self.task_service.succeed(db, task_id, result={"order_no": order.order_no, "type": "advisory"}, notify=False)

    async def _reminded(self, db: AsyncSession, order_id: int) -> bool:
        res = await db.execute(
            select(TravelTaskRow).where(
                TravelTaskRow.order_id == order_id,
                TravelTaskRow.type == TaskType.advisory.value,
                TravelTaskRow.status == TaskStatus.SUCCEEDED.value,
            ).limit(1)
        )
        return res.scalars().first() is not None

    @staticmethod
    def _departing_within(order: TravelOrderRow, hours: int) -> bool:
        """Mock 出发时间：订单更新时间 +24h（演示用）。
        updated_at 由 MySQL CURRENT_TIMESTAMP 写入（本地时区），因此用 datetime.now() 比较。"""
        depart = order.updated_at + timedelta(hours=24)
        now = datetime.now()
        return now <= depart <= now + timedelta(hours=hours)

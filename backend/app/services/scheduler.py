import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import order as order_crud
from app.crud import task as task_crud
from app.database import async_session_maker
from app.models.database import DataCacheRow, TravelOrderRow, TravelTripRow, UserProfileRow
from app.models.enums import OrderStatus, TaskStatus, TaskType
from app.services.memory import MemoryService
from app.services.memory_context import monitor_context_from_profile
from app.services.monitor import FlightMonitorService, PriceMonitorService
from app.services.reminder import ReminderService
from app.services.task import TaskService
from app.services.trace import TraceScope
from app.services.trace_schema import EventType

log = logging.getLogger("travel.scheduler")


async def cleanup_expired_cache(db: AsyncSession) -> int:
    """删除 data_cache 中已过期行（expire_at 存 UTC，用 UTC_TIMESTAMP 比较）。"""
    result = await db.execute(
        delete(DataCacheRow).where(DataCacheRow.expire_at < func.utc_timestamp())
    )
    await db.commit()
    return int(result.rowcount or 0)


def price_monitor_enabled(preferences) -> bool:
    """价格监控总开关：读 preferences.price_monitor，未设置视为开启。

    Commit 0：修复"写而不读"——之前 orchestrator 可关闭开关，但调度器
    price_watch 从不读取，用户关掉价格监控实际仍会推送。
    """
    prefs = preferences or {}
    return bool(prefs.get("price_monitor", True))


class SchedulerService:
    """
    定时任务（A3 定稿，APScheduler AsyncIOScheduler）。
    price_watch(1h) / flight_monitor(6h) / departure_reminder(30min) /
    memory_distill(每日23:55) / retry_worker(1min)
    """

    def __init__(
        self,
        task_service: TaskService,
        reminder: ReminderService,
        price_monitor: PriceMonitorService,
        flight_monitor: FlightMonitorService,
        memory: MemoryService,
    ):
        self.task_service = task_service
        self.reminder = reminder
        self.price_monitor = price_monitor
        self.flight_monitor = flight_monitor
        self.memory = memory
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    def start(self):
        if self.scheduler.running:
            return
        self.scheduler.add_job(self._price_watch, IntervalTrigger(minutes=60), id="price_watch", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._flight_monitor, IntervalTrigger(minutes=360), id="flight_monitor", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._departure_reminder, IntervalTrigger(minutes=30), id="departure_reminder", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._memory_distill, CronTrigger(hour=23, minute=55), id="memory_distill", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._retry_worker, IntervalTrigger(minutes=1), id="retry_worker", max_instances=1, coalesce=True)
        self.scheduler.add_job(self._cleanup_data_cache, IntervalTrigger(minutes=60), id="data_cache_cleanup", max_instances=1, coalesce=True)
        self.scheduler.start()
        log.info("SchedulerService 已启动：price_watch/flight_monitor/departure_reminder/memory_distill/retry_worker/data_cache_cleanup")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def _price_watch(self):
        async with async_session_maker() as db:
            # 价格监控总开关（preferences.price_monitor，未设置视为开启；按用户缓存避免重复查库）
            enabled_cache: dict = {}
            monitor_ctx_cache: dict = {}

            async def is_enabled(user_id: int) -> bool:
                if user_id not in enabled_cache:
                    profile = await self.memory.get_profile(db, user_id)
                    enabled_cache[user_id] = price_monitor_enabled(profile.preferences if profile else None)
                return enabled_cache[user_id]

            async def monitor_ctx_for(user_id: int) -> dict:
                if user_id not in monitor_ctx_cache:
                    profile = await self.memory.get_profile(db, user_id)
                    monitor_ctx_cache[user_id] = monitor_context_from_profile(profile)
                return monitor_ctx_cache[user_id]

            # 阶段1：进行中的行程需求（PLANNING）
            res = await db.execute(select(TravelTripRow).where(TravelTripRow.status == "PLANNING"))
            for trip in res.scalars().all():
                if not await is_enabled(trip.user_id):
                    continue
                async with TraceScope(db, "", trip.user_id, run_id=f"price_watch:trip:{trip.id}") as ctx:
                    task_id = await self.task_service.create(
                        db, trip.user_id, TaskType.price_watch.value,
                        {"trip_id": trip.id, "phase": 1}, channel="web",
                    )
                    ctx.set_task_id(task_id)
                    try:
                        await self.task_service.start(db, task_id)
                        hit = await self.price_monitor.scan_phase1(db, trip, monitor_ctx=await monitor_ctx_for(trip.user_id))
                        if hit:
                            ctx.record_event(EventType.PRICE_DROP_NOTIFIED, "MONITOR", {"trip_id": trip.id}, {"hit": bool(hit)})
                        await self.task_service.succeed(db, task_id, result={"hit": bool(hit)}, notify=False)
                    except Exception as e:  # noqa: BLE001
                        await self.task_service.fail(db, task_id, str(e), retryable=True)

            # 阶段2：已出票订单在出发窗口内
            res2 = await db.execute(select(TravelOrderRow).where(TravelOrderRow.status == OrderStatus.PAID.value))
            for order in res2.scalars().all():
                if not await is_enabled(order.user_id):
                    continue
                async with TraceScope(db, "", order.user_id, run_id=f"price_watch:order:{order.id}") as ctx:
                    task_id = await self.task_service.create(
                        db, order.user_id, TaskType.price_watch.value,
                        {"order_no": order.order_no, "phase": 2}, channel=order.channel, order_id=order.id,
                    )
                    ctx.set_task_id(task_id)
                    try:
                        await self.task_service.start(db, task_id)
                        decision = await self.price_monitor.scan_phase2(db, order, monitor_ctx=await monitor_ctx_for(order.user_id))
                        if decision:
                            ctx.record_event(EventType.PRICE_DROP_NOTIFIED, "MONITOR", {"order_no": order.order_no}, {"hit": bool(decision)})
                        await self.task_service.succeed(db, task_id, result={"hit": bool(decision)}, notify=False)
                    except Exception as e:  # noqa: BLE001
                        await self.task_service.fail(db, task_id, str(e), retryable=True)

    async def _flight_monitor(self):
        async with async_session_maker() as db:
            res = await db.execute(select(TravelOrderRow).where(TravelOrderRow.status == OrderStatus.PAID.value))
            for order in res.scalars().all():
                async with TraceScope(db, "", order.user_id, run_id=f"flight_monitor:order:{order.id}") as ctx:
                    task_id = await self.task_service.create(
                        db, order.user_id, TaskType.flight_monitor.value,
                        {"order_no": order.order_no}, channel=order.channel, order_id=order.id,
                    )
                    ctx.set_task_id(task_id)
                    try:
                        await self.task_service.start(db, task_id)
                        decision = await self.flight_monitor.scan(db, order)
                        await self.task_service.succeed(db, task_id, result={"hit": bool(decision)}, notify=False)
                    except Exception as e:  # noqa: BLE001
                        await self.task_service.fail(db, task_id, str(e), retryable=True)

    async def _departure_reminder(self):
        async with async_session_maker() as db:
            async with TraceScope(db, "", 0, run_id="departure_reminder"):
                try:
                    sent = await self.reminder.scan_due_orders(db)
                    if sent:
                        log.info("出发提醒已推送 %s 个订单", sent)
                except Exception as e:  # noqa: BLE001
                    log.warning("出发提醒扫描失败: %s", e)

    async def _memory_distill(self):
        async with async_session_maker() as db:
            res = await db.execute(select(UserProfileRow))
            for row in res.scalars().all():
                async with TraceScope(db, "", row.user_id, run_id=f"memory_distill:{row.user_id}") as ctx:
                    try:
                        ctx.record_event("MEMORY_DISTILL_STARTED", "MEMORY", {"userId": row.user_id}, {})
                        await self.memory.distill(db, row.user_id)
                        ctx.record_event("MEMORY_DISTILL_SUCCEEDED", "MEMORY", {"userId": row.user_id}, {})
                    except Exception as e:  # noqa: BLE001
                        log.warning("记忆蒸馏失败 user=%s: %s", row.user_id, e)
                        ctx.record_event("MEMORY_DISTILL_FAILED", "MEMORY", {"userId": row.user_id}, {"error": str(e)[:300]})

    async def _cleanup_data_cache(self):
        """每小时清理过期 data_cache（读时惰性过期的补位清理，防止残留行累积）。"""
        async with async_session_maker() as db:
            try:
                removed = await cleanup_expired_cache(db)
                if removed:
                    log.info("已清理过期 data_cache %s 条", removed)
            except Exception as e:  # noqa: BLE001
                log.warning("过期缓存清理失败: %s", e)

    async def _retry_worker(self):
        """拉起到期 RETRYING 任务（资金类不自动重试；重试次数超限标记失败）。"""
        async with async_session_maker() as db:
            tasks = await task_crud.list_retryable(db, limit=20)
            for t in tasks:
                if t.retry_count >= 3:
                    await task_crud.update_task(db, t.task_id, status=TaskStatus.FAILED.value, error_message="重试次数超限")
                else:
                    # 非资金类任务（监控/提醒类）重跑：先标 RUNNING，交由下次调度扫描自然恢复
                    await task_crud.update_task(
                        db, t.task_id,
                        status=TaskStatus.RUNNING.value,
                        next_run_at=datetime.utcnow() + timedelta(minutes=1),
                    )

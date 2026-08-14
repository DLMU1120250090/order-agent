import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import task as task_crud
from app.database import async_session_maker
from app.models.enums import TaskStatus, PaymentPending
from app.models.schemas import OutboundMessage, TaskOut
from app.services.push import PushService

log = logging.getLogger("travel.task")


class TaskService:
    """
    异步任务模型（A3 定稿）。
    PENDING → RUNNING → WAITING_USER → SUCCEEDED / FAILED / CANCELLED
    - 用户触发 → create → 立即回 TASK_PROGRESS → 后台协程 run(task_id, coro)
    - 每步 update_progress + PushService 推送 → succeed/fail 推送结果
    """

    def __init__(self, push_service: PushService):
        self.push_service = push_service

    async def create(
        self,
        db: AsyncSession,
        user_id: int,
        task_type: str,
        params: dict,
        channel: str = "web",
        session_id: Optional[str] = None,
        order_id: Optional[int] = None,
    ) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        await task_crud.create_task(
            db,
            task_id=task_id,
            user_id=user_id,
            task_type=task_type,
            params=params,
            channel=channel,
            session_id=session_id,
            order_id=order_id,
        )
        return task_id

    async def start(self, db: AsyncSession, task_id: str):
        await task_crud.update_task(db, task_id, status=TaskStatus.RUNNING.value, progress=0)

    async def update_progress(
        self,
        db: AsyncSession,
        task_id: str,
        progress: int,
        text: Optional[str] = None,
        status: Optional[str] = None,
    ):
        fields = {"progress": min(100, max(0, progress))}
        if status:
            fields["status"] = status
        row = await task_crud.update_task(db, task_id, **fields)
        if row:
            await self.push_service.push(
                row.user_id,
                OutboundMessage(
                    kind="TASK_PROGRESS",
                    channel=row.channel,
                    text=text or f"任务进行中（{row.progress}%）",
                    task_progress={"taskId": row.task_id, "status": row.status, "progress": row.progress},
                    correlation_id=row.task_id,
                ),
            )

    async def wait_user(self, db: AsyncSession, task_id: str, pending: str, text: str):
        """进入 WAITING_USER 状态（等支付/等手动/等确认）"""
        row = await task_crud.update_task(
            db,
            task_id,
            status=TaskStatus.WAITING_USER.value,
            progress=80,
        )
        if row:
            await self.push_service.push(
                row.user_id,
                OutboundMessage(
                    kind="TASK_PROGRESS",
                    channel=row.channel,
                    text=text,
                    task_progress={"taskId": row.task_id, "status": row.status, "progress": 80, "pending": pending},
                    correlation_id=row.task_id,
                ),
            )

    async def succeed(self, db: AsyncSession, task_id: str, result: Optional[dict] = None, notify: bool = True):
        row = await task_crud.update_task(
            db, task_id, status=TaskStatus.SUCCEEDED.value, progress=100, result=result
        )
        if row and notify:
            await self.push_service.push(
                row.user_id,
                OutboundMessage(
                    kind="TEXT",
                    channel=row.channel,
                    text="任务已完成 ✅",
                    task_progress={"taskId": row.task_id, "status": row.status, "progress": 100},
                    correlation_id=row.task_id,
                ),
            )

    async def fail(
        self,
        db: AsyncSession,
        task_id: str,
        error: str,
        retryable: bool = False,
        next_run_at: Optional[datetime] = None,
        notify: bool = True,
    ):
        status = TaskStatus.RETRYING.value if retryable else TaskStatus.FAILED.value
        fields = {"status": status, "error_message": error[:500], "retry_count": 0}
        if retryable:
            row_before = await task_crud.get_task(db, task_id)
            fields["retry_count"] = (row_before.retry_count if row_before else 0) + 1
            fields["next_run_at"] = next_run_at or (datetime.utcnow() + timedelta(minutes=1))
        row = await task_crud.update_task(db, task_id, **fields)
        if row and notify:
            await self.push_service.push(
                row.user_id,
                OutboundMessage(
                    kind="TEXT",
                    channel=row.channel,
                    text=f"任务失败：{error}",
                    task_progress={"taskId": row.task_id, "status": row.status, "progress": row.progress},
                    correlation_id=row.task_id,
                ),
            )

    async def cancel(self, db: AsyncSession, task_id: str):
        await task_crud.update_task(db, task_id, status=TaskStatus.CANCELLED.value)

    async def get(self, db: AsyncSession, task_id: str) -> Optional[TaskOut]:
        row = await task_crud.get_task(db, task_id)
        if not row:
            return None
        return TaskOut(
            task_id=row.task_id,
            type=row.type,
            status=row.status,
            progress=row.progress,
            result=row.result,
            error_message=row.error_message,
        )

    async def run(self, task_id: str, coro: Callable[[AsyncSession], Any]):
        """
        后台执行包装：独立 DB 会话，start → await → succeed/fail。
        供 asyncio.create_task(task_service.run(task_id, coro)) 调用。
        """
        async with async_session_maker() as db:
            await self.start(db, task_id)
            try:
                result = await coro(db)
                # 等待用户操作（支付/手动/确认）的任务保持 WAITING_USER，由业务方确认后置为 SUCCEEDED
                if isinstance(result, dict) and result.get("waiting"):
                    return
                await self.succeed(db, task_id, result=result)
            except Exception as e:  # noqa: BLE001
                log.exception("后台任务失败 task_id=%s", task_id)
                await self.fail(db, task_id, str(e), retryable=False)

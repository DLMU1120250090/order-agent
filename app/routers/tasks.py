from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import TaskOut
from app.services.runtime import task_service

router = APIRouter(prefix="/api/v1/travel/tasks", tags=["travel-tasks"])


@router.get("/{taskId}", response_model=TaskOut)
async def get_task(
    taskId: str,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """查询后台任务进度/结果。"""
    task = await task_service.get(db, taskId)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

from typing import List, Optional

from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import UserProfile
from app.services.runtime import memory

router = APIRouter(prefix="/api/v1/travel/profiles", tags=["travel-profiles"])


class ProfileUpdateRequest(BaseModel):
    homeCity: Optional[str] = None
    budgetLevel: Optional[str] = None
    preferences: Optional[dict] = None
    passengers: Optional[List[dict]] = None


@router.get("", response_model=UserProfile)
async def get_profile(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    profile = await memory.get_profile(db, x_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    return profile


@router.put("", response_model=UserProfile)
async def update_profile(
    request: ProfileUpdateRequest,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    fields = {}
    if request.homeCity:
        fields["home_city"] = request.homeCity
    if request.budgetLevel:
        fields["budget_level"] = request.budgetLevel
    if request.preferences:
        fields["preferences"] = request.preferences
    if request.passengers is not None:
        fields["passengers"] = request.passengers
    return await memory.update_profile(db, x_user_id, **fields)


memory_router = APIRouter(prefix="/api/v1/travel/memory", tags=["travel-memory"])


@memory_router.get("/episodes")
async def list_episodes(
    limit: int = 20,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户历史行程摘要经历（L2 Episode）"""
    import json
    from sqlalchemy import select, desc
    from app.models.database import TripSummaryRow

    safe_limit = max(1, min(100, limit))
    stmt = (
        select(TripSummaryRow)
        .where(TripSummaryRow.user_id == x_user_id)
        .order_by(desc(TripSummaryRow.created_at))
        .limit(safe_limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    episodes = []
    for r in rows:
        ep_data = r.episode_json
        if isinstance(ep_data, str):
            try:
                ep_data = json.loads(ep_data)
            except Exception:
                ep_data = {}
        episodes.append({
            "id": r.id,
            "tripId": r.trip_id,
            "summaryMd": r.summary_md or "",
            "episode": ep_data or {},
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        })
    return episodes


@memory_router.get("/distill")
async def get_distill_report(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
):
    """获取用户 L3 偏好蒸馏 Markdown 报告"""
    import os
    path = memory._l3_path(x_user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = f"# 用户偏好蒸馏（L3）\n\n暂无针对用户 {x_user_id} 的偏好蒸馏记录。"
    return {"userId": x_user_id, "content": content}


@memory_router.post("/distill")
async def trigger_distill(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """手动触发当前用户的 L3 偏好蒸馏并刷新报告"""
    try:
        content = await memory.distill(db, x_user_id)
    except Exception as e:
        content = f"# 用户偏好蒸馏（L3）\n\n蒸馏执行异常或无近期行程更新: {e}"
    return {"userId": x_user_id, "content": content}

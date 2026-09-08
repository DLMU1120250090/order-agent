from typing import List, Optional

from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import UserProfile, PassengerCreateInput, PassengerUpdateInput
from app.services.runtime import memory

router = APIRouter(prefix="/api/v1/travel/profiles", tags=["travel-profiles"])


class ProfileUpdateRequest(BaseModel):
    homeCity: Optional[str] = None
    budgetLevel: Optional[str] = None
    preferences: Optional[dict] = None
    preferences_v2: Optional[dict] = None
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
    if request.preferences_v2 is not None:
        fields["preferences_v2"] = request.preferences_v2
    if request.passengers is not None:
        fields["passengers"] = request.passengers
    return await memory.update_profile(db, x_user_id, **fields)


@router.post("/passengers", response_model=UserProfile)
async def add_passenger(
    request: PassengerCreateInput,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    profile = await memory.get_profile(db, x_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    new_passenger = request.model_dump()
    return await memory.update_profile(db, x_user_id, passengers=[new_passenger])


@router.put("/passengers/{passenger_id}", response_model=UserProfile)
async def update_passenger(
    passenger_id: str,
    request: PassengerUpdateInput,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    profile = await memory.get_profile(db, x_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    from app.models.database import UserProfileRow
    from sqlalchemy import select
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == x_user_id))
    row = res.scalars().first()
    if not row or not row.passengers:
        raise HTTPException(status_code=404, detail="乘客未找到")
    
    updated_passengers = []
    found = False
    for p in row.passengers:
        if str(p.get("passenger_id") or "") == passenger_id:
            found = True
            item = dict(p)
            for k, v in request.model_dump(exclude_unset=True).items():
                if v is not None:
                    item[k] = v
            # 若本人编辑，锁定 role="self" 与 passenger_id="0"
            if passenger_id == "0":
                item["role"] = "self"
                item["passenger_id"] = "0"
            updated_passengers.append(item)
        else:
            updated_passengers.append(p)
    if not found:
        raise HTTPException(status_code=404, detail="乘客未找到")
    row.passengers = updated_passengers
    await db.commit()
    return await memory.get_profile(db, x_user_id)


@router.delete("/passengers/{passenger_id}", response_model=UserProfile)
async def delete_passenger(
    passenger_id: str,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    profile = await memory.get_profile(db, x_user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="画像不存在")
    if passenger_id == "0":
        raise HTTPException(status_code=400, detail="本人乘客不可删除")
    from app.models.database import UserProfileRow
    from sqlalchemy import select
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == x_user_id))
    row = res.scalars().first()
    if row and row.passengers:
        row.passengers = [p for p in row.passengers if str(p.get("passenger_id") or "") != passenger_id]
        await db.commit()
    return await memory.get_profile(db, x_user_id)


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


@memory_router.get("/events")
async def list_user_events(
    limit: int = 50,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """获取操作者决策行为事件列表（User L2 Events）"""
    from sqlalchemy import select, desc
    from app.models.database import UserMemoryEventRow

    safe_limit = max(1, min(100, limit))
    stmt = (
        select(UserMemoryEventRow)
        .where(UserMemoryEventRow.user_id == x_user_id)
        .order_by(desc(UserMemoryEventRow.created_at))
        .limit(safe_limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    events = []
    for r in rows:
        events.append({
            "id": r.id,
            "userId": r.user_id,
            "eventType": r.event_type,
            "sessionId": r.session_id,
            "taskId": r.task_id,
            "traceId": r.trace_id,
            "orderNo": r.order_no,
            "context": r.context or {},
            "result": r.result or {},
            "createdAt": r.created_at.isoformat() if r.created_at else None,
        })
    return events


@memory_router.get("/distill")
async def get_distill_report(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户 L3 偏好蒸馏 Markdown 报告与结构化偏好"""
    import os
    path = memory._l3_path(x_user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = f"# 用户与乘车人偏好蒸馏（L3）\n\n暂无针对用户 {x_user_id} 的偏好蒸馏记录。"

    profile = await memory.get_profile(db, x_user_id)
    preferences_v2 = (profile.preferences_v2 if profile else {}) or {}
    return {
        "userId": x_user_id,
        "content": content,
        "preferencesV2": preferences_v2,
    }


@memory_router.post("/distill")
async def trigger_distill(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    """手动触发当前用户的 L3 偏好蒸馏并刷新报告与结构化偏好"""
    try:
        content = await memory.distill(db, x_user_id)
    except Exception as e:
        content = f"# 用户与乘车人偏好蒸馏（L3）\n\n蒸馏执行异常或无近期行程更新: {e}"
    profile = await memory.get_profile(db, x_user_id)
    preferences_v2 = (profile.preferences_v2 if profile else {}) or {}
    return {
        "userId": x_user_id,
        "content": content,
        "preferencesV2": preferences_v2,
    }

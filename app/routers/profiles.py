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

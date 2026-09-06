from typing import List

from fastapi import APIRouter, Header, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.schemas import OrderDraftOut
from app.services.runtime import booking

router = APIRouter(prefix="/api/v1/travel/orders", tags=["travel-orders"])


@router.get("", response_model=List[OrderDraftOut])
async def list_orders(
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    return await booking.list_orders(db, x_user_id)


@router.get("/{orderNo}", response_model=OrderDraftOut)
async def get_order(
    orderNo: str,
    x_user_id: int = Header(default=1, alias="X-User-Id"),
    db: AsyncSession = Depends(get_db),
):
    order = await booking.order_detail(db, x_user_id, orderNo)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order

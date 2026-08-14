"""Mock 供应商接口：收银台支付状态，供三层支付检测第 2 层（订单状态轮询）使用。"""

from fastapi import APIRouter

from app.services.mock_supplier import mock_supplier

router = APIRouter(prefix="/api/v1/travel/mock-supplier", tags=["travel-mock-supplier"])


@router.post("/orders/{order_no}/paid")
async def mark_paid(order_no: str):
    """Mock 收银台页面在「模拟支付」后回调，把订单标记为已支付。"""
    row = mock_supplier.mark_paid(order_no)
    return {"order_no": order_no, "status": row["status"], "paid_at": row["paid_at"]}


@router.get("/orders/{order_no}/status")
async def order_status(order_no: str):
    """查询 Mock 供应商支付状态（第 2 层轮询用）。"""
    return {"order_no": order_no, "status": mock_supplier.get_status(order_no)}

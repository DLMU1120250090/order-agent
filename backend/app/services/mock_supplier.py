"""Mock 供应商（模拟数据）：收银台支付状态存储，供三层支付检测的第 2 层轮询使用。"""

import logging
import threading
from datetime import datetime
from typing import Dict, Optional

log = logging.getLogger("travel.mock_supplier")


class MockSupplierService:
    """内存版供应商支付状态表：order_no -> {status: PENDING/PAID, paid_at}。
    真实供应商接入后替换为订单状态查询 API。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._orders: Dict[str, dict] = {}

    def register(self, order_no: str) -> dict:
        with self._lock:
            return self._orders.setdefault(order_no, {"status": "PENDING", "paid_at": None})

    def mark_paid(self, order_no: str) -> Optional[dict]:
        with self._lock:
            row = self._orders.setdefault(order_no, {"status": "PENDING", "paid_at": None})
            if row["status"] != "PAID":
                row["status"] = "PAID"
                row["paid_at"] = datetime.now().isoformat()
                log.info("Mock 供应商收到支付: order_no=%s", order_no)
            return row

    def get_status(self, order_no: str) -> str:
        with self._lock:
            return (self._orders.get(order_no) or {}).get("status", "PENDING")

    def is_paid(self, order_no: str) -> bool:
        return self.get_status(order_no) == "PAID"

    def snapshot(self) -> Dict[str, dict]:
        with self._lock:
            return {k: dict(v) for k, v in self._orders.items()}


mock_supplier = MockSupplierService()

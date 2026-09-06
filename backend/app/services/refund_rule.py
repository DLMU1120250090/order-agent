from datetime import datetime, timedelta
from typing import Dict

from app.models.enums import OrderType


class RefundRuleService:
    """
    动态退改费分档规则表（B1 定稿）。
    - TRAIN：12306 真实政策硬编码（上线前人工核对公告）
    - FLIGHT：Mock 分档（真实以票规为准，企业接入后 airticketOpen.Enrich 返回真实退改规则）
    """

    # (提前量阈值, 退票费率, 改签费率)
    TRAIN_RULES = [
        (timedelta(days=8), 0.00, 0.00),
        (timedelta(hours=48), 0.05, 0.00),
        (timedelta(hours=24), 0.10, 0.00),
        (timedelta(hours=0), 0.20, 0.00),
    ]
    FLIGHT_RULES = [
        (timedelta(hours=48), 0.05, 0.10),
        (timedelta(hours=24), 0.10, 0.20),
        (timedelta(hours=0), 0.20, 0.30),
    ]

    def fee(self, price: float, depart_at: datetime, now: datetime, order_type: str) -> Dict[str, float]:
        """按"当前时间 vs 出发时间"取档，计算退票费与改签费。"""
        delta = depart_at - now
        rules = self.TRAIN_RULES if order_type == OrderType.TRAIN.value else self.FLIGHT_RULES
        refund_rate, change_rate = rules[-1][1], rules[-1][2]
        for threshold, rr, cr in rules:
            if delta >= threshold:
                refund_rate, change_rate = rr, cr
                break
        return {
            "refund_fee": round(price * refund_rate, 2),
            "change_fee": round(price * change_rate, 2),
        }

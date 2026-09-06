"""Commit 2（R2）：User L2 行为事件 单元测试。

运行：cd order-agent && python -m pytest tests/test_user_memory_events.py -q
"""
from datetime import datetime
from types import SimpleNamespace

from app.services.user_memory_events import (
    UserEventType,
    summarize_change_events,
    summarize_price_events,
)


def test_event_type_values_unique():
    values = [
        UserEventType.PRICE_DROP_ACCEPTED,
        UserEventType.PRICE_DROP_IGNORED,
        UserEventType.CHANGE_CONFIRMED,
        UserEventType.CHANGE_REJECTED,
        UserEventType.REFUND_CONFIRMED,
        UserEventType.RECOMMEND_REJECTED,
        UserEventType.RECOMMEND_ACCEPTED,
        UserEventType.MONITOR_TOGGLED,
        UserEventType.REMINDER_SET,
    ]
    assert len(values) == len(set(values))


def _row(event_type, order_no=None, created_at=None):
    return SimpleNamespace(
        event_type=event_type,
        order_no=order_no,
        created_at=created_at or datetime(2026, 9, 6),
    )


def test_summarize_price_events():
    rows = [
        _row(UserEventType.PRICE_DROP_ACCEPTED),
        _row(UserEventType.PRICE_DROP_ACCEPTED),
        _row(UserEventType.PRICE_DROP_IGNORED),
        _row(UserEventType.MONITOR_TOGGLED),
    ]
    stat = summarize_price_events(rows)
    assert stat == {"accepted": 2, "ignored": 1, "total": 3, "acceptRatio": 0.67}
    assert summarize_price_events([])["total"] == 0


def test_summarize_change_events():
    rows = [
        _row(UserEventType.CHANGE_CONFIRMED, "ORD3"),
        _row(UserEventType.REFUND_CONFIRMED, "ORD2"),
        _row(UserEventType.CHANGE_CONFIRMED, "ORD1"),
    ]
    stat = summarize_change_events(rows)
    assert stat["confirmed"] == 2
    assert stat["refunded"] == 1
    assert stat["rejected"] == 0
    assert stat["recent"][0]["orderNo"] == "ORD3"

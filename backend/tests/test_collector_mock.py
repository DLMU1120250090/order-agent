"""Mock 数据生成策略 单元测试（10 条且互不重复、确定性）。

运行：cd backend && python -m pytest tests/test_collector_mock.py -q
"""
from app.services.collector.base import MockDataSource

mock = MockDataSource()


def test_flights_generate_ten_unique_items():
    items = mock.flights("北京", "上海")
    assert len(items) == 10
    vehicle_nos = [it["vehicle_no"] for it in items]
    departs = [it["depart"] for it in items]
    prices = [it["price"] for it in items]
    assert len(set(vehicle_nos)) == 10
    assert len(set(departs)) == 10
    assert len(set(prices)) == 10


def test_trains_generate_ten_unique_items():
    items = mock.trains("北京", "上海")
    assert len(items) == 10
    vehicle_nos = [it["vehicle_no"] for it in items]
    assert len(set(vehicle_nos)) == 10
    assert all(it["seat"] == "二等座" for it in items)


def test_mock_deterministic():
    assert mock.flights("广州", "成都") == mock.flights("广州", "成都")
    assert mock.trains("北京", "上海") == mock.trains("北京", "上海")


def test_train_city_restriction_but_flight_any_city():
    # 大连不在 MOCK_CITIES：火车无候选；航班可生成
    assert mock.trains("大连", "哈尔滨") == []
    assert len(mock.flights("大连", "哈尔滨")) == 10

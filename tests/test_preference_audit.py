"""Commit 0：Memory 写读对齐审计——死偏好逻辑单元测试。

运行：cd order-agent && python -m pytest tests/test_preference_audit.py -q
"""
from app.services.orchestrator import TravelOrchestratorService
from app.services.scheduler import price_monitor_enabled


def test_price_monitor_default_on():
    assert price_monitor_enabled(None) is True
    assert price_monitor_enabled({}) is True


def test_price_monitor_toggle():
    assert price_monitor_enabled({"price_monitor": True}) is True
    assert price_monitor_enabled({"price_monitor": False}) is False
    assert price_monitor_enabled({"early_bird": True}) is True


def test_early_departure_detection():
    assert TravelOrchestratorService._is_early_departure("07:30") is True
    assert TravelOrchestratorService._is_early_departure("06:00") is True
    assert TravelOrchestratorService._is_early_departure("08:00") is False
    assert TravelOrchestratorService._is_early_departure("09:05") is False
    assert TravelOrchestratorService._is_early_departure("") is False
    assert TravelOrchestratorService._is_early_departure("not-a-time") is False

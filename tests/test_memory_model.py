"""Commit 1：Memory 数据模型——乘客归一化/合并、偏好 v2 解析/合并纯函数测试。

运行：cd order-agent && python -m pytest tests/test_memory_model.py -q
"""
from app.crud.profile import (
    merge_passengers,
    merge_preferences_v2,
    normalize_passengers,
    resolve_preference,
)


def test_normalize_passengers_fills_id_and_role():
    out = normalize_passengers([{"name": "张三", "id_no": "110101199001011234"}])
    assert out[0]["passenger_id"].startswith("P_")
    assert out[0]["role"] == "self"


def test_passenger_id_stable_and_unique():
    a = normalize_passengers([{"name": "张三", "id_no": "110101199001011234"}])[0]["passenger_id"]
    b = normalize_passengers([{"name": "李四", "id_no": "110101199001011234"}])[0]["passenger_id"]
    assert a == b
    two = normalize_passengers([
        {"name": "张三", "id_no": "A"},
        {"name": "李四", "id_no": "B"},
    ])
    assert two[0]["role"] == "self"
    assert two[1]["role"] == "companion"
    assert two[0]["passenger_id"] != two[1]["passenger_id"]


def test_merge_passengers_keeps_old_role_and_extra_passenger():
    existing = normalize_passengers([
        {"name": "张三", "id_no": "A", "role": "self", "id_expiry": "2030-01-01"},
        {"name": "李四", "id_no": "B"},
    ])
    incoming = [{"name": "张三", "id_no": "A", "id_expiry": "2035-01-01"}]
    merged = merge_passengers(existing, incoming)
    zhang = next(p for p in merged if p["name"] == "张三")
    assert zhang["role"] == "self"
    assert zhang["id_expiry"] == "2035-01-01"
    assert any(p["name"] == "李四" for p in merged)


def test_merge_preferences_v2_deep_merge():
    old = {
        "user": {"price_sensitivity": {"value": "high", "source": "rule"}},
        "passengers": {"P_A": {"transport": {"value": "train", "source": "distilled"}}},
    }
    new = {
        "user": {"budget_habit": {"value": "economy", "source": "rule", "confidence": 0.9}},
        "passengers": {"P_A": {"seat": {"value": "aisle", "source": "rule"}}},
    }
    merged = merge_preferences_v2(old, new)
    assert merged["user"]["price_sensitivity"]["value"] == "high"
    assert merged["user"]["budget_habit"]["confidence"] == 0.9
    assert merged["passengers"]["P_A"]["transport"]["value"] == "train"
    assert merged["passengers"]["P_A"]["seat"]["value"] == "aisle"


def test_resolve_preference_precedence():
    v2 = {
        "user": {"transport": {"value": "flight", "source": "rule"}},
        "passengers": {"P_A": {"transport": {"value": "train", "source": "distilled"}}},
    }
    flat = {"early_bird": True}
    assert resolve_preference(v2, flat, "transport", passenger_id="P_A")["value"] == "train"
    assert resolve_preference(v2, flat, "transport")["value"] == "flight"
    assert resolve_preference(None, flat, "early_bird")["value"] is True
    assert resolve_preference(None, flat, "early_bird")["source"] == "legacy_flat"
    assert resolve_preference(None, None, "missing") is None

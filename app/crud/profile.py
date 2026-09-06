import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import UserProfileRow
from app.models.schemas import UserProfile


# ---------- 纯函数：乘客与偏好结构（Commit 1，可单测） ----------

def _new_passenger_id(p: dict) -> str:
    """由证件号（兜底姓名）生成稳定 passenger_id（id_no sha256 前 12 位）。"""
    raw = str(p.get("id_no") or p.get("name") or "passenger").strip()
    return "P_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def normalize_passengers(passengers) -> list:
    """给乘客列表补齐 passenger_id / role 并按 passenger_id 去重（同一乘客只保留一条）。

    缺省 role：首个 self，其余 companion；已存在的值不覆盖。
    """
    out = []
    seen = set()
    for idx, raw in enumerate(passengers or []):
        item = dict(raw)
        if not item.get("passenger_id"):
            item["passenger_id"] = _new_passenger_id(item)
        pid = str(item["passenger_id"])
        if pid in seen:
            continue
        seen.add(pid)
        if "role" not in item:
            item["role"] = "self" if idx == 0 else "companion"
        out.append(item)
    return out


def merge_passengers(existing, incoming) -> list:
    """乘客簿合并：incoming 为主，按 passenger_id/id_no/name 匹配旧项。

    - 匹配到的旧项保留未传字段（passenger_id / role 等），避免支付回写整表覆盖丢字段；
    - incoming 先归一化（补 passenger_id/role）再匹配，杜绝"已有 P_ 前缀 id 而原始乘客按
      证件号匹配不上"导致的重复追加（修复 2026-09-06）；
    - 未匹配的旧项追加保留（乘客簿不清空，删除留待后续显式能力）。
    """
    existing = normalize_passengers(existing)
    incoming = incoming or []
    if not incoming:
        return existing
    incoming = normalize_passengers(incoming)
    result = []
    seen = set()
    for item in incoming:
        pid = str(item["passenger_id"])
        if pid in seen:
            continue
        matched = next((old for old in existing if str(old.get("passenger_id")) == pid), None)
        if matched:
            merged = dict(matched)
            merged.update(item)
            item = merged
        result.append(item)
        seen.add(pid)
    for old in existing:
        if str(old.get("passenger_id")) not in seen:
            result.append(dict(old))
    return result


def merge_preferences_v2(old, new) -> dict:
    """preferences_v2 合并：user / passengers 两级各自按 key 覆盖更新。"""
    old = old or {}
    new = new or {}
    out = {
        "user": dict(old.get("user") or {}),
        "passengers": {str(pid): dict(prefs) for pid, prefs in (old.get("passengers") or {}).items()},
    }
    if new.get("user"):
        out["user"].update(dict(new["user"]))
    for pid, prefs in (new.get("passengers") or {}).items():
        bucket = out["passengers"].setdefault(str(pid), {})
        bucket.update(dict(prefs))
    return out


def resolve_preference(preferences_v2, flat_preferences, key: str, passenger_id: Optional[str] = None) -> Optional[dict]:
    """统一偏好解析：passenger 级 v2 > user 级 v2 > flat（legacy）。返回条目 dict 或 None。"""
    v2 = preferences_v2 or {}
    if passenger_id:
        passenger_entry = ((v2.get("passengers") or {}).get(str(passenger_id)) or {}).get(key)
        if passenger_entry is not None:
            return passenger_entry
    user_entry = ((v2.get("user") or {}) or {}).get(key)
    if user_entry is not None:
        return user_entry
    flat = flat_preferences or {}
    if key in flat:
        return {"value": flat[key], "source": "legacy_flat"}
    return None


# ---------- 数据库读写 ----------

async def get_profile(db: AsyncSession, user_id: int) -> Optional[UserProfile]:
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == user_id))
    row = res.scalars().first()
    if not row:
        return None
    return UserProfile(
        user_id=row.user_id,
        home_city=row.home_city,
        passengers=row.passengers or [],
        budget_level=row.budget_level,
        preferences=row.preferences or {},
        preferences_v2=row.preferences_v2 or {},
    )


async def update_profile(db: AsyncSession, user_id: int, **fields):
    res = await db.execute(select(UserProfileRow).where(UserProfileRow.user_id == user_id))
    row = res.scalars().first()
    if not row:
        row = UserProfileRow(user_id=user_id)
        db.add(row)
    if "home_city" in fields:
        row.home_city = fields["home_city"]
    if "passengers" in fields:
        row.passengers = merge_passengers(row.passengers, fields["passengers"])
    if "budget_level" in fields:
        row.budget_level = fields["budget_level"]
    if "preferences" in fields:
        prefs = dict(row.preferences or {})
        prefs.update(fields["preferences"])
        row.preferences = prefs
    if "preferences_v2" in fields:
        row.preferences_v2 = merge_preferences_v2(row.preferences_v2, fields["preferences_v2"])
    await db.commit()
    return await get_profile(db, user_id)

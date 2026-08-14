import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from cachetools import TTLCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import DataCacheRow

log = logging.getLogger("travel.collector.cache")


class CachePolicy:
    """
    数据采集缓存 + 重试 + 降级包装（C1 定稿）。
    - 内存 TTLCache 作为第一层
    - data_cache 表作为跨进程兜底（stale 缓存降级）
    - 失败重试：指数退避 1m/5m/15m（Mock 模式单次尝试，避免演示阻塞）
    """

    def __init__(self, memory_ttl: int = 300, retry_delays=(60, 300, 900)):
        self.memory = TTLCache(maxsize=512, ttl=memory_ttl)
        self.retry_delays = retry_delays

    async def with_policy(
        self,
        db: AsyncSession,
        cache_key: str,
        fetch_fn: Callable[[], Any],
        ttl_seconds: int = 300,
        retries: int = 3,
        stale_ok: bool = True,
    ) -> tuple:
        """
        返回 (payload, from_cache, stale)
        - payload: 数据
        - from_cache: 是否来自缓存
        - stale: 是否为过期缓存降级
        """
        # 1. 内存 LRU
        if cache_key in self.memory:
            return self.memory[cache_key], True, False

        # 2. DB 缓存（未过期）
        row = await self._db_get(db, cache_key)
        if row and row.expire_at and row.expire_at > datetime.utcnow():
            payload = row.payload
            self.memory[cache_key] = payload
            return payload, True, False

        # 3. 调用数据源（带重试）
        last_error: Optional[Exception] = None
        attempts = 1 if retries <= 0 else retries
        for i in range(attempts):
            try:
                payload = await fetch_fn()
                self.memory[cache_key] = payload
                await self._db_put(db, cache_key, payload, ttl_seconds)
                return payload, False, False
            except Exception as e:  # noqa: BLE001
                last_error = e
                if i < attempts - 1:
                    delay = self.retry_delays[min(i, len(self.retry_delays) - 1)]
                    if settings_mock_mode():
                        break  # Mock 模式不实际等待退避
                    await asyncio.sleep(delay)

        # 4. 全部失败：stale 缓存降级
        if stale_ok and row and row.payload is not None:
            log.warning("数据源失败，使用过期缓存降级。key=%s error=%s", cache_key, last_error)
            self.memory[cache_key] = row.payload
            return row.payload, True, True

        raise last_error or RuntimeError(f"数据源不可达: {cache_key}")

    async def _db_get(self, db: AsyncSession, cache_key: str) -> Optional[DataCacheRow]:
        try:
            res = await db.execute(select(DataCacheRow).where(DataCacheRow.cache_key == cache_key))
            return res.scalars().first()
        except Exception:  # noqa: BLE001
            return None

    async def _db_put(self, db: AsyncSession, cache_key: str, payload: Any, ttl_seconds: int):
        try:
            row = await self._db_get(db, cache_key)
            if not row:
                row = DataCacheRow(cache_key=cache_key)
                db.add(row)
            row.payload = payload if isinstance(payload, (dict, list)) else {"value": payload}
            row.expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
            await db.commit()
        except Exception as e:  # noqa: BLE001
            log.warning("data_cache 写入失败: %s", e)


def settings_mock_mode() -> bool:
    from app.config import settings
    return bool(settings.TRAVEL_MOCK_MODE)

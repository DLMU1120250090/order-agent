import hashlib
import logging
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import PoiStationRow, TransferTimeCacheRow
from app.models.schemas import GeoPoint
from app.services.collector.base import MockDataSource, build_qweather_token, is_mock_mode
from app.services.collector.cache import CachePolicy

log = logging.getLogger("travel.collector.geo")


class GeoAdapter:
    """
    地理适配器（高德 geocode → 和风 GeoAPI → poi_station 种子表 → Mock）。
    """

    AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"

    def __init__(self, cache: CachePolicy, mock: MockDataSource):
        self.cache = cache
        self.mock = mock

    async def geocode(self, db: AsyncSession, city: str) -> GeoPoint:
        cache_key = f"geocode:{city}"

        async def fetch():
            if not is_mock_mode():
                try:
                    point = await self._amap_geocode(city)
                    if point:
                        return point
                    log.warning("高德地理编码不可用（可能 key 平台不匹配），尝试和风 GeoAPI: %s", city)
                    point = await self._qweather_geocode(city)
                    if point:
                        return point
                except Exception as e:  # noqa: BLE001
                    log.warning("真实地理编码失败，回退种子表/Mock: city=%s err=%s", city, e)
            # 优先查 poi_station 种子表（城市级）
            res = await db.execute(select(PoiStationRow).where(PoiStationRow.city == city).limit(1))
            row = res.scalars().first()
            if row:
                return GeoPoint(city=city, name=city, kind="city", lat=row.lat or 0.0, lng=row.lng or 0.0).model_dump()
            return self.mock.geocode(city)

        payload, _, _ = await self.cache.with_policy(db, cache_key, fetch, ttl_seconds=86400)
        return GeoPoint(**payload)

    async def _amap_geocode(self, city: str) -> Optional[Dict]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_AMAP_KEY:
            return None
        params = {"address": city, "key": settings.TRAVEL_AMAP_KEY}
        if settings.TRAVEL_AMAP_SECURITY_KEY:
            base = "".join(f"{k}{params[k]}" for k in sorted(params))
            params["sig"] = hashlib.sha1((base + settings.TRAVEL_AMAP_SECURITY_KEY).encode("utf-8")).hexdigest()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self.AMAP_GEOCODE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != "1":
            return None
        geocodes = data.get("geocodes") or []
        if not geocodes:
            return None
        loc = (geocodes[0].get("location") or "").split(",")
        if len(loc) != 2:
            return None
        return {"city": city, "name": city, "kind": "city", "lat": float(loc[1]), "lng": float(loc[0])}

    async def _qweather_geocode(self, city: str) -> Optional[Dict]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_QWEATHER_PROJECT_ID:
            return None
        url = settings.TRAVEL_QWEATHER_API_HOST.rstrip("/") + "/geo/v2/city/lookup"
        headers = {"Authorization": f"Bearer {build_qweather_token()}"}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={"location": city}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if data.get("code") != "200":
            return None
        locations = data.get("location") or []
        if not locations:
            return None
        first = locations[0]
        return {
            "city": city,
            "name": first.get("name") or city,
            "kind": "city",
            "lat": float(first.get("lat") or 0.0),
            "lng": float(first.get("lon") or 0.0),
        }

    async def transfer_minutes(self, db: AsyncSession, from_name: str, to_name: str) -> int:
        cache_key = f"transfer:{from_name}:{to_name}"

        async def fetch():
            res = await db.execute(
                select(TransferTimeCacheRow).where(
                    TransferTimeCacheRow.from_key == from_name,
                    TransferTimeCacheRow.to_key == to_name,
                )
            )
            row = res.scalars().first()
            if row:
                return {"minutes": row.minutes}
            return {"minutes": self.mock.transfer_minutes(from_name, to_name)}

        payload, _, _ = await self.cache.with_policy(db, cache_key, fetch, ttl_seconds=2592000)  # TTL 30 天
        return int(payload.get("minutes", 30))

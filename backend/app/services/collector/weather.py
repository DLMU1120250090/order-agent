import logging
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import HourlyWeather
from app.services.collector.base import MockDataSource, build_qweather_token, is_mock_mode
from app.services.collector.cache import CachePolicy

log = logging.getLogger("travel.collector.weather")


class WeatherAdapter:
    """
    天气适配器（和风逐小时预报，JWT 认证）。
    真实模式请求：
    GET https://{api-host}/v7/weather/24h?location={lng},{lat}
    """

    def __init__(self, cache: CachePolicy, mock: MockDataSource):
        self.cache = cache
        self.mock = mock

    async def hourly(self, db: AsyncSession, lat: float, lng: float, hours: int = 24) -> List[HourlyWeather]:
        cache_key = f"weather:{lat:.3f}:{lng:.3f}:{hours}"

        async def fetch():
            if not is_mock_mode():
                try:
                    return await self._fetch_real(lat, lng, hours)
                except Exception as e:  # noqa: BLE001
                    log.warning("和风天气接口调用失败，回退 Mock: lat=%s lng=%s err=%s", lat, lng, e)
            return self.mock.hourly_weather(lat, lng, hours)

        payload, _, _ = await self.cache.with_policy(db, cache_key, fetch, ttl_seconds=1800)
        return [HourlyWeather(**item) for item in payload]

    async def _fetch_real(self, lat: float, lng: float, hours: int = 24) -> List[dict]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_QWEATHER_API_HOST or not settings.TRAVEL_QWEATHER_PROJECT_ID:
            return self.mock.hourly_weather(lat, lng, hours)
        url = settings.TRAVEL_QWEATHER_API_HOST.rstrip("/") + "/v7/weather/24h"
        headers = {"Authorization": f"Bearer {build_qweather_token()}"}
        params = {"location": f"{lng:.6f},{lat:.6f}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        if data.get("code") != "200":
            raise RuntimeError(f"和风接口业务错误: code={data.get('code')}")

        out = []
        for item in (data.get("hourly") or [])[:hours]:
            temp = self._to_float(item.get("temp"))
            out.append({
                "time": str(item.get("fxTime") or ""),
                "temp": temp,
                "feels_like": temp,  # 24h 预报无体感温度，用气温兜底
                "wind": f"{item.get('windDir') or ''} {item.get('windScale') or ''}".strip(),
                "precip_prob": round(self._to_float(item.get("pop")) / 100.0, 2),
                "text": str(item.get("text") or "晴"),
            })
        if not out:
            raise RuntimeError("和风接口返回为空")
        return out

    @staticmethod
    def _to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

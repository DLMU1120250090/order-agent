import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.collector.base import MockDataSource, is_mock_mode
from app.services.collector.cache import CachePolicy

log = logging.getLogger("travel.collector.train")

# 站站查询返回的价格字段 → 座席名（按优先级取第一个有值字段）
PRICE_FIELDS: List[Tuple[str, str]] = [
    ("priceed", "二等座"),
    ("priceyz", "硬座"),
    ("priceyd", "一等座"),
    ("pricewz", "无座"),
    ("priceyw", "硬卧"),
    ("pricesw", "商务座"),
    ("pricerz", "软座"),
    ("pricerw", "软卧"),
    ("pricegr", "高级软卧"),
]


class TrainAdapter:
    """
    火车数据适配器（阿里云市场 cmapi011240 极速数据，APPCODE 认证）。
    真实模式请求站站查询：
    GET https://jisutrain.market.alicloudapi.com/train/station2s?start=..&end=..&date=..
    """

    API_URL = "https://jisutrain.market.alicloudapi.com/train/station2s"

    def __init__(self, cache: CachePolicy, mock: MockDataSource):
        self.cache = cache
        self.mock = mock

    async def search(self, db: AsyncSession, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        cache_key = f"train:{origin}:{destination}:{date}"

        async def fetch():
            if is_mock_mode():
                return self.mock.trains(origin, destination)
            try:
                return await self._fetch_real(origin, destination, date)
            except Exception as e:  # noqa: BLE001
                log.warning("火车接口调用失败，回退 Mock: origin=%s dest=%s err=%s", origin, destination, e)
                return self.mock.trains(origin, destination)

        payload, _, _ = await self.cache.with_policy(db, cache_key, fetch, ttl_seconds=300)
        return list(payload)

    async def _fetch_real(self, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_ALIYUN_APPCODE:
            return self.mock.trains(origin, destination)

        headers = {"Authorization": f"APPCODE {settings.TRAVEL_ALIYUN_APPCODE}"}
        params = {"start": origin, "end": destination, "date": date}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(self.API_URL, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
            else:
                # 网关把业务错误映射为 4xx/5xx，body 仍是极速数据 JSON（如 203 没有信息）
                try:
                    data = resp.json()
                except Exception:  # noqa: BLE001
                    resp.raise_for_status()
                    return []

        if data.get("status") != 0:
            if str(data.get("status")) in ("202", "203"):
                # 参数缺失/无直达车：视为无数据
                return []
            raise RuntimeError(f"火车接口业务错误: {data.get('msg')}")

        items = (data.get("result") or {}).get("list") or []
        out: List[Dict[str, Any]] = []
        for item in items:
            price, seat = self._pick_price(item)
            if price is None:
                continue
            out.append({
                "mode": "TRAIN",
                "from_city": origin,
                "to_city": destination,
                "from_station": str(item.get("station") or origin),
                "to_station": str(item.get("endstation") or destination),
                "arrive_day": int(item.get("day") or 1),
                "depart": str(item.get("departuretime") or ""),
                "arrive": str(item.get("arrivaltime") or ""),
                "price": price,
                "vehicle_no": str(item.get("trainno") or ""),
                "seat": seat,
                "carrier": str(item.get("typename") or "高铁"),
                "remaining": 99,
            })
        return out

    @staticmethod
    def _pick_price(item: Dict[str, Any]) -> Tuple[Optional[float], str]:
        for field, label in PRICE_FIELDS:
            raw = item.get(field)
            if raw is None or str(raw) in ("", "-"):
                continue
            try:
                return float(raw), label
            except (TypeError, ValueError):
                continue
        return None, "二等座"

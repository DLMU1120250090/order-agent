import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.collector.base import MockDataSource, is_mock_mode
from app.services.collector.cache import CachePolicy

log = logging.getLogger("travel.collector.flight")

# 城市 → 机场三字码（航班接口 depCode/arrCode 使用）
CITY_CODES: Dict[str, str] = {
    "北京": "BJS", "上海": "SHA", "广州": "CAN", "深圳": "SZX", "成都": "CTU",
    "杭州": "HGH", "西安": "XIY", "重庆": "CKG", "南京": "NKG", "武汉": "WUH",
    "天津": "TSN", "青岛": "TAO", "济南": "TNA", "厦门": "XMN", "福州": "FOC",
    "昆明": "KMG", "长沙": "CSX", "郑州": "CGO", "沈阳": "SHE", "哈尔滨": "HRB",
    "长春": "CGQ", "贵阳": "KWE", "南宁": "NNG", "海口": "HAK", "三亚": "SYX",
    "乌鲁木齐": "URC", "兰州": "LHW", "太原": "TYN", "合肥": "HFE", "南昌": "KHN",
    "石家庄": "SJW", "呼和浩特": "HET", "银川": "INC", "西宁": "XNN", "拉萨": "LXA",
    "无锡": "WUX", "宁波": "NGB", "温州": "WNZ", "珠海": "ZUH", "大连": "DLC",
    "赣州": "KOW", "烟台": "YNT", "徐州": "XUZ", "洛阳": "LYA",
}

# 熔断：上游服务商后端不可达（如 504）时，短期内跳过真实调用直接回退 Mock
_FLIGHT_BROKEN_UNTIL: float = 0.0
_FLIGHT_BROKEN_WINDOW = 600
# 旧航班 API（cmapi028585）后端长期不可达，进程内首次失败后不再重试
_AIRINFO_DEAD = False


class FlightAdapter:
    """
    航班数据适配器。
    主源：聚美智数（cmapi00074571）POST /flight/detail，form: depCode/arrCode/depDate
    兜底：cmapi028585 POST /airInfos（HTTP-only），form: leave_code/arrive_code/query_date
    全部失败后由 search() 回退 Mock（含熔断）。
    """

    JUMEI_API_URL = "https://jmfjhb.market.alicloudapi.com/flight/detail"
    API_URL = "http://airinfo.market.alicloudapi.com/airInfos"
    MAX_RESULTS = 30

    def __init__(self, cache: CachePolicy, mock: MockDataSource):
        self.cache = cache
        self.mock = mock

    async def search(self, db: AsyncSession, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        cache_key = f"flight:{origin}:{destination}:{date}"

        async def fetch():
            if is_mock_mode():
                return self.mock.flights(origin, destination)
            global _FLIGHT_BROKEN_UNTIL
            if time.time() < _FLIGHT_BROKEN_UNTIL:
                log.info("航班接口处于熔断窗口，直接回退 Mock")
                return self.mock.flights(origin, destination)
            try:
                return await self._fetch_real(origin, destination, date)
            except Exception as e:  # noqa: BLE001
                _FLIGHT_BROKEN_UNTIL = time.time() + _FLIGHT_BROKEN_WINDOW
                log.warning("航班接口调用失败，进入 %ss 熔断并回退 Mock: origin=%s dest=%s err=%s",
                            _FLIGHT_BROKEN_WINDOW, origin, destination, e)
                return self.mock.flights(origin, destination)

        payload, _, _ = await self.cache.with_policy(db, cache_key, fetch, ttl_seconds=300)
        return list(payload)

    async def _fetch_real(self, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        global _FLIGHT_BROKEN_UNTIL
        if time.time() < _FLIGHT_BROKEN_UNTIL:
            raise RuntimeError("航班接口处于熔断窗口")
        errors = []
        try:
            items = await self._fetch_jumei(origin, destination, date)
            if items:
                return items
            errors.append("聚美智数返回为空")
        except Exception as e:  # noqa: BLE001
            errors.append(f"聚美智数: {e}")
        global _AIRINFO_DEAD
        if not _AIRINFO_DEAD:
            try:
                items = await self._fetch_airinfo(origin, destination, date)
                if items:
                    return items
                errors.append("旧航班API返回为空")
            except Exception as e:  # noqa: BLE001
                _AIRINFO_DEAD = True
                errors.append(f"旧航班API: {e}")
        raise RuntimeError("; ".join(errors))

    async def _fetch_jumei(self, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_ALIYUN_APPCODE:
            return []
        leave_code = CITY_CODES.get(origin)
        arrive_code = CITY_CODES.get(destination)
        if not leave_code or not arrive_code:
            return []

        headers = {"Authorization": f"APPCODE {settings.TRAVEL_ALIYUN_APPCODE}"}
        data = {"depCode": leave_code, "arrCode": arrive_code, "depDate": date}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self.JUMEI_API_URL, data=data, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        if not payload.get("success") or str(payload.get("code")) not in ("200", "0"):
            raise RuntimeError(f"聚美智数业务错误: code={payload.get('code')} msg={payload.get('msg')}")

        items = ((payload.get("data") or {}).get("list")) or []
        out = []
        for item in items:
            price = self._first(item.get("price") or {}, ("adultPrice", "price"))
            if price is None:
                continue
            out.append({
                "mode": "FLIGHT",
                "from_city": origin,
                "to_city": destination,
                "from_station": str(item.get("departureAirportName") or origin),
                "to_station": str(item.get("arrivalAirportName") or destination),
                "arrive_day": 1,
                "depart": self._time_only(item.get("departureDateTime")),
                "arrive": self._time_only(item.get("arrivalDateTime")),
                "price": float(price),
                "vehicle_no": str(item.get("operateFlightNo") or item.get("flightNo") or ""),
                "seat": "经济舱",
                "carrier": str(item.get("operateAirlineName") or item.get("airlineName") or ""),
                "remaining": 99,
            })
        out.sort(key=lambda x: x["price"])
        return out[: self.MAX_RESULTS]

    async def _fetch_airinfo(self, origin: str, destination: str, date: str) -> List[Dict[str, Any]]:
        import httpx

        from app.config import settings

        if not settings.TRAVEL_ALIYUN_APPCODE:
            return []
        leave_code = CITY_CODES.get(origin)
        arrive_code = CITY_CODES.get(destination)
        if not leave_code or not arrive_code:
            return []

        headers = {"Authorization": f"APPCODE {settings.TRAVEL_ALIYUN_APPCODE}"}
        data = {"leave_code": leave_code, "arrive_code": arrive_code, "query_date": date}
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.post(self.API_URL, data=data, headers=headers)
            resp.raise_for_status()
            payload = resp.json()

        items = self._extract_items(payload)
        out: List[Dict[str, Any]] = []
        for item in items:
            depart = self._first(item, ("departtime", "depart_time", "departureTime", "starttime"))
            arrive = self._first(item, ("arrivetime", "arrive_time", "arrivalTime", "endtime"))
            price = self._first(item, ("price", "minprice", "lowestprice", "ticketprice", "adultprice"))
            if price is None:
                continue
            out.append({
                "mode": "FLIGHT",
                "from_city": origin,
                "to_city": destination,
                "from_station": str(self._first(item, ("departureAirportName", "leaveAirportName", "departure_airport")) or origin),
                "to_station": str(self._first(item, ("arrivalAirportName", "arriveAirportName", "arrival_airport")) or destination),
                "arrive_day": 1,
                "depart": str(depart or ""),
                "arrive": str(arrive or ""),
                "price": float(price),
                "vehicle_no": str(self._first(item, ("flightno", "flight_no", "flight", "fno")) or ""),
                "seat": "经济舱",
                "carrier": str(self._first(item, ("airline", "carrier", "company")) or ""),
                "remaining": 99,
            })
        if not out:
            raise RuntimeError("航班接口返回为空")
        return out

    @staticmethod
    def _time_only(value) -> str:
        if not value:
            return ""
        s = str(value)
        if " " in s:
            s = s.split(" ", 1)[1]
        return s[:5]

    @staticmethod
    def _extract_items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = payload.get("result") or {}
        if isinstance(result, list):
            return [i for i in result if isinstance(i, dict)]
        if isinstance(result, dict):
            for key in ("list", "flights", "flightList", "data"):
                val = result.get(key)
                if isinstance(val, list):
                    return [i for i in val if isinstance(i, dict)]
        for key in ("list", "flights", "flightList", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [i for i in val if isinstance(i, dict)]
        return []

    @staticmethod
    def _first(item: Dict[str, Any], keys: tuple) -> Optional[Any]:
        for k in keys:
            v = item.get(k)
            if v is not None and str(v) not in ("", "-"):
                return v
        return None

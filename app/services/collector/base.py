import hashlib
from typing import List, Dict, Any

from app.config import settings


# Mock 支持的城市集合（与 sql/travel_tables.sql 中 poi_station 种子保持一致）
MOCK_CITIES = ["北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "重庆", "南京", "武汉"]
MOCK_AIRLINES = ["国航", "东航", "南航", "川航", "海航"]

# 全量已知城市（规则兜底/中转枢纽用；真实 API 支持任意站点）
KNOWN_CITIES = list(dict.fromkeys(MOCK_CITIES + [
    "天津", "青岛", "济南", "厦门", "福州", "昆明", "长沙", "郑州", "沈阳", "哈尔滨",
    "长春", "贵阳", "南宁", "海口", "三亚", "乌鲁木齐", "兰州", "太原", "合肥", "南昌",
    "石家庄", "呼和浩特", "银川", "西宁", "拉萨", "无锡", "宁波", "温州", "珠海",
    "大连", "赣州", "烟台", "徐州", "洛阳",
]))


class MockDataSource:
    """
    内置模拟数据源（当前阶段演示用）。
    所有数据由城市对+槽位索引确定性生成，保证同一次查询结果稳定可复现。
    """

    def _seed(self, origin: str, destination: str) -> int:
        return sum(ord(c) for c in f"{origin}:{destination}")

    def _city_lat_lng(self, city: str) -> tuple:
        table = {
            "北京": (40.0799, 116.6031), "上海": (31.1979, 121.3363),
            "广州": (23.3924, 113.2988), "深圳": (22.6393, 113.8108),
            "成都": (30.5785, 103.9471), "杭州": (30.2295, 120.4344),
            "西安": (34.4471, 108.7516), "重庆": (29.7192, 106.6417),
            "南京": (31.7401, 118.8621), "武汉": (30.7838, 114.2081),
        }
        return table.get(city, (30.0, 110.0))

    def trains(self, origin: str, destination: str) -> List[Dict[str, Any]]:
        if origin not in MOCK_CITIES or destination not in MOCK_CITIES or origin == destination:
            return []
        seed = self._seed(origin, destination)
        out = []
        for i in range(4):
            s = seed + i * 7
            depart_h = 6 + (s % 14)
            duration_h = 3 + (s % 5)
            arrive_h = depart_h + duration_h
            out.append({
                "mode": "TRAIN",
                "from_city": origin,
                "to_city": destination,
                "from_station": f"{origin}站",
                "to_station": f"{destination}站",
                "arrive_day": 1,
                "depart": f"{depart_h:02d}:00",
                "arrive": f"{arrive_h % 24:02d}:00",
                "price": float(180 + (s % 460)),
                "vehicle_no": f"G{1000 + (s % 8000)}",
                "seat": "二等座",
                "remaining": 10 + (s % 90),
            })
        return out

    def flights(self, origin: str, destination: str) -> List[Dict[str, Any]]:
        if origin == destination or not origin or not destination:
            return []
        seed = self._seed(origin, destination)
        out = []
        for i in range(4):
            s = seed + i * 11
            depart_h = 7 + (s % 13)
            duration_h = 1 + (s % 3)
            arrive_h = depart_h + duration_h
            out.append({
                "mode": "FLIGHT",
                "from_city": origin,
                "to_city": destination,
                "from_station": f"{origin}机场",
                "to_station": f"{destination}机场",
                "arrive_day": 1,
                "depart": f"{depart_h:02d}:00",
                "arrive": f"{arrive_h % 24:02d}:00",
                "price": float(180 + (s % 340)),
                "vehicle_no": f"{MOCK_AIRLINES[s % len(MOCK_AIRLINES)]}{s % 9000 + 1000}",
                "seat": "经济舱",
                "remaining": 5 + (s % 120),
            })
        return out

    def geocode(self, city: str) -> Dict[str, Any]:
        lat, lng = self._city_lat_lng(city)
        return {"city": city, "name": city, "kind": "city", "lat": lat, "lng": lng}

    def transfer_minutes(self, from_name: str, to_name: str) -> int:
        if from_name == to_name:
            return 0
        return 30 + (self._seed(from_name, to_name) % 50)

    def hourly_weather(self, lat: float, lng: float, hours: int = 24) -> List[Dict[str, Any]]:
        seed = int(abs(lat * 100)) + int(abs(lng * 100))
        out = []
        from datetime import datetime, timedelta
        base = datetime.now().replace(minute=0, second=0, microsecond=0)
        for i in range(hours):
            t = base + timedelta(hours=i)
            s = seed + i * 3
            out.append({
                "time": t.strftime("%Y-%m-%d %H:00"),
                "temp": float(18 + (s % 16)),
                "feels_like": float(17 + (s % 18)),
                "wind": f"{1 + (s % 5)}级",
                "precip_prob": round(((s % 10) / 10.0), 2),
                "text": "晴" if s % 3 else "多云",
            })
        return out


def is_mock_mode() -> bool:
    """当前是否使用 Mock 数据源"""
    return bool(settings.TRAVEL_MOCK_MODE)


def build_qweather_token() -> str:
    """生成和风天气 JWT（header kid=凭据ID，payload sub=项目ID，EdDSA 签名）。"""
    import time
    import jwt

    now = int(time.time())
    payload = {
        "sub": settings.TRAVEL_QWEATHER_PROJECT_ID,
        "iat": now - 30,
        "exp": now + 900,
    }
    headers = {"kid": settings.TRAVEL_QWEATHER_CREDENTIAL_ID}
    return jwt.encode(payload, settings.qweather_private_key(), algorithm="EdDSA", headers=headers)

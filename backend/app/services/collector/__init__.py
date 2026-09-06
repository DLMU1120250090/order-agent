from app.services.collector.base import MockDataSource
from app.services.collector.train import TrainAdapter
from app.services.collector.flight import FlightAdapter
from app.services.collector.geo import GeoAdapter
from app.services.collector.weather import WeatherAdapter
from app.services.collector.cache import CachePolicy


class DataCollectorService:
    """
    数据采集适配层（C1 定稿）。
    统一数据模型屏蔽各家差异；供应商可替换：
    - Mock 模式（当前阶段）：TRAVEL_MOCK_MODE=true 或密钥缺失时，全部走内置模拟数据
    - 真实模式：对接阿里云市场（火车/航班）+ 高德（地理/路线）+ 和风（天气）
    """

    def __init__(self):
        self.cache_policy = CachePolicy()
        self.mock = MockDataSource()
        self.train = TrainAdapter(self.cache_policy, self.mock)
        self.flight = FlightAdapter(self.cache_policy, self.mock)
        self.geo = GeoAdapter(self.cache_policy, self.mock)
        self.weather = WeatherAdapter(self.cache_policy, self.mock)

    async def search_transport(self, db, origin: str, destination: str, date: str):
        """统一查询：返回 [{mode, from_city, to_city, depart, arrive, price, vehicle_no, seat}]"""
        return await self.train.search(db, origin, destination, date)

    async def search_trains(self, db, origin: str, destination: str, date: str):
        return await self.train.search(db, origin, destination, date)

    async def search_flights(self, db, origin: str, destination: str, date: str):
        return await self.flight.search(db, origin, destination, date)

    async def geocode(self, db, city: str):
        return await self.geo.geocode(db, city)

    async def transfer_minutes(self, db, from_name: str, to_name: str) -> int:
        return await self.geo.transfer_minutes(db, from_name, to_name)

    async def hourly_weather(self, db, lat: float, lng: float, hours: int = 24):
        return await self.weather.hourly(db, lat, lng, hours)

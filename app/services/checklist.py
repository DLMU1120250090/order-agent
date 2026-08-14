import json
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checklist import ChecklistAgent
from app.models.schemas import HourlyWeather, TransportLeg
from app.services.weather_advice import WeatherAdvisoryService


class ChecklistService:
    """出行清单生成（C4 定稿）：LLM 生成 + 模板兜底。"""

    def __init__(self, agent: Optional[ChecklistAgent] = None, weather_advice: Optional[WeatherAdvisoryService] = None):
        self.agent = agent or ChecklistAgent()
        self.weather_advice = weather_advice or WeatherAdvisoryService()

    async def generate(
        self,
        db: AsyncSession,
        legs: List[TransportLeg],
        destination: str,
        weather: Optional[List[HourlyWeather]] = None,
    ) -> str:
        try:
            return await self.agent.call(
                legs=json.dumps([l.model_dump() for l in legs], ensure_ascii=False),
                destination=destination,
                weather=json.dumps([w.model_dump() for w in weather or []], ensure_ascii=False),
            )
        except Exception:  # noqa: BLE001
            return self._template(legs, destination)

    def _template(self, legs: List[TransportLeg], destination: str) -> str:
        seg = " → ".join(f"{l.from_city}→{l.to_city}({l.depart}-{l.arrive})" for l in legs)
        return (
            f"## 出行清单（{destination}）\n"
            "- 证件：身份证/护照随身携带，值机需证件号\n"
            "- 行李：按航司/铁路规定确认行李额，充电宝随身携带\n"
            f"- 行程：{seg}\n"
            "- 当地注意：提前查看目的地天气与交通，预留中转时间"
        )

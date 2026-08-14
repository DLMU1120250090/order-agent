from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import HourlyWeather


class WeatherAdvisoryService:
    """
    天气联动建议（C4 定稿，规则生成）。
    - 出发时段早高峰(7-9点) 且 通勤耗时>阈值 → 建议提前出发
    - 到达时刻降水概率>0.6 → 建议带伞
    - 体感温差/温度 → 穿衣建议
    """

    async def build_advisory(
        self,
        db: AsyncSession,
        origin: str,
        destination: str,
        depart_hour: int,
        commute_minutes: int = 60,
        weather: Optional[List[HourlyWeather]] = None,
    ) -> str:
        weather = weather or []
        advice = []

        if 7 <= depart_hour <= 9 and commute_minutes > 45:
            advice.append(f"出发时段为早高峰，家到出发地通勤约 {commute_minutes} 分钟，建议提前出发。")

        arr_weather = next((w for w in weather if w.precip_prob > 0.6), None)
        if arr_weather:
            advice.append(f"到达 {destination} 时降水概率 {int(arr_weather.precip_prob * 100)}%，建议带伞。")

        if weather:
            avg_temp = sum(w.temp for w in weather) / len(weather)
            if avg_temp >= 28:
                advice.append(f"{destination} 近期体感偏热（约 {avg_temp:.0f}°C），建议轻薄衣物并注意防晒。")
            elif avg_temp <= 12:
                advice.append(f"{destination} 近期偏冷（约 {avg_temp:.0f}°C），建议携带外套。")

        return "；".join(advice) if advice else "目的地天气平稳，无特殊出行建议。"

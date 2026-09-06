from typing import List
from app.models.schemas import TravelSlotBundle


class ClarifyRuleService:
    """
    出行槽位澄清规则校验（A1 定稿）。
    必填：destination + tripDate（已解析、非模糊）；budget 条件必填。
    """

    def has_enough_slots(self, slots: TravelSlotBundle, fuzzy_date: bool = False) -> bool:
        return len(self.missing_slots(slots, fuzzy_date)) == 0

    def missing_slots(self, slots: TravelSlotBundle, fuzzy_date: bool = False) -> List[str]:
        safe_slots = slots if slots is not None else TravelSlotBundle()
        missing = []

        # 1. 目的地必填
        if not safe_slots.destination:
            missing.append("destination")

        # 2. 出行日期必填，且必须已解析为具体日期（模糊表达需追问）
        if not safe_slots.tripDate:
            missing.append("tripDate")
        elif fuzzy_date:
            missing.append("tripDate")

        # 3. 预算条件必填：无预算且无其它强偏好时追问
        if not safe_slots.budget and not self.has_strong_preference(safe_slots):
            missing.append("budget")

        return missing

    def has_strong_preference(self, slots: TravelSlotBundle) -> bool:
        return bool(slots.travelStyle or slots.transportMode or slots.companion)

    def fallback_question(self, missing_slots: List[str]) -> str:
        if not missing_slots:
            return "你想去哪里、大概什么时候出发？"
        if "destination" in missing_slots:
            return "这次想去的城市是哪里？"
        if "tripDate" in missing_slots:
            return "具体哪天出发？如果是节假日或模糊时间，麻烦告诉我具体的日期或日期范围。"
        if "budget" in missing_slots:
            return "这次出行的预算大概是什么档位：经济型、舒适型还是高端型？"
        return "我再确认一下，这次出行更看重预算、时间还是交通方式？"

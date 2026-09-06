import re
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple


class DateResolveResult:
    """日期解析结果（A1 定稿）"""
    def __init__(self, dates: List[str], fuzzy: bool, raw: str = ""):
        self.dates = dates  # 单元素=单日，双元素=[start,end] 范围
        self.fuzzy = fuzzy  # 模糊（如"国庆"未明确具体几天）
        self.raw = raw

    def __repr__(self):
        return f"DateResolveResult(dates={self.dates}, fuzzy={self.fuzzy})"


class DateResolverService:
    """
    tripDate 自由值日期解析（A1 定稿）。
    输入自然语言（"下周三"/"10.1-10.3"/"国庆"）→ 输出具体日期/范围 + 是否模糊。
    实现：规则（今天/明天/后天/本周X/下周X/几月几号）+ 节假日表；LLM 辅助留作增强钩子。
    """

    WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}

    # 节假日表：可配置。未明确具体几天 → 标记模糊，交由 ClarifyRule 追问
    HOLIDAYS = {
        "元旦": (None, None, True),
        "五一": (None, None, True),
        "国庆": (None, None, True),
        "春节": (None, None, True),
        "中秋": (None, None, True),
    }

    def __init__(self):
        self.today = date.today

    def resolve(self, text: str) -> DateResolveResult:
        raw = (text or "").strip()
        if not raw:
            return DateResolveResult([], True, raw)

        # 1. 范围优先：X月X日到X月X日 / 10.1-10.3 / 2026.8.18-2026.8.22
        range_result = self._resolve_range(raw)
        if range_result:
            return range_result

        # 2. 明确的单日日期格式 2026-08-19 / 2026.8.20 / 2026/08/19
        m = re.search(r"(20\d{2})[./年-](\d{1,2})[./月-](\d{1,2})[日号]?", raw)
        if m:
            d = self._safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d:
                return DateResolveResult([d], False, raw)

        # 3. 相对日期词
        rel = self._resolve_relative(raw)
        if rel:
            return rel

        # 4. 节假日
        for name, (start, end, fuzzy) in self.HOLIDAYS.items():
            if name in raw:
                if fuzzy or not start:
                    return DateResolveResult([], True, raw)
                year = self.today().year
                dates = [f"{year}-{start}", f"{year}-{end}"]
                return DateResolveResult(dates, False, raw)

        # 5. 无法识别 → 标记模糊，交给 ClarifyRule 追问
        return DateResolveResult([], True, raw)

    def _resolve_range(self, raw: str) -> Optional[DateResolveResult]:
        # 10月1日到10月3日 / 8月18号到8月22号 / 10.1-10.3 / 2026.8.18-2026.8.22
        pat = re.search(
            r"(?:(20\d{2})[./年-])?(\d{1,2})[./月-](\d{1,2})[日号]?"
            r"[到至~\-—]"
            r"(?:(20\d{2})[./年-])?(\d{1,2})[./月-](\d{1,2})[日号]?",
            raw,
        )
        if pat:
            year1 = int(pat.group(1)) if pat.group(1) else self.today().year
            year2 = int(pat.group(4)) if pat.group(4) else year1
            s = self._safe_date(year1, int(pat.group(2)), int(pat.group(3)))
            e = self._safe_date(year2, int(pat.group(5)), int(pat.group(6)))
            if s and e:
                return DateResolveResult([s, e], False, raw)
        return None

    def _resolve_relative(self, raw: str) -> Optional[DateResolveResult]:
        today = self.today()
        if "大后天" in raw:
            return DateResolveResult([self._fmt(today + timedelta(days=3))], False, raw)
        if "后天" in raw:
            return DateResolveResult([self._fmt(today + timedelta(days=2))], False, raw)
        if "明天" in raw or "明儿" in raw:
            return DateResolveResult([self._fmt(today + timedelta(days=1))], False, raw)
        if "今天" in raw or "今晚" in raw:
            return DateResolveResult([self._fmt(today)], False, raw)
        if "下下周" in raw:
            return DateResolveResult([self._fmt(today + timedelta(days=14))], False, raw)
        if "下周" in raw or "下星期" in raw:
            wd = self._weekday_in(raw)
            if wd is not None:
                delta = (wd - today.weekday()) % 7 + 7
                return DateResolveResult([self._fmt(today + timedelta(days=delta))], False, raw)
            return DateResolveResult([], True, raw)
        if "本周" in raw or "这周" in raw:
            wd = self._weekday_in(raw)
            if wd is not None:
                delta = (wd - today.weekday()) % 7
                return DateResolveResult([self._fmt(today + timedelta(days=delta))], False, raw)
            return DateResolveResult([], True, raw)
        # 单独星期表达（"周五"/"星期五"）：取本周最近一次该星期（当天则今天）
        wd = self._weekday_in(raw)
        if wd is not None:
            delta = (wd - today.weekday()) % 7
            return DateResolveResult([self._fmt(today + timedelta(days=delta))], False, raw)
        # 几月几号（不带年份）
        m = re.search(r"(\d{1,2})[月./-](\d{1,2})[日号]?", raw)
        if m:
            d = self._safe_date(today.year, int(m.group(1)), int(m.group(2)))
            if d:
                return DateResolveResult([d], False, raw)
        return None

    def _weekday_in(self, raw: str) -> Optional[int]:
        for ch, idx in self.WEEKDAY_MAP.items():
            if f"周{ch}" in raw or f"星期{ch}" in raw:
                return idx
        return None

    def _safe_date(self, year: int, month: int, day: int) -> Optional[str]:
        try:
            return self._fmt(date(year, month, day))
        except ValueError:
            return None

    @staticmethod
    def _fmt(d: date) -> str:
        return d.strftime("%Y-%m-%d")


class DateConsistencyService:
    """
    日期先后校验（A1 定稿）：
    - 同一请求内：start <= end
    - 往返拆两次任务：返程日期晚于去程（查询已有行程/订单）
    """

    def check(self, trip_date: List[str], existing_trips: Optional[List[dict]] = None) -> Tuple[bool, str]:
        if not trip_date:
            return False, "缺少出行日期"
        if len(trip_date) > 1:
            start, end = trip_date[0], trip_date[1]
            if start > end:
                return False, f"出发日期 {start} 必须早于或等于返回日期 {end}"
        # 返程晚于去程：新行程的出发不得早于已有行程的出发日
        for trip in existing_trips or []:
            existing_start = trip.get("start_date")
            if existing_start and trip_date[0] <= existing_start:
                return False, f"返程日期必须晚于已有去程日期 {existing_start}"
        return True, ""

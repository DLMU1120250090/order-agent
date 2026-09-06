from typing import List, Tuple, Optional
from app.models.enums import Intent

# 资金/安全操作统一保守告知话术（合规：绝不代付）
CONSERVATIVE_MESSAGE = (
    "涉及资金的操作（下单、支付、改签、退票）需要你本人确认并亲自完成支付。"
    "我绝不会自动付款或替你代付。请先确认方案卡片，再按提示扫码完成支付。"
)

FUND_PHRASES = ["代付", "自动付款", "替我付款", "支付密码", "银行卡密码", "转账"]
ABSOLUTE_PHRASES = ["保证", "一定", "包退", "稳赚"]


class RiskGuardService:
    """
    合规与资金安全审查服务（RiskGuard，出行版）。
    对最终要输出给用户的文本以及用户输入进行双向合规审查，
    防止出现代付承诺、绝对化承诺或资金操作诱导。
    """

    def check(
        self,
        user_input: Optional[str],
        intent: Optional[Intent],
        speech_text: Optional[str],
    ) -> Tuple[bool, List[str], str]:
        reasons = []
        all_text = f"{user_input or ''} {speech_text or ''}"

        if any(kw in all_text for kw in FUND_PHRASES):
            reasons.append("涉及代付/资金敏感操作")
        if any(kw in all_text for kw in ABSOLUTE_PHRASES):
            reasons.append("涉及绝对化承诺")

        if not reasons:
            return True, [], ""
        return False, reasons, self.conservative_message()

    def conservative_message(self) -> str:
        return CONSERVATIVE_MESSAGE

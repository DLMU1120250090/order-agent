import re

from app.models.enums import Intent
from app.models.schemas import SessionState, TravelSlotBundle
from app.agents.intent import IntentResultSchema

# 意图分类置信度低水平阈值，低于该值将强行降级
LOW_CONFIDENCE_THRESHOLD = 0.4

# 资金安全敏感词（涉及代付/自动付款等，一律并入 OTHER 兜底拦截）
FUND_RISK_KEYWORDS = [
    "代付", "自动付款", "帮我付款", "替我付款", "转账", "支付密码", "银行卡密码", "验证码",
]


class IntentReviseService:
    """
    出行意图识别后置的规则修正服务（保留现有三层兜底机制）。
    """

    def revise(
        self,
        state: SessionState,
        result: IntentResultSchema,
        user_input: str,
        has_orders: bool = False,
        has_plan: bool = False,
    ) -> IntentResultSchema:
        safe_result = result or IntentResultSchema(
            intent=Intent.CLARIFY_NEEDED.value, slots=TravelSlotBundle(), confidence=0.0
        )

        # 规则 0: 有推荐上下文且用户明确点选方案（方案1/第一个/就订/订这个）→ 强制 PLAN_BOOK
        # 让“第一个不错”“方案2吧”这类口语也能进入下单与反馈闭环；调整类（太贵等）不覆盖
        if (
            safe_result.intent not in (Intent.PLAN_BOOK.value, Intent.PLAN_ADJUST.value)
            and self.has_plan_context(state)
            and re.search(r"方案\s*(\d+|[一二三四五六七八九十]+)|第\s*(\d+|[一二三四五六七八九十]+)\s*个|就订|订这个|订方案|这个方案", user_input or "")
        ):
            return IntentResultSchema(
                intent=Intent.PLAN_BOOK.value,
                slots=safe_result.slots,
                confidence=max(safe_result.confidence, 0.6),
            )

        # 规则 1: 资金安全首要原则。命中代付/自动付款等敏感词 → OTHER（安全风险并入 OTHER）
        if self.contains_fund_risk_keyword(user_input):
            return IntentResultSchema(
                intent=Intent.OTHER.value,
                slots=safe_result.slots,
                confidence=safe_result.confidence,
            )

        # 规则 2: 无推荐上下文时 PLAN_ADJUST 降级为首次规划
        if safe_result.intent == Intent.PLAN_ADJUST.value and not self.has_plan_context(state):
            return IntentResultSchema(
                intent=Intent.PLAN_RECOMMENDATION.value,
                slots=safe_result.slots,
                confidence=safe_result.confidence,
            )

        # 规则 3: 无方案上下文时 PLAN_BOOK 降级为重新规划
        if safe_result.intent == Intent.PLAN_BOOK.value and not has_plan and not self.has_plan_context(state):
            return IntentResultSchema(
                intent=Intent.PLAN_RECOMMENDATION.value,
                slots=safe_result.slots,
                confidence=safe_result.confidence,
            )

        # 规则 4: 无订单时 ORDER_CHANGE / ORDER_CANCEL 降级为规划（状态感知矫正）
        if safe_result.intent in (Intent.ORDER_CHANGE.value, Intent.ORDER_CANCEL.value) and not has_orders:
            return IntentResultSchema(
                intent=Intent.PLAN_RECOMMENDATION.value,
                slots=safe_result.slots,
                confidence=safe_result.confidence,
            )

        # 规则 5: 置信度降级。PLAN_RECOMMENDATION 低置信度 → CLARIFY_NEEDED
        if safe_result.intent == Intent.PLAN_RECOMMENDATION.value and safe_result.confidence < LOW_CONFIDENCE_THRESHOLD:
            return IntentResultSchema(
                intent=Intent.CLARIFY_NEEDED.value,
                slots=safe_result.slots,
                confidence=safe_result.confidence,
            )

        return safe_result

    def has_plan_context(self, state: SessionState) -> bool:
        return bool(state and (state.lastRecommendations or state.selectedPlanId))

    def contains_fund_risk_keyword(self, user_input: str) -> bool:
        if not user_input:
            return False
        return any(kw in user_input for kw in FUND_RISK_KEYWORDS)

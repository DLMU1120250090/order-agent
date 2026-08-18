from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from app.config import get_main_model
from app.agents.prompt_loader import load_prompt


class RecommendationPlanItem(BaseModel):
    """单条出行方案推荐子项"""
    planId: str = Field(description="方案 ID，必须来自候选方案列表，不能编造")
    reason: str = Field(description="针对该方案的推荐理由，需切合用户诉求与已知槽位")


class PlanRecommendOutputSchema(BaseModel):
    """出行方案推荐最终输出格式"""
    recommendations: List[RecommendationPlanItem] = Field(description="推荐方案列表，最多 3 项")
    speechText: str = Field(description="向用户回复的口语化回复内容")


class PlanRecommendAgent:
    """
    出行方案推荐生成 Agent。
    候选方案由 ItineraryPlanner 确定性给出，LLM 仅负责写推荐理由与口语化回复。
    """
    def __init__(self):
        self.system_prompt = load_prompt("recommend-plan.txt")
        self.model = get_main_model().with_structured_output(PlanRecommendOutputSchema, method="json_mode")
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", (
                "用户原话：{user_input}\n"
                "当前槽位：{slots}\n"
                "用户长期记忆（参考，不要编造）：{memory_context}\n"
                "候选方案：{top_plans}\n"
                "请输出 JSON，包含 recommendations 数组（每项 planId + reason）和 speechText，不要编造候选之外的方案。"
            ))
        ])
        self.chain = self.prompt_template | self.model

    async def call(
        self,
        user_input: str,
        slots: str,
        top_plans: str,
        memory_context: str = "",
    ) -> PlanRecommendOutputSchema:
        return await self.chain.ainvoke({
            "user_input": user_input,
            "slots": slots,
            "top_plans": top_plans,
            "memory_context": memory_context or "（暂无）",
        })


# 兼容旧引用名（若外部仍 import RecommendResponseAgent）
RecommendResponseAgent = PlanRecommendAgent

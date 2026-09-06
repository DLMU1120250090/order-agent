from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from app.config import get_light_model
from app.agents.prompt_loader import load_prompt
from app.models.schemas import TravelSlotBundle


class IntentResultSchema(BaseModel):
    """
    意图分类与槽位提取结果的 Pydantic 校验 Schema。
    通过 LangChain with_structured_output 机制，大模型的输出结果被强制解析并校验为此结构。
    """
    intent: str = Field(
        description="必须是以下值之一：PLAN_RECOMMENDATION, CLARIFY_NEEDED, PLAN_ADJUST, PLAN_BOOK, ORDER_QUERY, ORDER_CHANGE, ORDER_CANCEL, PRICE_MONITOR, CHECKLIST_EXPORT, OTHER"
    )
    slots: TravelSlotBundle = Field(..., description="提取到的 6 维出行槽位字典")
    confidence: float = Field(..., description="意图识别置信度分数 (0.0 到 1.0)")


class IntentAgent:
    """
    意图识别与槽位提取 Agent（出行版）。
    利用系统提示词配合最近三轮的历史消息、已搜集槽位、词库以及当前问题，分类意图并抽取新出现的槽位信息。
    """
    def __init__(self):
        self.system_prompt = load_prompt("intent.txt")
        # 显式指定 method="json_mode"，DeepSeek 兼容接口只支持 response_format=json_object
        self.model = get_light_model().with_structured_output(IntentResultSchema, method="json_mode")
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", (
                "userId: {user_id}\n"
                "sessionId: {session_id}\n"
                "recentHistory: {history}\n"
                "knownSlots: {known_slots}\n"
                "slotOptions: {slot_options}\n"
                "当前这一句: {user_input}\n"
                "请输出 JSON，字段为 intent、slots、confidence。"
            ))
        ])
        self.chain = self.prompt_template | self.model

    async def call(
        self,
        user_id: int,
        session_id: str,
        history: str,
        known_slots: str,
        slot_options: str,
        user_input: str
    ) -> IntentResultSchema:
        return await self.chain.ainvoke({
            "user_id": str(user_id),
            "session_id": session_id,
            "history": history,
            "known_slots": known_slots,
            "slot_options": slot_options,
            "user_input": user_input
        })

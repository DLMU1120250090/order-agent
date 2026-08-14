from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from app.config import get_light_model
from app.agents.prompt_loader import load_prompt


class SummaryAgent:
    """L2 行程摘要生成 Agent（后台异步，轻量模型）"""
    def __init__(self):
        self.system_prompt = load_prompt("summary.txt")
        self.model = get_light_model()
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", "用户：{user_input}\n订单/行程数据：{order_data}")
        ])
        self.chain = self.prompt_template | self.model | StrOutputParser()

    async def call(self, user_input: str, order_data: str) -> str:
        return await self.chain.ainvoke({"user_input": user_input, "order_data": order_data})

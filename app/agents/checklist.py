from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from app.config import get_light_model
from app.agents.prompt_loader import load_prompt


class ChecklistAgent:
    """出行清单生成 Agent（C4 定稿）"""
    def __init__(self):
        self.system_prompt = load_prompt("checklist.txt")
        self.model = get_light_model()
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", "行程段：{legs}\n目的地：{destination}\n天气：{weather}")
        ])
        self.chain = self.prompt_template | self.model | StrOutputParser()

    async def call(self, legs: str, destination: str, weather: str) -> str:
        return await self.chain.ainvoke({
            "legs": legs,
            "destination": destination,
            "weather": weather
        })

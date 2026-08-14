from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import StrOutputParser
from app.config import get_light_model
from app.agents.prompt_loader import load_prompt

class ClarifyAgent:
    """
    槽位澄清追问生成 Agent。
    当用户表达的信息不足以完成就餐推荐时，该 Agent 会结合已获知的槽位信息和缺少的必填槽位，
    以自然友好的口吻向用户生成追问话术。
    """
    def __init__(self):
        # 1. 载入追问澄清的系统提示词
        self.system_prompt = load_prompt("clarify.txt")
        self.model = get_light_model()
        # 2. 构造 Prompt 模板，传入当前对话槽位情况
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", "用户原话：{user_input}\n已知信息：{known_slots}\n缺失字段：{missing_slots}")
        ])
        # 3. 组装 Chain，使用 StrOutputParser 提取大模型返回的纯文本应答
        self.chain = self.prompt_template | self.model | StrOutputParser()

    async def call(self, user_input: str, known_slots: str, missing_slots: str) -> str:
        """
        调用大模型生成澄清追问的话术。
        """
        return await self.chain.ainvoke({
            "user_input": user_input,
            "known_slots": known_slots,
            "missing_slots": missing_slots
        })


from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage
from app.config import get_light_model
from app.agents.prompt_loader import load_prompt

class EvaluationJudgeOutputSchema(BaseModel):
    """
    大模型裁判打分输出校验 Schema。
    大模型需要从“解释合理性”与“表达口语自然度”两个维度给出 1-5 分的评价，并写明理由。
    """
    explanationQuality: float = Field(description="解释质量得分 (1-5 分)，评估回复是否合理解释了推荐理由")
    naturalness: float = Field(description="回复自然度得分 (1-5 分)，评估回复语调是否简洁、口语化且自然")
    reason: str = Field(description="给出打分的具体评价理由")

class EvaluationJudgeAgent:
    """
    离线质量评估 LLM 裁判 Agent。
    利用系统提示词评估实际运行时的输入输出，从而对生成答案的语义质量、自然度与解释力进行主观打分。
    """
    def __init__(self):
        # 1. 载入大模型裁判系统的提示词
        self.system_prompt = load_prompt("evaluation-judge.txt")
        # 2. 绑定结构化输出 schema，返回自动序列化的 LLM 客户端
        # 注意：显式指定 method="json_mode"，DeepSeek 兼容接口只支持 response_format=json_object
        self.model = get_light_model().with_structured_output(EvaluationJudgeOutputSchema, method="json_mode")
        # 3. 构造打分 Prompt
        self.prompt_template = ChatPromptTemplate.from_messages([
            SystemMessage(content=self.system_prompt),
            ("user", "traceId：{trace_id}\ntrace摘要：\n{judge_input}\n请按系统要求输出 JSON。")
        ])
        # 4. 组装 Chain
        self.chain = self.prompt_template | self.model

    async def call(self, trace_id: str, judge_input: str) -> EvaluationJudgeOutputSchema:
        """
        调用 LLM 裁判对 Trace 执行打分。
        """
        return await self.chain.ainvoke({
            "trace_id": trace_id,
            "judge_input": judge_input
        })


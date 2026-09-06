from cachetools import LRUCache
from app.agents.intent import IntentAgent
from app.agents.clarify import ClarifyAgent
from app.agents.recommend import PlanRecommendAgent
from app.agents.summary import SummaryAgent
from app.agents.checklist import ChecklistAgent


class SessionAgentSet:
    """
    会话级别的 Agent 集合包装类。
    用于管理和隔离单次会话内调用的所有具体 Agent 链实例。
    """
    def __init__(self):
        self.intent = IntentAgent()
        self.clarify = ClarifyAgent()
        self.recommend_plan = PlanRecommendAgent()
        self.summary = SummaryAgent()
        self.checklist = ChecklistAgent()


class AgentFactory:
    """
    Agent 缓存工厂（复用现有 LRU 模式）。
    """
    def __init__(self, prompt_version: str = "v3", max_sessions: int = 1000):
        self.prompt_version = prompt_version
        self.cache = LRUCache(maxsize=max_sessions)

    def get(self, session_id: str) -> SessionAgentSet:
        cache_key = f"{session_id}::{self.prompt_version}"
        if cache_key not in self.cache:
            self.cache[cache_key] = SessionAgentSet()
        return self.cache[cache_key]

    def remove(self, session_id: str):
        cache_key = f"{session_id}::{self.prompt_version}"
        self.cache.pop(cache_key, None)

import logging
import os
from datetime import date, datetime
from typing import List, Optional

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompt_loader import load_prompt
from app.config import get_light_model
from app.crud import profile as profile_crud
from app.models.database import TripSummaryRow
from app.models.schemas import TripSummary, UserProfile

log = logging.getLogger("travel.memory")


class MemoryService:
    """
    记忆系统 L0–L3（C2 定稿）。
    - L0 会话上下文：复用 diet_sessions/diet_messages（编排层）
    - L1 用户画像：MySQL user_profile（规则确定性写入）
    - L2 行程摘要：表 + md 文件 memory/trips/（后台异步 LLM 生成）
    - L3 偏好蒸馏：memory/distill/user_{id}.md（每日定时 distill，按用户隔离）
    """

    def __init__(self, memory_dir: str = ""):
        if not memory_dir:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            memory_dir = os.path.join(project_dir, "memory")
        self.memory_dir = memory_dir
        os.makedirs(os.path.join(self.memory_dir, "trips"), exist_ok=True)
        os.makedirs(os.path.join(self.memory_dir, "distill"), exist_ok=True)

    def _l3_path(self, user_id: int) -> str:
        """L3 偏好蒸馏文件路径（按用户隔离，避免多用户互相覆盖/串读）。"""
        return os.path.join(self.memory_dir, "distill", f"user_{user_id}.md")

    async def get_profile(self, db: AsyncSession, user_id: int) -> Optional[UserProfile]:
        return await profile_crud.get_profile(db, user_id)

    async def update_profile(self, db: AsyncSession, user_id: int, **fields) -> Optional[UserProfile]:
        return await profile_crud.update_profile(db, user_id, **fields)

    async def add_trip_summary(
        self,
        db: AsyncSession,
        user_id: int,
        trip_id: Optional[int],
        summary_md: str,
        episode: Optional[dict] = None,
    ):
        """L2 落库：summary_md（LLM 派生文本）+ episode_json（结构化字段，Commit 1）。"""
        row = TripSummaryRow(user_id=user_id, trip_id=trip_id, summary_md=summary_md, episode_json=episode)
        db.add(row)
        await db.commit()
        # md 双写：memory/trips/YYYY-MM-DD.md
        md_path = os.path.join(self.memory_dir, "trips", f"{date.today().isoformat()}.md")
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{summary_md}\n")
        return row

    async def get_preference(
        self,
        db: AsyncSession,
        user_id: int,
        key: str,
        passenger_id: Optional[str] = None,
    ) -> Optional[dict]:
        """统一偏好读取：passenger 级 v2 > user 级 v2 > flat（legacy）。返回条目 dict（含 value）或 None。"""
        profile = await self.get_profile(db, user_id)
        if not profile:
            return None
        return profile_crud.resolve_preference(
            profile.preferences_v2, profile.preferences, key, passenger_id=passenger_id
        )

    async def update_preference(
        self,
        db: AsyncSession,
        user_id: int,
        key: str,
        value,
        passenger_id: Optional[str] = None,
        confidence: Optional[float] = None,
        source: str = "rule",
    ) -> Optional[UserProfile]:
        """统一偏好写入（Commit 1）：user 级（默认）或 passenger 级，写入 preferences_v2 带 value/confidence/source。"""
        profile = await self.get_profile(db, user_id)
        v2 = dict(profile.preferences_v2 or {}) if profile else {}
        bucket_key = "passengers" if passenger_id else "user"
        bucket = dict(v2.get(bucket_key) or {})
        if passenger_id:
            prefs = dict(bucket.get(str(passenger_id)) or {})
        else:
            prefs = bucket
        entry = {"value": value, "source": source}
        if confidence is not None:
            entry["confidence"] = float(confidence)
        prefs[key] = entry
        if passenger_id:
            bucket[str(passenger_id)] = prefs
        else:
            bucket = prefs
        v2[bucket_key] = bucket
        await self.update_profile(db, user_id, preferences_v2=v2)
        return await self.get_profile(db, user_id)

    async def recent_summaries(self, db: AsyncSession, user_id: int, n: int = 30) -> List[str]:
        res = await db.execute(
            select(TripSummaryRow)
            .where(TripSummaryRow.user_id == user_id)
            .order_by(TripSummaryRow.created_at.desc())
            .limit(n)
        )
        return [r.summary_md for r in res.scalars().all()]

    async def distill(self, db: AsyncSession, user_id: int) -> str:
        """L3 偏好蒸馏：轻量模型读 L1 + 近 30 条 L2 + 历史偏好结论 → 提炼新结论；失败回退规则汇总。"""
        profile = await self.get_profile(db, user_id)
        summaries = await self.recent_summaries(db, user_id, 30)
        previous = self._read_previous_conclusion(user_id)
        conclusion = await self._llm_distill(user_id, profile, summaries, previous)

        lines = ["# 用户偏好蒸馏（L3）", ""]
        if conclusion:
            lines += ["## 偏好结论（LLM 蒸馏）", conclusion, ""]
        else:
            lines += ["## 偏好结论（规则汇总兜底）", "（本次蒸馏模型不可用，由规则汇总生成）", ""]
        lines += [
            "## 数据依据",
            f"- 用户ID: {user_id}",
        ]
        if profile:
            lines += [
                f"- 常驻城市: {profile.home_city or '未知'}",
                f"- 预算档位: {profile.budget_level or '未知'}",
                f"- 偏好: {profile.preferences or {}}",
                f"- 常用乘客数: {len(profile.passengers or [])}",
            ]
        lines.append("")
        lines.append("## 近期行程（最近 30 条）")
        lines.extend(f"- {s.replace(chr(10), ' ')[:180]}" for s in summaries)
        text = "\n".join(lines)
        md_path = self._l3_path(user_id)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
        return text

    def _read_previous_conclusion(self, user_id: int) -> str:
        """读取该用户上一轮 L3 偏好结论（供新一轮蒸馏参考，保持长期连续性，不无限追加）。"""
        try:
            md_path = self._l3_path(user_id)
            if not os.path.exists(md_path):
                return ""
            with open(md_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()
            start = None
            for i, line in enumerate(lines):
                if line.startswith("## 偏好结论"):
                    start = i + 1
                    break
            if start is None:
                return ""
            parts = []
            for line in lines[start:]:
                if line.startswith("## "):
                    break
                if line.strip():
                    parts.append(line.strip())
            return "\n".join(parts)[:300]
        except Exception:  # noqa: BLE001
            return ""

    async def _llm_distill(self, user_id: int, profile, summaries: List[str], previous: str = "") -> str:
        """轻量模型提炼偏好结论（参考历史结论，保留稳定、更新变化）；异常返回空串由 distill 兜底。"""
        try:
            profile_text = (
                f"常驻城市={profile.home_city or '未知'}, 预算档位={profile.budget_level or '未知'}, "
                f"偏好={profile.preferences or {}}, 常用乘客数={len(profile.passengers or [])}"
                if profile
                else "（暂无画像）"
            )
            summaries_text = "\n".join(f"- {s[:150]}" for s in summaries) or "（暂无行程）"
            history_text = previous or "（暂无历史结论）"
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=load_prompt("distill.txt")),
                ("user", "用户画像：{profile}\n近期行程摘要：{summaries}\n历史偏好结论：{history}\n请输出偏好结论。"),
            ])
            chain = prompt | get_light_model()
            res = await chain.ainvoke({
                "profile": profile_text,
                "summaries": summaries_text,
                "history": history_text,
            })
            text = str(getattr(res, "content", "") or "").strip()
            return text[:400]
        except Exception as e:  # noqa: BLE001
            log.warning("L3 LLM 蒸馏失败，回退规则汇总: %s", e)
            return ""

    def _read_l3(self, user_id: int) -> str:
        """读取该用户 L3 长期偏好蒸馏快照（memory/distill/user_{id}.md），控制注入长度。"""
        try:
            md_path = self._l3_path(user_id)
            if not os.path.exists(md_path):
                return ""
            with open(md_path, "r", encoding="utf-8") as f:
                text = f.read().strip()
            return text[:600]
        except Exception:  # noqa: BLE001
            return ""

    async def build_context(self, db: AsyncSession, user_id: int) -> str:
        """L1 画像 + 相关 L2 摘要 + L3 长期偏好快照 → 上下文串（注入规划/推荐/决策）。"""
        profile = await self.get_profile(db, user_id)
        summaries = await self.recent_summaries(db, user_id, 5)
        parts = []
        if profile:
            parts.append(
                f"用户画像: 常驻城市={profile.home_city or '未知'}, "
                f"预算档位={profile.budget_level or '未知'}, 偏好={profile.preferences or {}}"
            )
        if summaries:
            parts.append("近期行程: " + " | ".join(s.replace("\n", " ")[:100] for s in summaries))
        l3 = self._read_l3(user_id)
        if l3:
            parts.append("长期偏好(L3): " + l3.replace("\n", " ")[:400])
        return "\n".join(parts) if parts else "（暂无用户画像）"

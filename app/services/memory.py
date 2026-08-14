import os
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import profile as profile_crud
from app.models.database import TripSummaryRow
from app.models.schemas import TripSummary, UserProfile


class MemoryService:
    """
    记忆系统 L0–L3（C2 定稿）。
    - L0 会话上下文：复用 diet_sessions/diet_messages（编排层）
    - L1 用户画像：MySQL user_profile（规则确定性写入）
    - L2 行程摘要：表 + md 文件 memory/trips/（后台异步 LLM 生成）
    - L3 偏好蒸馏：memory/MEMORY.md（每日定时 distill，简化 Dream）
    """

    def __init__(self, memory_dir: str = ""):
        if not memory_dir:
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            memory_dir = os.path.join(project_dir, "memory")
        self.memory_dir = memory_dir
        os.makedirs(os.path.join(self.memory_dir, "trips"), exist_ok=True)

    async def get_profile(self, db: AsyncSession, user_id: int) -> Optional[UserProfile]:
        return await profile_crud.get_profile(db, user_id)

    async def update_profile(self, db: AsyncSession, user_id: int, **fields) -> Optional[UserProfile]:
        return await profile_crud.update_profile(db, user_id, **fields)

    async def add_trip_summary(self, db: AsyncSession, user_id: int, trip_id: Optional[int], summary_md: str):
        row = TripSummaryRow(user_id=user_id, trip_id=trip_id, summary_md=summary_md)
        db.add(row)
        await db.commit()
        # md 双写：memory/trips/YYYY-MM-DD.md
        md_path = os.path.join(self.memory_dir, "trips", f"{date.today().isoformat()}.md")
        with open(md_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{summary_md}\n")
        return row

    async def recent_summaries(self, db: AsyncSession, user_id: int, n: int = 30) -> List[str]:
        res = await db.execute(
            select(TripSummaryRow)
            .where(TripSummaryRow.user_id == user_id)
            .order_by(TripSummaryRow.created_at.desc())
            .limit(n)
        )
        return [r.summary_md for r in res.scalars().all()]

    async def distill(self, db: AsyncSession, user_id: int) -> str:
        """L3 偏好蒸馏：读 L1 + 最近 30 条 L2 → 更新 memory/MEMORY.md。"""
        profile = await self.get_profile(db, user_id)
        summaries = await self.recent_summaries(db, user_id, 30)
        lines = [
            "# 用户偏好蒸馏（L3）",
            "",
            f"- 用户ID: {user_id}",
            f"- 常驻城市: {profile.home_city if profile and profile.home_city else '未知'}",
            f"- 预算档位: {profile.budget_level if profile and profile.budget_level else '未知'}",
            f"- 偏好: {profile.preferences if profile and profile.preferences else '{}'}",
            f"- 常用乘客数: {len(profile.passengers) if profile and profile.passengers else 0}",
            "",
            "## 近期行程（最近 30 条）",
        ]
        lines.extend(f"- {s.replace(chr(10), ' ')[:180]}" for s in summaries)
        text = "\n".join(lines)
        md_path = os.path.join(self.memory_dir, "MEMORY.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
        return text

    async def build_context(self, db: AsyncSession, user_id: int) -> str:
        """L1 画像 + 相关 L2 → 上下文串（注入规划/决策/下单预填）。"""
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
        return "\n".join(parts) if parts else "（暂无用户画像）"

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
from app.services.user_memory_events import (
    UserEventType,
    recent_user_events,
    summarize_price_events,
)

log = logging.getLogger("travel.memory")


def majority_transport_from_episodes(episodes: list) -> Optional[dict]:
    """从结构化 Episode 统计首段交通方式高频项（Commit 7 规则蒸馏，不调 LLM）。

    返回 {"value": "train|flight", "confidence": 占比, "count": n, "total": m}；
    样本 < 3 或最高占比 < 60% 时不形成偏好（返回 None）。
    """
    counts = {"train": 0, "flight": 0}
    for ep in episodes:
        plan = (ep or {}).get("selected_plan") or {}
        mode = str(plan.get("mode") or "").upper()
        if mode == "TRAIN":
            counts["train"] += 1
        elif mode == "FLIGHT":
            counts["flight"] += 1
    total = counts["train"] + counts["flight"]
    if total < 3:
        return None
    best = max(counts, key=counts.get)
    ratio = counts[best] / total
    if ratio < 0.6:
        return None
    return {"value": best, "confidence": round(ratio, 2), "count": counts[best], "total": total}


def _morning_share_from_episodes(episodes: list) -> Optional[dict]:
    """统计早班（05:00~08:59 出发）占比；样本 >=3 且占比 >=60% 才形成 time_window=morning。"""
    morning = 0
    total = 0
    for ep in episodes:
        plan = (ep or {}).get("selected_plan") or {}
        depart = str(plan.get("depart") or "")
        try:
            hour = int(depart.split(":")[0])
        except (TypeError, ValueError):
            continue
        total += 1
        if 5 <= hour < 9:
            morning += 1
    if total < 3:
        return None
    ratio = morning / total
    if ratio < 0.6:
        return None
    return {"value": "morning", "confidence": round(ratio, 2), "count": morning, "total": total}


def passenger_preferences_from_episodes(episodes: list) -> dict:
    """按乘客分组蒸馏（分化方案 A1/P2）：transport / time_window 写入 preferences_v2.passengers。

    episodes 形如 [{"passengers": ["0", "P_x"], "selected_plan": {...}}, ...]。
    """
    grouped: dict = {}
    for ep in episodes:
        for pid in (ep or {}).get("passengers") or []:
            grouped.setdefault(str(pid), []).append(ep)
    result = {}
    for pid, rows in grouped.items():
        transport = majority_transport_from_episodes(rows)
        time_window = _morning_share_from_episodes(rows)
        prefs = {}
        if transport:
            prefs["transport"] = {
                "value": transport["value"],
                "confidence": transport["confidence"],
                "source": "distilled",
            }
        if time_window:
            prefs["time_window"] = {
                "value": time_window["value"],
                "confidence": time_window["confidence"],
                "source": "distilled",
            }
        if prefs:
            result[pid] = prefs
    return result


def price_sensitivity_from_events(events) -> Optional[dict]:
    """从 User L2 价格事件蒸馏 price_sensitivity（接受率 >=60% high / <=30% low / 其余 medium）。"""
    accepted = sum(1 for e in events if e.event_type == UserEventType.PRICE_DROP_ACCEPTED)
    ignored = sum(1 for e in events if e.event_type == UserEventType.PRICE_DROP_IGNORED)
    total = accepted + ignored
    if total < 3:
        return None
    ratio = accepted / total
    value = "high" if ratio >= 0.6 else ("low" if ratio <= 0.3 else "medium")
    return {"value": value, "confidence": round(ratio, 2), "count": accepted, "total": total}


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
        conditions: Optional[dict] = None,
    ) -> Optional[UserProfile]:
        """统一偏好写入（Commit 1）：user 级（默认）或 passenger 级，写入 preferences_v2。

        entry 结构：value / source / confidence(可选) / conditions(可选，P2 预留透传)。
        """
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
        if conditions:
            entry["conditions"] = conditions
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
        """L3 偏好蒸馏：双主体提炼（User L2 决策行为 + Passenger L2 出行经历）→ 提炼新结论；失败回退双主体规则汇总。"""
        profile = await self.get_profile(db, user_id)
        
        # 1. 查取近期行程（Passenger L2）
        res_trips = await db.execute(
            select(TripSummaryRow)
            .where(TripSummaryRow.user_id == user_id)
            .order_by(TripSummaryRow.created_at.desc())
            .limit(30)
        )
        trip_rows = list(res_trips.scalars().all())
        
        # 2. 查取近期操作者行为事件（User L2）
        user_events = await recent_user_events(
            db,
            user_id,
            (
                UserEventType.PRICE_DROP_ACCEPTED,
                UserEventType.PRICE_DROP_IGNORED,
                UserEventType.CHANGE_CONFIRMED,
                UserEventType.CHANGE_REJECTED,
                UserEventType.REFUND_CONFIRMED,
                UserEventType.RECOMMEND_ACCEPTED,
                UserEventType.RECOMMEND_REJECTED,
                UserEventType.MONITOR_TOGGLED,
                UserEventType.REMINDER_SET,
            ),
            limit=30,
        )

        # 构建乘客名称映射
        p_name_map = {}
        for p in (profile.passengers if profile else []) or []:
            pid = str(p.get("passenger_id") or "")
            p_name = p.get("name") or ("本人" if pid == "0" else pid)
            role_txt = "本人" if pid == "0" or p.get("role") == "self" else "同行人"
            p_name_map[pid] = f"{p_name}({role_txt})"

        # 整理 Passenger L2 文本（按乘车人分组）
        passenger_grouped: dict = {}
        for r in trip_rows:
            ep = r.episode_json or {}
            passengers = ep.get("passengers") or ["0"]
            plan = ep.get("selected_plan") or {}
            ctx = ep.get("context") or {}
            mode = plan.get("mode") or "TRAIN"
            depart = plan.get("depart") or ""
            seat = plan.get("seat") or ""
            price = plan.get("price") or 0
            route = f"{ctx.get('origin', '')}->{ctx.get('destination', '')}" if ctx else ""
            desc_item = f"{route} {mode} {depart} {seat} ¥{price}"
            for pid in passengers:
                pid_str = str(pid)
                passenger_grouped.setdefault(pid_str, []).append(desc_item)

        passenger_text_lines = []
        for pid_str, items in passenger_grouped.items():
            label = p_name_map.get(pid_str, f"乘客 {pid_str}")
            passenger_text_lines.append(f"【{label}】近期 {len(items)} 次出行：")
            passenger_text_lines.extend(f"  - {it}" for it in items[:6])
        passenger_episodes_text = "\n".join(passenger_text_lines)

        # 整理 User L2 行为事件文本
        price_stats = summarize_price_events(user_events)
        user_event_lines = []
        if price_stats.get("total", 0) > 0:
            user_event_lines.append(
                f"价格监控响应：接受 {price_stats['accepted']} 次，忽略 {price_stats['ignored']} 次，"
                f"接受率 {int((price_stats['acceptRatio'] or 0) * 100)}%"
            )
        rec_acc = sum(1 for e in user_events if e.event_type == UserEventType.RECOMMEND_ACCEPTED)
        rec_rej = sum(1 for e in user_events if e.event_type == UserEventType.RECOMMEND_REJECTED)
        if rec_acc + rec_rej > 0:
            user_event_lines.append(f"方案推荐响应：采纳 {rec_acc} 次，拒绝/换一批 {rec_rej} 次")
        change_acc = sum(1 for e in user_events if e.event_type == UserEventType.CHANGE_CONFIRMED)
        change_rej = sum(1 for e in user_events if e.event_type == UserEventType.CHANGE_REJECTED)
        if change_acc + change_rej > 0:
            user_event_lines.append(f"改签处理响应：确认改签 {change_acc} 次，放弃 {change_rej} 次")
        user_events_text = "\n".join(f"- {l}" for l in user_event_lines)

        previous = self._read_previous_conclusion(user_id)
        conclusion = await self._llm_distill(
            user_id, profile, passenger_episodes_text, user_events_text, previous
        )

        lines = ["# 用户与乘车人偏好蒸馏（L3）", ""]
        if conclusion:
            lines += ["## 偏好结论（LLM 双主体提炼）", conclusion, ""]
        else:
            # 规则汇总兜底双主体展示
            lines += [
                "## 偏好结论（规则汇总兜底）",
                "### 一、用户决策风格偏好 (User L3)",
                f"1. 价格敏感倾向：{price_stats.get('acceptRatio', '标准中等')}",
                f"2. 常用操作习惯：默认预算档位 {profile.budget_level if profile else '标准'}，主动采纳推荐为主",
                "",
                "### 二、乘车人出行偏好 (Passenger L3)",
            ]
            for pid_str, label in p_name_map.items():
                lines.append(f"- **{label}**：倾向高铁二等座出行，偏好早间与常规白天车次")
            lines.append("")

        lines += [
            "## 数据依据",
            f"- 用户ID: {user_id}",
        ]
        if profile:
            lines += [
                f"- 常驻城市: {profile.home_city or '未知'}",
                f"- 预算档位: {profile.budget_level or '未知'}",
                f"- 操作者行为事件数 (User L2): {len(user_events)} 条",
                f"- 乘车人出行经历数 (Passenger L2): {len(trip_rows)} 条",
                f"- 常用乘客数: {len(profile.passengers or [])}",
            ]
        lines.append("")
        lines.append("## 近期行程经历（Passenger L2）")
        for r in trip_rows[:15]:
            ep = r.episode_json or {}
            pids = [p_name_map.get(str(p), str(p)) for p in (ep.get("passengers") or ["0"])]
            p_tag = f"[{' / '.join(pids)}]"
            lines.append(f"- {p_tag} {r.summary_md.replace(chr(10), ' ')[:160]}")

        lines.append("")
        lines.append("## 最近操作者决策事件（User L2）")
        if user_events:
            for ev in user_events[:10]:
                ctx_desc = f" | {ev.context}" if ev.context else ""
                lines.append(f"- [{ev.event_type}] 订单: {ev.order_no or '无'}{ctx_desc}")
        else:
            lines.append("- （暂无决策事件记录）")

        text = "\n".join(lines)
        md_path = self._l3_path(user_id)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
        # 规则蒸馏结构化偏好（高频交通方式与价格敏感度），供 Planner/Resolver 消费
        await self.distill_preferences(db, user_id)
        return text

    async def distill_preferences(self, db: AsyncSession, user_id: int) -> Optional[dict]:
        """结构化偏好蒸馏（无 LLM、幂等）：
        - 按乘客（本人=0 / P_xxx）从最近 Episode 蒸馏 transport / time_window → preferences_v2.passengers；
        - 从 User L2 价格事件蒸馏 price_sensitivity → preferences_v2.user。
        """
        res = await db.execute(
            select(TripSummaryRow)
            .where(
                TripSummaryRow.user_id == user_id,
                TripSummaryRow.episode_json.is_not(None),
            )
            .order_by(TripSummaryRow.created_at.desc())
            .limit(20)
        )
        episodes = [r.episode_json or {} for r in res.scalars().all()]
        written = {}
        per_passenger = passenger_preferences_from_episodes(episodes)
        for pid, prefs in per_passenger.items():
            for key, meta in prefs.items():
                await self.update_preference(
                    db, user_id, key, meta["value"],
                    passenger_id=pid, confidence=meta.get("confidence"), source=meta.get("source", "distilled"),
                    conditions=meta.get("conditions"),
                )
            written[pid] = {key: meta["value"] for key, meta in prefs.items()}

        price_events = await recent_user_events(
            db, user_id,
            (UserEventType.PRICE_DROP_ACCEPTED, UserEventType.PRICE_DROP_IGNORED),
            limit=100,
        )
        sensitivity = price_sensitivity_from_events(price_events)
        if sensitivity:
            await self.update_preference(
                db, user_id, "price_sensitivity", sensitivity["value"],
                confidence=sensitivity["confidence"], source="distilled",
            )
        return {"passengers": written, "priceSensitivity": sensitivity["value"] if sensitivity else None}

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

    async def _llm_distill(
        self,
        user_id: int,
        profile,
        passenger_episodes_text: str,
        user_events_text: str,
        previous: str = "",
    ) -> str:
        """轻量模型提炼偏好结论（参考历史结论，分 User L3 与 Passenger L3）；异常返回空串由 distill 兜底。"""
        try:
            profile_text = (
                f"常驻城市={profile.home_city or '未知'}, 预算档位={profile.budget_level or '未知'}, "
                f"偏好={profile.preferences or {}}, 常用乘客数={len(profile.passengers or [])}"
                if profile
                else "（暂无画像）"
            )
            passenger_text = passenger_episodes_text or "（暂无乘车人行程）"
            user_text = user_events_text or "（暂无操作者决策事件）"
            history_text = previous or "（暂无历史结论）"
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=load_prompt("distill.txt")),
                (
                    "user",
                    "【用户画像】\n{profile}\n\n"
                    "【操作者决策事件 (User L2)】\n{user_events}\n\n"
                    "【各乘车人出行经历 (Passenger L2)】\n{passenger_episodes}\n\n"
                    "【历史偏好结论】\n{history}\n\n"
                    "请按要求输出分主体偏好结论。"
                ),
            ])
            chain = prompt | get_light_model()
            res = await chain.ainvoke({
                "profile": profile_text,
                "user_events": user_text,
                "passenger_episodes": passenger_text,
                "history": history_text,
            })
            text = str(getattr(res, "content", "") or "").strip()
            return text[:600]
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

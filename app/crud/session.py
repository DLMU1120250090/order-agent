import uuid
import json
import datetime
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import SessionRow, SessionMessageRow
from app.models.schemas import SessionState, TravelSlotBundle
from app.models.enums import SessionPhase, Intent, Channel


TRAVEL_SLOT_NAMES = ["origin", "destination", "tripDate", "returnDate", "budget", "travelStyle", "transportMode", "companion"]


def parse_slots_and_meta(slots_val: Any) -> Tuple[TravelSlotBundle, Dict[str, Any]]:
    """解析 slots JSON 数据，转化为 6 维出行槽位结构与 _meta 元数据字典。"""
    if not slots_val:
        slots_val = {}
    elif isinstance(slots_val, str):
        try:
            slots_val = json.loads(slots_val)
        except Exception:
            slots_val = {}

    meta = slots_val.get("_meta", {}) if isinstance(slots_val, dict) else {}
    bundle = TravelSlotBundle(
        origin=slots_val.get("origin") or [],
        destination=slots_val.get("destination") or [],
        tripDate=slots_val.get("tripDate") or [],
        returnDate=slots_val.get("returnDate") or [],
        budget=slots_val.get("budget") or [],
        travelStyle=slots_val.get("travelStyle") or [],
        transportMode=slots_val.get("transportMode") or [],
        companion=slots_val.get("companion") or [],
    )
    return bundle, meta


def serialize_slots_and_meta(state: SessionState) -> dict:
    """将 SessionState 序列化为存储 JSON：6 维槽位 + _meta 运行时状态。"""
    slots_dict = state.slots.model_dump()
    slots_dict["_meta"] = {
        "channel": state.channel.value if state.channel else Channel.web.value,
        "currentIntent": state.currentIntent.value if state.currentIntent else None,
        "currentBatch": list(state.currentBatch),
        "selectedPlanId": state.selectedPlanId,
        "orderId": state.orderId,
        "orderNo": state.orderNo,
    }
    return slots_dict


async def create_session(
    db: AsyncSession,
    user_id: int,
    channel: Channel = Channel.web,
    session_id: Optional[str] = None,
) -> str:
    # 有外部会话键（如 web:1 / dingtalk:ding_xxx）时直接用其作为行 id，保证跨轮稳定
    if not session_id:
        session_id = f"sess_{uuid.uuid4().hex}"
    empty_slots = {
        "destination": [], "tripDate": [], "budget": [], "travelStyle": [],
        "transportMode": [], "companion": [],
        "_meta": {"channel": channel.value, "currentIntent": None, "selectedPlanId": None, "orderId": None, "orderNo": None},
    }
    row = SessionRow(
        id=session_id,
        user_id=user_id,
        phase=SessionPhase.START.value,
        slots=empty_slots,
        last_recommendations=[],
    )
    db.add(row)
    await db.commit()
    return session_id


async def ensure_session(db: AsyncSession, session_id: str, user_id: int, channel: Channel = Channel.web):
    result = await db.execute(select(SessionRow).where(SessionRow.id == session_id, SessionRow.user_id == user_id))
    if not result.scalars().first():
        await create_session(db, user_id, channel)


async def load_session_state(
    db: AsyncSession,
    session_id: Optional[str],
    user_id: int,
    channel: Channel = Channel.web,
) -> SessionState:
    if not session_id:
        new_sess_id = await create_session(db, user_id, channel)
        return SessionState(
            sessionId=new_sess_id,
            userId=user_id,
            phase=SessionPhase.START,
            channel=channel,
            currentIntent=None,
            slots=TravelSlotBundle(),
            lastRecommendations=[],
        )

    result = await db.execute(select(SessionRow).where(SessionRow.id == session_id, SessionRow.user_id == user_id))
    row = result.scalars().first()
    if not row:
        new_sess_id = await create_session(db, user_id, channel, session_id=session_id)
        return SessionState(
            sessionId=new_sess_id,
            userId=user_id,
            phase=SessionPhase.START,
            channel=channel,
            currentIntent=None,
            slots=TravelSlotBundle(),
            lastRecommendations=[],
        )

    slots_bundle, meta = parse_slots_and_meta(row.slots)

    try:
        channel_enum = Channel(meta.get("channel") or channel.value)
    except ValueError:
        channel_enum = channel

    saved_intent_str = meta.get("currentIntent")
    try:
        current_intent = Intent(saved_intent_str) if saved_intent_str else None
    except ValueError:
        current_intent = None

    try:
        phase = SessionPhase(row.phase)
    except ValueError:
        phase = SessionPhase.START

    last_recs = row.last_recommendations
    if isinstance(last_recs, str):
        try:
            last_recs = json.loads(last_recs)
        except Exception:
            last_recs = []
    if not last_recs:
        last_recs = []

    return SessionState(
        sessionId=row.id,
        userId=row.user_id,
        phase=phase,
        channel=channel_enum,
        currentIntent=current_intent,
        slots=slots_bundle,
        lastRecommendations=list(last_recs),
        currentBatch=meta.get("currentBatch") or [],
        selectedPlanId=meta.get("selectedPlanId"),
        orderId=meta.get("orderId"),
        orderNo=meta.get("orderNo"),
    )


async def save_session_state(db: AsyncSession, state: SessionState):
    result = await db.execute(select(SessionRow).where(SessionRow.id == state.sessionId, SessionRow.user_id == state.userId))
    row = result.scalars().first()
    if not row:
        raise Exception(f"Session {state.sessionId} not found when saving state.")
    row.phase = state.phase.value
    row.slots = serialize_slots_and_meta(state)
    row.last_recommendations = state.lastRecommendations
    row.updated_at = datetime.datetime.now()
    db.add(row)
    await db.commit()


async def append_message(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    intent: Optional[str],
    trace_id: Optional[str],
):
    msg = SessionMessageRow(
        session_id=session_id,
        role=role,
        content=content if content is not None else "",
        intent=intent,
        agent_trace_id=trace_id,
    )
    db.add(msg)
    await db.commit()


async def recent_conversation_turns(
    db: AsyncSession,
    session_id: str,
    user_id: int,
    n: int,
    max_turns: int = 10,
) -> List[dict]:
    limit = min(n, max(1, max_turns))
    query = (
        select(SessionMessageRow)
        .join(SessionRow, SessionMessageRow.session_id == SessionRow.id)
        .where(SessionRow.id == session_id, SessionRow.user_id == user_id)
        .order_by(desc(SessionMessageRow.created_at))
        .limit(limit)
    )
    result = await db.execute(query)
    rows = list(result.scalars().all())
    rows.reverse()

    turns = []
    for r in rows:
        content = r.content or ""
        normalized = content.replace("\r", "").replace("\n", " ").strip()
        summary = normalized if len(normalized) <= 120 else normalized[:120]
        epoch_ms = int(r.created_at.timestamp() * 1000)
        turns.append({
            "role": r.role,
            "intent": r.intent,
            "content": summary,
            "createdAt": epoch_ms,
        })
    return turns


async def latest_session_id(
    db: AsyncSession,
    user_id: int,
) -> Optional[str]:
    """返回该用户最近有消息的 Web 会话（sess_* / web:*），供刷新后恢复对话。"""
    query = (
        select(SessionMessageRow.session_id)
        .join(SessionRow, SessionRow.id == SessionMessageRow.session_id)
        .where(
            SessionRow.user_id == user_id,
            or_(SessionRow.id.like("sess_%"), SessionRow.id.like("web:%")),
        )
        .group_by(SessionMessageRow.session_id)
        .order_by(desc(func.max(SessionMessageRow.created_at)))
        .limit(1)
    )
    res = await db.execute(query)
    return res.scalars().first()

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
        passengers=slots_val.get("passengers") or [],
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
        "pendingConfirms": list(state.pendingConfirms),
        "currentPassengerId": state.currentPassengerId,
        "currentPassengerIds": list(state.currentPassengerIds or [state.currentPassengerId or "0"]),
        "passengerSelectionPending": state.passengerSelectionPending,
        "passengerSelectionDone": state.passengerSelectionDone,
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
        "transportMode": [], "companion": [], "passengers": [],
        "_meta": {"channel": channel.value, "currentIntent": None, "selectedPlanId": None, "orderId": None, "orderNo": None, "pendingConfirms": [], "currentPassengerId": "0", "currentPassengerIds": ["0"], "passengerSelectionPending": False, "passengerSelectionDone": False},
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
        # 修复（2026-09-06）：必须复用传入的 session_id，否则会生成随机新会话 id，
        # 调用方按原 id 再次查询仍找不到会话。
        await create_session(db, user_id, channel, session_id=session_id)


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
        pendingConfirms=meta.get("pendingConfirms") or [],
        currentPassengerId=str(meta.get("currentPassengerId") or "0"),
        currentPassengerIds=[str(x) for x in (meta.get("currentPassengerIds") or [meta.get("currentPassengerId") or "0"])],
        passengerSelectionPending=bool(meta.get("passengerSelectionPending")),
        passengerSelectionDone=bool(meta.get("passengerSelectionDone")),
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
    trace_ids = [r.agent_trace_id for r in rows if r.agent_trace_id]
    trace_map = {}
    if trace_ids:
        from app.models.database import RequestTraceRow
        t_res = await db.execute(select(RequestTraceRow).where(RequestTraceRow.trace_id.in_(trace_ids)))
        for t in t_res.scalars().all():
            trace_map[t.trace_id] = t

    for r in rows:
        content = r.content or ""
        epoch_ms = int(r.created_at.timestamp() * 1000) if r.created_at else 0
        resp_type = "ANSWER"
        if r.role == "assistant":
            resp_type = "CLARIFY" if r.intent == "CLARIFY_NEEDED" else ("PLAN_RECOMMENDATION" if r.intent == "PLAN_RECOMMENDATION" else "ANSWER")

        display_blocks = []
        turn_missing_slots = None
        turn_confirm_fields = None
        turn_order_no = None
        turn_task_id = None
        if r.role == "assistant" and r.agent_trace_id and r.agent_trace_id in trace_map:
            t_row = trace_map[r.agent_trace_id]
            t_json = t_row.trace_json
            if isinstance(t_json, str):
                try:
                    t_json = json.loads(t_json)
                except Exception:
                    pass
            if isinstance(t_json, dict):
                events = t_json.get("events", [])
                for ev in events:
                    if ev.get("eventType") == "CLARIFY_DECISION" and ev.get("outputPayload"):
                        try:
                            c_payload = json.loads(ev["outputPayload"]) if isinstance(ev["outputPayload"], str) else ev["outputPayload"]
                            if isinstance(c_payload, dict):
                                if "missingSlots" in c_payload:
                                    turn_missing_slots = c_payload.get("missingSlots") or []
                                if "confirmFields" in c_payload:
                                    turn_confirm_fields = c_payload.get("confirmFields") or []
                        except Exception:
                            pass
                    if ev.get("eventType") in ("REQUEST_FINISHED", "RESPONSE_READY") and ev.get("outputPayload"):
                        try:
                            payload = json.loads(ev["outputPayload"]) if isinstance(ev["outputPayload"], str) else ev["outputPayload"]
                            if isinstance(payload, dict):
                                if "blocks" in payload and payload["blocks"]:
                                    display_blocks = payload["blocks"]
                                if payload.get("kind") == "CLARIFY":
                                    resp_type = "CLARIFY"
                                elif payload.get("kind") == "TASK_PROGRESS":
                                    resp_type = "TASK_PROGRESS"
                                    tp = payload.get("task_progress") or {}
                                    turn_order_no = tp.get("orderNo") or turn_order_no
                                    turn_task_id = tp.get("taskId") or payload.get("correlation_id") or turn_task_id
                                elif payload.get("kind") == "CARD":
                                    resp_type = "CARD"
                                    if payload.get("blocks"):
                                        b0 = payload["blocks"][0]
                                        if isinstance(b0, dict) and b0.get("orderNo"):
                                            turn_order_no = b0.get("orderNo") or turn_order_no
                        except Exception:
                            pass

        turn = {
            "id": r.id,
            "role": r.role,
            "intent": r.intent,
            "content": content,
            "agent_trace_id": r.agent_trace_id,
            "responseType": resp_type if r.role == "assistant" else None,
            "displayBlocks": display_blocks,
            "orderNo": turn_order_no,
            "taskId": turn_task_id,
            "createdAt": epoch_ms,
        }
        if r.role == "assistant" and (resp_type == "CLARIFY" or r.intent == "CLARIFY_NEEDED"):
            turn["missingSlots"] = turn_missing_slots if turn_missing_slots is not None else []
            turn["confirmFields"] = turn_confirm_fields if turn_confirm_fields is not None else []
            turn["clarifyQuestion"] = content

        turns.append(turn)
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


async def list_user_sessions(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
) -> List[dict]:
    """返回该用户的历史会话列表，按更新时间倒序。自动解析标题与消息数。"""
    safe_limit = max(1, min(100, limit))
    stmt = (
        select(SessionRow)
        .where(SessionRow.user_id == user_id)
        .order_by(desc(SessionRow.updated_at))
        .limit(safe_limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    sessions = []
    for r in rows:
        slots_val = r.slots
        if isinstance(slots_val, str):
            try:
                slots_val = json.loads(slots_val)
            except Exception:
                slots_val = {}
        elif not isinstance(slots_val, dict):
            slots_val = {}

        meta = slots_val.get("_meta") or {}
        title = meta.get("title")

        # 若未指定自定义标题，查询该会话第一条用户输入内容作为标题
        if not title:
            msg_res = await db.execute(
                select(SessionMessageRow.content)
                .where(
                    SessionMessageRow.session_id == r.id,
                    SessionMessageRow.role == "user",
                )
                .order_by(SessionMessageRow.created_at.asc())
                .limit(1)
            )
            first_user_msg = msg_res.scalars().first()
            if first_user_msg:
                first_clean = first_user_msg.replace("\r", "").replace("\n", " ").strip()
                title = first_clean[:28] if len(first_clean) > 28 else first_clean
            else:
                title = "新出行规划会话"

        # 统计消息数量
        cnt_res = await db.execute(
            select(func.count(SessionMessageRow.id))
            .where(SessionMessageRow.session_id == r.id)
        )
        msg_count = cnt_res.scalar() or 0

        sessions.append({
            "sessionId": r.id,
            "title": title,
            "phase": r.phase,
            "createdAt": r.created_at.isoformat() if r.created_at else None,
            "updatedAt": r.updated_at.isoformat() if r.updated_at else None,
            "messageCount": msg_count,
        })
    return sessions


async def delete_session(
    db: AsyncSession,
    session_id: str,
    user_id: int,
) -> bool:
    """删除指定会话及其所有关联消息。"""
    from sqlalchemy import delete
    sess_res = await db.execute(
        select(SessionRow).where(SessionRow.id == session_id, SessionRow.user_id == user_id)
    )
    row = sess_res.scalars().first()
    if not row:
        return False

    await db.execute(
        delete(SessionMessageRow).where(SessionMessageRow.session_id == session_id)
    )
    await db.delete(row)
    await db.commit()
    return True


async def update_session_title(
    db: AsyncSession,
    session_id: str,
    user_id: int,
    title: str,
) -> bool:
    """修改会话自定义标题，保存在 slots._meta.title 中。"""
    sess_res = await db.execute(
        select(SessionRow).where(SessionRow.id == session_id, SessionRow.user_id == user_id)
    )
    row = sess_res.scalars().first()
    if not row:
        return False

    slots_val = row.slots
    if isinstance(slots_val, str):
        try:
            slots_val = json.loads(slots_val)
        except Exception:
            slots_val = {}
    elif not isinstance(slots_val, dict):
        slots_val = {}

    if "_meta" not in slots_val or not isinstance(slots_val["_meta"], dict):
        slots_val["_meta"] = {}
    slots_val["_meta"]["title"] = title

    row.slots = slots_val
    row.updated_at = datetime.datetime.now()
    db.add(row)
    await db.commit()
    return True

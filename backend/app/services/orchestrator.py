import asyncio
import logging
import re
from collections import defaultdict
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.factory import AgentFactory
from app.agents.intent import IntentResultSchema
from app.crud import binding as binding_crud
from app.crud import order as order_crud
from app.crud import profile as profile_crud
from app.crud import session as session_crud
from app.crud import slot_option as slot_option_crud
from app.crud import task as task_crud
from app.crud import trip as trip_crud
from app.models.database import FeedbackRow, TravelOrderRow
from app.models.enums import (
    Channel, ChangeScenario, Intent, OrderStatus, SessionPhase, TaskType,
)
from app.models.schemas import (
    ChangeRequest, InboundMessage, OutboundMessage, PlanOption, SessionState,
    TransportLeg, TravelIntentResult, TravelSlotBundle,
)
from app.services.booking import BookingService
from app.services.browser import browser_order
from app.services.change_decision import ChangeDecisionService
from app.services.checklist import ChecklistService
from app.services.clarify_rule import ClarifyRuleService
from app.services.collector import DataCollectorService
from app.services.date_resolver import DateConsistencyService, DateResolverService
from app.services.intent_revise import IntentReviseService
from app.services.memory import MemoryService
from app.services.memory_context import MemoryContextBuilder, MemoryResolver
from app.services.mock_supplier import mock_supplier
from app.services.planner import ItineraryPlanner
from app.services.push import PushService
from app.services.risk_guard import RiskGuardService
from app.services.skill_loader import load_skill
from app.services.task import TaskService
from app.services.trace import TraceContext, TraceScope, active_trace_ctx, traced_agent_call
from app.services.trace_schema import EventType
from app.services.user_memory_events import UserEventType, record_user_event
from app.database import async_session_maker

log = logging.getLogger("travel.orchestrator")

CHITCHAT_REPLY = (
    "我是出行规划与预订助手。告诉我目的地和日期（例如“下周三去成都”），"
    "我可以帮你规划行程、下单、查订单、改签或退票。"
)

PAYMENT_CONFIRM_KEYWORDS = ["付好了", "已支付", "支付完成", "付完了", "付了"]
CHANGE_CONFIRM_KEYWORDS = ["确认改签", "就改", "同意改", "确认改", "改签确认"]
CANCEL_CONFIRM_KEYWORDS = ["确认退票", "确认退", "同意退", "退票确认"]
MANUAL_ORDER_PATTERN = re.compile(r"订单号[是为：: ]*([A-Za-z0-9]+)")
# Commit 2：Memory 推断值确认——简短肯定回复直接确认默认推断并规划
MEMORY_CONFIRM_PATTERN = re.compile(
    r"^(好的?|可以|行吧|行|嗯+|对|对的|是|是的|按这个|就这样|没问题|ok|okay|同意|好呀|好嘞|好滴|成)$",
    re.IGNORECASE,
)
# 分化方案 P0（Commit 1）：乘客选择
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _self_passenger(profile) -> Optional[dict]:
    if not profile:
        return None
    for p in profile.passengers or []:
        if str(p.get("passenger_id") or "") == "0" or p.get("role") == "self":
            return p
    return None


def _other_passengers(profile) -> list:
    if not profile:
        return []
    return [
        p for p in profile.passengers or []
        if not (str(p.get("passenger_id") or "") == "0" or p.get("role") == "self")
    ]


def resolve_passenger_choice(text: str, profile) -> Optional[str]:
    """解析乘客选择回复：本人 / 乘客名 / 第N个（N 对应非本人乘客列表）。解析失败返回 None。"""
    if not profile or not text:
        return None
    t = (text or "").strip().strip("。！!？?，, ")
    if not t:
        return None
    self_p = _self_passenger(profile)
    self_id = str(self_p.get("passenger_id") or "0") if self_p else "0"
    self_name = str(self_p.get("name") or "") if self_p else ""
    if t in ("0", "本人", "自己", "我自己", "给我自己", "我") or t.startswith("本人") or "本人" in t:
        return self_id
    if self_name and (self_name in t or t in self_name):
        return self_id
    others = _other_passengers(profile)
    if not others:
        return self_id
    # 编号：1/2/3 或 第N个
    m = re.fullmatch(r"第?(\d+|[一二三四五六七八九十]+)个?", t)
    if m:
        raw = m.group(1)
        idx = int(raw) if raw.isdigit() else _CN_NUM.get(raw, 0)
        if 1 <= idx <= len(others):
            return str(others[idx - 1].get("passenger_id") or "")
    # 姓名包含匹配
    for p in others:
        name = str(p.get("name") or "")
        if name and (name in t or t in name):
            return str(p.get("passenger_id") or "")
    return None


ID_CARD_PATTERN = re.compile(r"([1-9]\d{5}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])")


def resolve_passenger_choices(text: str, profile) -> List[str]:
    """解析多个乘车人回复：返回匹配到的 passenger_id 列表。"""
    if not profile or not text:
        return []
    t = (text or "").strip()
    results = []
    others = _other_passengers(profile)
    self_p = _self_passenger(profile)
    self_id = str(self_p.get("passenger_id") or "0") if self_p else "0"
    self_name = str(self_p.get("name") or "") if self_p else ""

    # 本人或本人姓名
    if any(k in t for k in ("本人", "自己", "我自己", "给我自己", "1人", "单人", "一个人")) or t == "0" or (self_name and self_name in t):
        if self_id not in results:
            results.append(self_id)
    # 全部
    if any(k in t for k in ("全部", "所有人", "都去", "全去", "全选")):
        if self_id not in results:
            results.append(self_id)
        for p in others:
            pid = str(p.get("passenger_id") or "")
            if pid and pid not in results:
                results.append(pid)
        return results
    # 其它乘客姓名匹配
    for p in others:
        name = str(p.get("name") or "")
        pid = str(p.get("passenger_id") or "")
        if name and name in t and pid not in results:
            results.append(pid)
    # 编号匹配
    matches = re.findall(r"第?(\d+|[一二三四五六七八九十]+)个?", t)
    for raw in matches:
        idx = int(raw) if raw.isdigit() else _CN_NUM.get(raw, 0)
        if 1 <= idx <= len(others):
            pid = str(others[idx - 1].get("passenger_id") or "")
            if pid and pid not in results:
                results.append(pid)
    return results


def resolve_passenger_ids_from_slots(slots_passengers, profile) -> List[str]:
    """从槽位 passengers 列表中解析出对应的 passenger_id 列表。"""
    if not profile or not slots_passengers:
        return []
    if isinstance(slots_passengers, str):
        raw_list = [slots_passengers]
    elif isinstance(slots_passengers, (list, tuple, set)):
        raw_list = list(slots_passengers)
    else:
        return []

    results: List[str] = []
    all_passengers = profile.passengers or []
    self_p = _self_passenger(profile)
    self_id = str(self_p.get("passenger_id") or "0") if self_p else "0"
    self_name = str(self_p.get("name") or "") if self_p else ""

    for item in raw_list:
        if not item:
            continue
        item_str = str(item).strip()
        # 1. 尝试使用 resolve_passenger_choices 解析
        p_ids = resolve_passenger_choices(item_str, profile)
        for pid in p_ids:
            if pid not in results:
                results.append(pid)
        if p_ids:
            continue

        # 2. 单项匹配
        single_id = resolve_passenger_choice(item_str, profile)
        if single_id and single_id not in results:
            results.append(single_id)
            continue

        # 3. 关键字兜底（本人/自己/单人/1人等）
        if any(k in item_str for k in ("本人", "自己", "我", "1人", "单人", "一个人")) or (self_name and self_name in item_str):
            if self_id not in results:
                results.append(self_id)

        # 4. 遍历所有乘客 ID 或姓名包含匹配
        for p in all_passengers:
            pid = str(p.get("passenger_id") or "")
            name = str(p.get("name") or "")
            if pid and (item_str == pid or (name and (name in item_str or item_str in name))):
                if pid not in results:
                    results.append(pid)

    return results


def passenger_selection_question(profile) -> str:
    others = _other_passengers(profile)
    if not others:
        return "这次还是给本人买票吗？回复“本人”即可。"
    names = "、".join(f"{i}. {p.get('name')}" for i, p in enumerate(others, 1))
    return f"这次给谁买票？回复“本人”，或告诉我乘客名字/编号（{names}）。"


def passenger_selection_gate(profile, state) -> str:
    """下单前乘客闸门：返回 passenger_id 直接下单；"ASK" 表示需要先询问。"""
    if not profile or not profile.passengers:
        return "0"
    if not _other_passengers(profile):
        return "0"
    if state.passengerSelectionPending:
        return "ASK"
    if state.passengerSelectionDone:
        return state.currentPassengerId or "0"
    # 如果已从槽位或上下文获得了乘客信息，直接放行，避免重复询问
    if state.slots and state.slots.passengers:
        resolved = resolve_passenger_ids_from_slots(state.slots.passengers, profile)
        if resolved:
            return resolved[0]
    return "ASK"


class TravelOrchestratorService:
    """
    出行编排中枢（步骤 6）。
    统一收 InboundMessage，按状态机路由各业务分支，产出领域响应（OutboundMessage）。
    LLM 负责"想明白、说清楚"，编排层负责"走对路、守规矩"。
    """

    def __init__(
        self,
        agent_factory: AgentFactory,
        push_service: PushService,
        task_service: TaskService,
        booking: BookingService,
        memory: MemoryService,
        collector: Optional[DataCollectorService] = None,
        change_decision: Optional[ChangeDecisionService] = None,
        checklist: Optional[ChecklistService] = None,
    ):
        self.agent_factory = agent_factory
        self.push_service = push_service
        self.task_service = task_service
        self.booking = booking
        self.memory = memory
        self.collector = collector or DataCollectorService()
        self.change_decision = change_decision or ChangeDecisionService(self.collector)
        self.checklist = checklist or ChecklistService()

        self.clarify_rules = ClarifyRuleService()
        self.intent_revise = IntentReviseService()
        self.risk_guard = RiskGuardService()
        self.date_resolver = DateResolverService()
        self.date_consistency = DateConsistencyService()
        self.planner = ItineraryPlanner(self.collector)
        self.memory_resolver = MemoryResolver()
        self.memory_builder = MemoryContextBuilder()
        self.session_locks = defaultdict(asyncio.Lock)

    async def handle_message(self, db: AsyncSession, inbound: InboundMessage) -> OutboundMessage:
        """统一入口：入站消息 → 领域响应。"""
        if not inbound or not inbound.text or not inbound.text.strip():
            return OutboundMessage(channel=inbound.channel, text="消息不能为空")

        # 身份解析：Web 直接取 channel_user_id；其它通道查绑定表
        user_id = inbound.user_id
        if user_id is None:
            if inbound.channel == Channel.web.value:
                try:
                    user_id = int(inbound.channel_user_id)
                except (TypeError, ValueError):
                    user_id = 1
            else:
                user_id = await binding_crud.find_user_id(db, inbound.channel, inbound.channel_user_id)
                if user_id is None:
                    return OutboundMessage(
                        channel=inbound.channel,
                        channel_user_id=inbound.channel_user_id,
                        text="你还未绑定用户。请在 Web 端确认你的 userId 后回复：绑定 <userId>",
                    )

        self.push_service.remember(inbound)
        session_id = inbound.session_key or f"{inbound.channel}:{inbound.channel_user_id}"
        state = await session_crud.load_session_state(
            db, session_id, user_id, Channel(inbound.channel)
        )

        async with self.session_locks[state.sessionId]:
            async with TraceScope(db, state.sessionId, user_id) as ctx:
                ctx.record_event("REQUEST_RECEIVED", "HTTP", inbound.model_dump(), state.model_dump())
                try:
                    await session_crud.append_message(db, state.sessionId, "user", inbound.text, None, ctx.trace_id)
                    ctx.record_event("USER_MESSAGE_RECORDED", "SESSION", inbound.text, {"sessionId": state.sessionId})
                    response = await self._handle_turn(db, user_id, inbound.text, state, ctx)
                    response.session_id = response.session_id or state.sessionId
                    if not response.correlation_id:
                        response.correlation_id = ctx.trace_id
                    ctx.record_event("REQUEST_FINISHED", "HTTP", inbound.model_dump(), response.model_dump())
                    return response
                except Exception as e:  # noqa: BLE001
                    ctx.record_error("REQUEST_FAILED", "HTTP", inbound.model_dump(), e)
                    log.exception("编排异常")
                    return OutboundMessage(channel=inbound.channel, text="服务暂时开小差了，请稍后重试。")

    async def _handle_turn(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        state: SessionState,
        ctx: TraceContext,
    ) -> OutboundMessage:
        # ① 支付确认快捷路径（回复"付好了" / "已支付"）
        if self._contains_any(text, PAYMENT_CONFIRM_KEYWORDS):
            order = None
            if state.orderNo:
                order = await order_crud.get_order_by_no(db, user_id, state.orderNo)
            if not order:
                order = await self._latest_active_order(db, user_id)
            if order and order.status in (OrderStatus.BOOKING.value, OrderStatus.CONFIRMED.value, OrderStatus.DRAFT.value):
                return await self._confirm_payment(db, user_id, text, state.model_copy(update={"orderNo": order.order_no}), ctx)
            if order and order.status == OrderStatus.PAID.value:
                msg = OutboundMessage(channel=state.channel.value, text=f"主人喵，订单【{order.order_no}】已经完成支付出票啦喵~ 随时可以查订单或办理退改喵！")
                return self._finish(db, state, ctx, msg)

        # ② 改签/退票确认路径（ORDER 阶段）
        if state.orderNo and state.phase == SessionPhase.ORDER:
            if self._contains_any(text, CHANGE_CONFIRM_KEYWORDS):
                return await self._confirm_change(db, user_id, text, state, ctx)
            if self._contains_any(text, CANCEL_CONFIRM_KEYWORDS):
                return await self._confirm_cancel(db, user_id, text, state, ctx)

        # ③ 手动登记订单号（兜底 MANUAL_STEP）
        m = MANUAL_ORDER_PATTERN.search(text)
        if m and not state.orderNo:
            order_no = m.group(1)
            await self.booking.register_manual_order(db, user_id, order_no, channel=state.channel.value)
            await self._save_state(db, state.model_copy(update={"phase": SessionPhase.ORDER, "orderNo": order_no}))
            msg = OutboundMessage(channel=state.channel.value, text=f"已登记订单 {order_no}（手动兜底）。")
            ctx.record_event("ORDER_REGISTERED_MANUAL", "ORDER", {"orderNo": order_no}, msg.model_dump())
            return self._finish(db, state, ctx, msg)

        # ③.5 Memory 推断值确认快捷路径（Commit 2）
        # 处于 CLARIFY 且有待确认推断字段时：简短肯定 → 直接按记忆默认值规划；
        # 其它回复（否定/补充修正）→ 清空待确认项，走标准意图流重新理解。
        prior_confirms = []
        if state.phase == SessionPhase.CLARIFY and state.pendingConfirms:
            brief = text.strip().strip("。！!～~ ")
            if MEMORY_CONFIRM_PATTERN.match(brief):
                agent_set = self.agent_factory.get(state.sessionId)
                empty_revised = IntentResultSchema(
                    intent=Intent.PLAN_RECOMMENDATION.value,
                    slots=TravelSlotBundle(),
                    confidence=1.0,
                )
                return await self._handle_plan(db, user_id, text, state, ctx, agent_set, empty_revised, adjust=False)
            prior_confirms = list(state.pendingConfirms)
            state = state.model_copy(update={"pendingConfirms": []})
            await self._save_state(db, state)

        # ③.6 乘客选择回答（分化方案 P0 / Commit 1 & 升级方案）
        if (
            state.phase == SessionPhase.CLARIFY
            and state.passengerSelectionPending
            and state.currentIntent == Intent.PLAN_BOOK
        ):
            profile = await self.memory.get_profile(db, user_id)
            # 优先检查是否输入了新乘车人的身份证号进行实名补全
            id_match = ID_CARD_PATTERN.search(text)
            if id_match:
                id_no = id_match.group(1)
                clean_text = text.replace(id_no, "").strip()
                name_match = re.search(r"(?:叫|名字|姓名|给|帮|乘客)?\s*([\u4e00-\u9fa5]{2,4})", clean_text)
                p_name = name_match.group(1) if name_match else "同行人"
                new_p = {"name": p_name, "id_no": id_no, "id_type": "身份证", "role": "others"}
                updated_profile = await self.memory.update_profile(db, user_id, passengers=[new_p])
                profile = updated_profile
                new_id = profile_crud._new_passenger_id(new_p)
                current_ids = list(state.currentPassengerIds or ["0"])
                if new_id not in current_ids:
                    current_ids.append(new_id)
                resolved_state = state.model_copy(update={
                    "currentPassengerId": new_id,
                    "currentPassengerIds": current_ids,
                    "passengerSelectionPending": False,
                    "passengerSelectionDone": True,
                })
                await self._save_state(db, resolved_state)
                ctx.record_event("PASSENGER_NEW_RECORDED", "PASSENGER", {"name": p_name, "idNo": id_no[:6] + "******"}, {"passengerId": new_id})
                return await self._handle_book(db, user_id, text, resolved_state, ctx)

            chosen_list = resolve_passenger_choices(text, profile)
            chosen = chosen_list[0] if chosen_list else resolve_passenger_choice(text, profile)
            if not chosen:
                question = passenger_selection_question(profile)
                ctx.record_event("PASSENGER_SELECTION_RETRY", "PASSENGER", {"text": text}, {"question": question})
                msg = OutboundMessage(channel=state.channel.value, kind="CLARIFY", text=question, blocks=[])
                return self._finish(db, state, ctx, msg, clarify=True)
            resolved_state = state.model_copy(update={
                "currentPassengerId": chosen,
                "currentPassengerIds": chosen_list or [chosen],
                "passengerSelectionPending": False,
                "passengerSelectionDone": True,
            })
            await self._save_state(db, resolved_state)
            ctx.record_event("PASSENGER_SELECTED", "PASSENGER", {"text": text}, {"passengerId": chosen, "passengerIds": chosen_list or [chosen]})
            return await self._handle_book(db, user_id, text, resolved_state, ctx)

        # ④ 标准意图流
        agent_set = self.agent_factory.get(state.sessionId)
        history = await session_crud.recent_conversation_turns(db, state.sessionId, user_id, 3)
        slot_options = await slot_option_crud.find_all_slot_options(db)

        try:
            raw_intent = await traced_agent_call(
                agent_name="IntentAgent",
                model_name=self.agent_factory.prompt_version,
                chain=agent_set.intent.chain,
                inputs={
                    "user_id": user_id,
                    "session_id": state.sessionId,
                    "history": str(history),
                    "known_slots": str(state.slots.model_dump()),
                    "slot_options": str(slot_options),
                    "user_input": text,
                },
                user_input_text=text,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("IntentAgent 失败，走关键词兜底: %s", e)
            raw_intent = self._fallback_intent(text)
            ctx.record_event("INTENT_FALLBACK", "INTENT", text, raw_intent.model_dump())

        ctx.record_event("INTENT_RECOGNIZED", "INTENT", text, raw_intent.model_dump())
        has_orders = await order_crud.count_orders(db, user_id) > 0
        has_plan = bool(state.lastRecommendations or state.selectedPlanId)
        revised = self.intent_revise.revise(
            state, raw_intent, text, has_orders=has_orders, has_plan=has_plan
        )
        ctx.record_event("INTENT_REVISED", "INTENT", raw_intent.model_dump(), revised.model_dump())
        target = Intent(revised.intent)
        ctx.record_event("ROUTE_SELECTED", "ROUTE", revised.model_dump(), {"route": target.value})
        return await self._route(db, user_id, text, state, ctx, agent_set, revised, target, prior_confirms=prior_confirms)

    # ---------- 路由分发 ----------

    async def _route(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        state: SessionState,
        ctx: TraceContext,
        agent_set,
        revised: IntentResultSchema,
        intent: Intent,
        prior_confirms: Optional[List[str]] = None,
    ) -> OutboundMessage:
        if intent in (Intent.PLAN_RECOMMENDATION, Intent.CLARIFY_NEEDED):
            return await self._handle_plan(db, user_id, text, state, ctx, agent_set, revised, adjust=False, prior_confirms=prior_confirms)
        if intent == Intent.PLAN_ADJUST:
            return await self._handle_plan(db, user_id, text, state, ctx, agent_set, revised, adjust=True, prior_confirms=prior_confirms)
        if intent == Intent.PLAN_BOOK:
            return await self._handle_book(db, user_id, text, state, ctx)
        if intent == Intent.ORDER_QUERY:
            if self._is_trip_query(text):
                return await self._handle_trip_query(db, user_id, state, ctx)
            return await self._handle_order_query(db, user_id, state, ctx)
        if intent == Intent.ORDER_CHANGE:
            return await self._handle_order_change(db, user_id, text, state, ctx, revised)
        if intent == Intent.ORDER_CANCEL:
            return await self._handle_order_cancel(db, user_id, text, state, ctx)
        if intent == Intent.PRICE_MONITOR:
            return await self._handle_price_monitor(db, user_id, text, state, ctx)
        if intent == Intent.CHECKLIST_EXPORT:
            return await self._handle_checklist(db, user_id, state, ctx)
        return await self._handle_other(db, user_id, text, state, ctx)

    async def _handle_plan(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        state: SessionState,
        ctx: TraceContext,
        agent_set,
        revised: IntentResultSchema,
        adjust: bool,
        prior_confirms: Optional[List[str]] = None,
    ) -> OutboundMessage:
        # 调整方案即对上一批推荐的负向反馈（非 Web 通道也能通过对话产生反馈）
        if adjust:
            rejected = state.selectedPlanId or (state.currentBatch[-1] if state.currentBatch else None)
            action = "DISLIKE" if any(k in text for k in ("太贵", "不好", "不喜欢", "不满意")) else "SWITCH"
            await self._record_feedback(db, state, action, plan_id=rejected, reason=f"用户调整方案: {text[:80]}", trace_id=ctx.trace_id)
            await record_user_event(
                db, user_id=user_id, event_type=UserEventType.RECOMMEND_REJECTED,
                session_id=state.sessionId, trace_id=ctx.trace_id,
                context={"planId": rejected, "action": action, "reason": text[:100]},
            )

        # 订单/会话生命周期：若用户主动表达重新规划、或者在 ORDER（已成单）阶段开启新规划，清空上一笔订单的历史槽位
        is_reset = any(kw in text for kw in ("重新规划", "重新来", "重新选", "重头开始", "重置"))
        is_new_plan_from_order = (state.phase == SessionPhase.ORDER and not adjust)
        clean_start = is_reset or is_new_plan_from_order

        history_slots = TravelSlotBundle() if clean_start else state.slots
        merged = self._merge_slots(history_slots, revised.slots)
        merged, fuzzy = await self._resolve_dates(db, merged)
        ctx.record_event("SLOTS_MERGED", "SLOT", {"stateSlots": history_slots.model_dump(), "intentSlots": revised.slots.model_dump()}, merged.model_dump())

        # Commit 2：Memory Resolver —— L1/L3 补全缺失字段并标记来源；高影响推断字段需确认
        profile = await self.memory.get_profile(db, user_id)
        effective_confirms = list(set((state.pendingConfirms or []) + (prior_confirms or [])))
        resolved = self.memory_resolver.resolve(
            merged, profile,
            confirmed_fields=effective_confirms,
            current_passenger_id=state.currentPassengerId,
        )
        planning_slots = resolved.slots
        ctx.record_event(
            EventType.MEMORY_RESOLVED,
            "MEMORY",
            {"userId": user_id},
            resolved.to_dict(),
            memory_sources=sorted({info.source for info in resolved.inferred.values()}),
            inferred_fields={name: info.to_dict() for name, info in resolved.inferred.items()},
        )

        missing = self.clarify_rules.missing_slots(planning_slots, fuzzy_date=fuzzy)
        ctx.record_event(
            "CLARIFY_DECISION", "CLARIFY", planning_slots.model_dump(),
            {
                "action": "ASK" if (missing or resolved.pending_confirm) else "READY",
                "missingSlots": missing,
                "confirmFields": resolved.pending_confirm,
            },
        )

        if missing:
            # 日期先后校验（存在范围时）
            ok, reason = self.date_consistency.check(merged.tripDate, [])
            if not ok and not fuzzy:
                missing.append("tripDate")
                ctx.record_event("DATE_CONFLICT_CHECKED", "CLARIFY", merged.tripDate, {"ok": False, "reason": reason})
            question = await self._ask_clarify(db, state, ctx, agent_set, text, merged, missing)
            p_ids = resolve_passenger_ids_from_slots(merged.passengers, profile) if merged.passengers else []
            clarify_state = state.model_copy(update={
                "phase": SessionPhase.CLARIFY,
                "currentIntent": Intent.CLARIFY_NEEDED,
                "slots": merged,
                "pendingConfirms": [],
                "orderNo": None if clean_start else state.orderNo,
                "orderId": None if clean_start else state.orderId,
                "lastRecommendations": [] if clean_start else state.lastRecommendations,
                "currentBatch": [] if clean_start else state.currentBatch,
                "selectedPlanId": None if clean_start else state.selectedPlanId,
                "passengerSelectionPending": False,
                "passengerSelectionDone": bool(p_ids) if clean_start else (state.passengerSelectionDone or bool(p_ids)),
                "currentPassengerId": p_ids[0] if p_ids else (None if clean_start else state.currentPassengerId),
                "currentPassengerIds": p_ids if p_ids else ([] if clean_start else state.currentPassengerIds),
            })
            await self._save_state(db, clarify_state)
            msg = OutboundMessage(
                channel=state.channel.value,
                kind="CLARIFY",
                text=question,
                blocks=[],
                missing_slots=missing,
            )
            ctx.record_event("RESPONSE_READY", "CLARIFY", {"missing": missing}, msg.model_dump())
            return self._finish(db, clarify_state, ctx, msg, clarify=True)

        # Commit 2：高影响推断字段需显式确认（记忆辅助澄清，不替用户决定）
        if resolved.pending_confirm:
            question = self._memory_confirm_question(resolved)
            p_ids = resolve_passenger_ids_from_slots(merged.passengers, profile) if merged.passengers else []
            confirm_state = state.model_copy(update={
                "phase": SessionPhase.CLARIFY,
                "currentIntent": Intent.CLARIFY_NEEDED,
                "slots": merged,
                "pendingConfirms": resolved.pending_confirm,
                "orderNo": None if clean_start else state.orderNo,
                "orderId": None if clean_start else state.orderId,
                "lastRecommendations": [] if clean_start else state.lastRecommendations,
                "currentBatch": [] if clean_start else state.currentBatch,
                "selectedPlanId": None if clean_start else state.selectedPlanId,
                "passengerSelectionPending": False,
                "passengerSelectionDone": bool(p_ids) if clean_start else (state.passengerSelectionDone or bool(p_ids)),
                "currentPassengerId": p_ids[0] if p_ids else (None if clean_start else state.currentPassengerId),
                "currentPassengerIds": p_ids if p_ids else ([] if clean_start else state.currentPassengerIds),
            })
            await self._save_state(db, confirm_state)
            msg = OutboundMessage(
                channel=state.channel.value,
                kind="CLARIFY",
                text=question,
                blocks=[],
                confirm_fields=resolved.pending_confirm,
            )
            ctx.record_event("RESPONSE_READY", "MEMORY_CONFIRM", {"confirmFields": resolved.pending_confirm}, msg.model_dump())
            return self._finish(db, confirm_state, ctx, msg, clarify=True)

        # 记忆注入（L2 摘要 + L3 长期偏好快照；L1 已由 MemoryResolver 消费）
        memory_context = await self.memory.build_context(db, user_id)
        planning_memory = await self.memory_builder.build_for_planning(db, user_id, resolved)
        similar_context = str(planning_memory.get("similarEpisodes") or [])[:400]
        ctx.record_event(
            "MEMORY_INJECTED", "MEMORY", {"userId": user_id},
            {
                "profile": profile.model_dump() if profile else None,
                "context": memory_context[:300],
                "similarEpisodes": planning_memory.get("similarEpisodes") or [],
            },
        )

        decision = await self.planner.plan(
            db, user_id, planning_slots, profile,
            decision_context=resolved.decision_context(),
        )
        ctx.record_event("PLAN_RANKED", "PLAN", planning_slots.model_dump(), {"optionCount": len(decision.options), "options": [o.plan_id for o in decision.options]})

        if not decision.options:
            reply = "没有满足约束的出行方案，请调整日期、目的地或预算。"
            msg = OutboundMessage(channel=state.channel.value, text=reply)
            return self._finish(db, state, ctx, msg)

        blocks = [self._plan_card(o, plan_no=idx) for idx, o in enumerate(decision.options, 1)]
        top_plans = [{"planId": o.plan_id, "legs": [l.model_dump() for l in o.legs], "totalPrice": o.total_price, "totalDurationH": o.total_duration_h, "score": o.score} for o in decision.options]
        speech = await self._recommend_speech(
            db, state, ctx, agent_set, text, planning_slots, top_plans, decision.reason,
            memory_context=memory_context, similar_context=similar_context,
        )

        plan_ids = [o.plan_id for o in decision.options]
        p_ids = resolve_passenger_ids_from_slots(planning_slots.passengers, profile) if planning_slots.passengers else []
        new_state = state.model_copy(update={
            "phase": SessionPhase.PLAN,
            "currentIntent": Intent.PLAN_RECOMMENDATION,
            "slots": planning_slots,
            "lastRecommendations": plan_ids if clean_start else (list(state.lastRecommendations) + plan_ids),
            "currentBatch": plan_ids,
            "selectedPlanId": decision.recommended.plan_id if decision.recommended else (plan_ids[0] if plan_ids else None),
            "pendingConfirms": [],
            "orderNo": None if clean_start else state.orderNo,
            "orderId": None if clean_start else state.orderId,
            "passengerSelectionPending": False,
            "passengerSelectionDone": bool(p_ids) if clean_start else (state.passengerSelectionDone or bool(p_ids)),
            "currentPassengerId": p_ids[0] if p_ids else (None if clean_start else state.currentPassengerId),
            "currentPassengerIds": p_ids if p_ids else ([] if clean_start else state.currentPassengerIds),
        })
        await self._save_state(db, new_state)
        msg = OutboundMessage(channel=state.channel.value, kind="CARD", text=speech, blocks=blocks)
        ctx.record_event("RESPONSE_READY", "RESPONSE", new_state.model_dump(), msg.model_dump())
        return self._finish(db, new_state, ctx, msg)

    async def _handle_book(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        batch = state.currentBatch or (state.lastRecommendations[-3:] if state.lastRecommendations else [])
        cn_num = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        m_num = re.search(r"方案\s*(\d+|[一二三四五六七八九十]+)|第\s*(\d+|[一二三四五六七八九十]+)\s*个", text)
        selected = None
        if m_num:
            raw = m_num.group(1) or m_num.group(2)
            n = int(raw) if raw.isdigit() else cn_num.get(raw, 0)
            if 1 <= n <= len(batch):
                selected = batch[n - 1]
            else:
                msg = OutboundMessage(channel=state.channel.value, text=f"方案编号超出范围，当前只有 {len(batch)} 个方案（回复“就订第一个”或“方案1/2/3”）。")
                return self._finish(db, state, ctx, msg)
        if not selected:
            selected = state.selectedPlanId
        if not selected and state.lastRecommendations:
            selected = state.lastRecommendations[-1]
        if not selected:
            msg = OutboundMessage(channel=state.channel.value, text="请先选择要下单的方案（回复方案编号或“就订第一个”）。")
            return self._finish(db, state, ctx, msg)

        # 分化方案 P0（Commit 1）：先确认"给谁买"，再记录 LIKE 与下单
        profile = await self.memory.get_profile(db, user_id)
        gate = passenger_selection_gate(profile, state)
        if gate == "ASK":
            question = passenger_selection_question(profile)
            ask_state = state.model_copy(update={
                "phase": SessionPhase.CLARIFY,
                "currentIntent": Intent.PLAN_BOOK,
                "passengerSelectionPending": True,
                "passengerSelectionDone": False,
            })
            await self._save_state(db, ask_state)
            ctx.record_event("PASSENGER_SELECTION_ASKED", "PASSENGER", {"passengerCount": len(profile.passengers or [])}, {"question": question})
            msg = OutboundMessage(channel=state.channel.value, kind="CLARIFY", text=question, blocks=[])
            return self._finish(db, ask_state, ctx, msg, clarify=True)

        # 用户以消息方式选择方案 → 记录正向反馈（LIKE），供评估系统使用
        await self._record_feedback(db, state, "LIKE", plan_id=str(selected), reason=f"用户选择方案下单: {text[:80]}", trace_id=ctx.trace_id)
        await record_user_event(
            db, user_id=user_id, event_type=UserEventType.RECOMMEND_ACCEPTED,
            session_id=state.sessionId, trace_id=ctx.trace_id,
            context={"planId": str(selected), "reason": text[:100]},
        )

        plan_row = await trip_crud.get_plan(db, int(selected))
        if not plan_row:
            msg = OutboundMessage(channel=state.channel.value, text="所选方案已失效，请重新规划。")
            return self._finish(db, state, ctx, msg)
        plan = PlanOption(**plan_row.plan_json)

        passenger_id = gate if gate != "ASK" else "0"
        resolved_slot_ids = []
        if state.slots and state.slots.passengers:
            resolved_slot_ids = resolve_passenger_ids_from_slots(state.slots.passengers, profile)
        target_ids = set(state.currentPassengerIds or resolved_slot_ids or ([passenger_id] if passenger_id else ["0"]))
        profile_passengers = profile.passengers or []
        passengers = [
            p for p in profile_passengers
            if str(p.get("passenger_id") or "") in target_ids
        ]
        # 若 slots.passengers 指定了乘客姓名，匹配已有乘客
        if state.slots.passengers:
            for p in profile_passengers:
                p_name = str(p.get("name") or "")
                p_id = str(p.get("passenger_id") or "")
                if (p_name in state.slots.passengers or p_id in state.slots.passengers) and p not in passengers:
                    passengers.append(p)
        if not passengers:
            passengers = [
                p for p in profile_passengers
                if str(p.get("passenger_id") or "") == str(passenger_id)
            ] or None
        order = await self.booking.create_order_draft(
            db,
            user_id,
            plan,
            passengers=passengers,
            channel=state.channel.value,
            trip_id=plan_row.trip_id,
        )
        # 幂等复用已有订单时：已支付订单不允许重复下单；
        # 否则把订单通道对齐当前会话通道，确保二维码/支付结果推送到用户当前所在通道
        if order.status == OrderStatus.PAID.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"该方案已下单并支付出票（订单 {order.order_no}）。可回复“查订单”查看，或办理改签/退票。",
            )
            return self._finish(db, state, ctx, msg)
        if order.channel != state.channel.value:
            await order_crud.update_order(db, order.id, channel=state.channel.value)
            order.channel = state.channel.value

        task_id = await self.task_service.create(
            db,
            user_id,
            TaskType.book.value,
            {"plan_id": selected, "order_no": order.order_no},
            channel=state.channel.value,
            session_id=state.sessionId,
            order_id=order.id,
        )
        await order_crud.update_order(db, order.id, task_id=task_id)
        ctx.record_event("BOOKING_STARTED", "BOOKING", {"planId": selected}, {"orderNo": order.order_no, "taskId": task_id})

        new_state = state.model_copy(update={
            "phase": SessionPhase.BOOKING,
            "currentIntent": Intent.PLAN_BOOK,
            "orderId": order.id,
            "orderNo": order.order_no,
            "passengerSelectionPending": False,
            "passengerSelectionDone": True,
            "currentPassengerId": passenger_id,
            "currentPassengerIds": list(target_ids),
        })
        await self._save_state(db, new_state)

        # 后台执行下单（Playwright Mock 收银台：确认订单 → 截图二维码 → WAITING_USER）
        asyncio.create_task(self.task_service.run(task_id, lambda db: self.booking.execute_booking(db, task_id, order)))
        # 三层支付检测监控（第1层页面变化 / 第2层订单轮询；第3层用户确认走快捷路径）
        asyncio.create_task(self._payment_monitor(user_id, order, new_state))
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="TASK_PROGRESS",
            text=f"已为您锁定席位并生成订单 {order.order_no}，请在下方订单卡片中完成支付。支付完成后点击『我已完成支付』或回复『付好了』即可出票。",
            task_progress={"taskId": task_id, "status": "RUNNING", "progress": 10, "orderNo": order.order_no},
            correlation_id=task_id,
        )
        ctx.record_event("RESPONSE_READY", "BOOKING", new_state.model_dump(), msg.model_dump())
        return self._finish(db, new_state, ctx, msg)

    async def _confirm_payment(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        order = await order_crud.get_order_by_no(db, user_id, state.orderNo or "")
        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="未找到待支付订单。")
            return self._finish(db, state, ctx, msg)
        if order.status == OrderStatus.PAID.value:
            msg = OutboundMessage(channel=state.channel.value, text=f"订单 {order.order_no} 已支付出票。")
            return self._finish(db, state, ctx, msg)
        updated = await self.booking.confirm_payment(db, order.task_id, order)
        ctx.record_event("PAYMENT_DETECTED", "PAYMENT", {"orderNo": order.order_no}, {"layer": 3})
        new_state = await self._finalize_payment(db, user_id, updated, state, ctx)
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="CARD",
            text=f"✅ 订单 {order.order_no} 已支付出票（Mock 供应商）。可回复“查订单”查看，或办理改签/退票。",
            blocks=[{"orderNo": order.order_no, "status": updated.status, "price": order.price}],
        )
        ctx.record_event("RESPONSE_READY", "PAYMENT", new_state.model_dump(), msg.model_dump())
        return self._finish(db, new_state, ctx, msg)

    async def _finalize_payment(
        self,
        db: AsyncSession,
        user_id: int,
        order: TravelOrderRow,
        state: SessionState,
        ctx: Optional[TraceContext] = None,
    ) -> SessionState:
        """支付确认后的统一收尾：L1 画像写入 + L2 摘要 + 注册价格监控 + 阶段落库（幂等）。"""
        await self._write_profile_after_booking(db, user_id, order, state)
        asyncio.create_task(self._write_summary_async(user_id, order, state))
        await self.task_service.create(
            db, user_id, TaskType.price_watch.value,
            {"order_no": order.order_no, "phase": 2}, channel=state.channel.value, order_id=order.id,
        )
        new_state = state.model_copy(update={
            "phase": SessionPhase.ORDER,
            "currentIntent": Intent.ORDER_QUERY,
            "slots": TravelSlotBundle(),
            "lastRecommendations": [],
            "currentBatch": [],
            "selectedPlanId": None,
            "pendingConfirms": [],
            "passengerSelectionPending": False,
            "passengerSelectionDone": False,
            "currentPassengerId": None,
            "currentPassengerIds": [],
        })
        await self._save_state(db, new_state)
        if ctx:
            ctx.record_event("PAYMENT_CONFIRMED", "PAYMENT", {"orderNo": order.order_no}, {"status": order.status})
        return new_state

    async def _payment_monitor(self, user_id: int, order: TravelOrderRow, state: SessionState):
        """三层支付检测监控（后台协程）：
        第1层 Playwright 页面变化检测（Mock 收银台「支付成功」元素）；
        第2层 Mock 供应商订单状态轮询；第3层由用户「付好了」快捷路径完成。
        前两层任一命中 → 与第3层同一套收尾逻辑（confirm_payment 幂等）。
        """
        import time as _time

        from app.config import settings as _settings

        paid_event = mock_supplier.get_paid_event(order.order_no)
        start = _time.time()
        deadline = start + _settings.TRAVEL_PAYMENT_MONITOR_TIMEOUT
        while _time.time() < deadline:
            try:
                async with async_session_maker() as db:
                    cur = await order_crud.get_order_by_no(db, user_id, order.order_no)
                    if cur and cur.status == OrderStatus.PAID.value:
                        # 第3层用户已确认，关闭浏览器会话
                        await browser_order.close(order.order_no)
                        return
                    layer1 = await browser_order.check_paid(order.order_no)
                    layer2 = mock_supplier.is_paid(order.order_no)
                    if layer1 or layer2:
                        layer = 1 if layer1 else 2
                        log.info("三层支付检测命中 layer=%s order=%s", layer, order.order_no)
                        async with TraceScope(db, state.sessionId, user_id, run_id=f"payment_monitor:{order.order_no}") as ctx:
                            ctx.record_event("PAYMENT_DETECTED", "PAYMENT", {"orderNo": order.order_no}, {"layer": layer})
                            target = cur or order
                            updated = await self.booking.confirm_payment(
                                db, target.task_id, target, push_success=True,
                            )
                            await self._finalize_payment(db, user_id, updated, state, ctx)
                            await browser_order.close(order.order_no)
                        return
            except Exception as e:  # noqa: BLE001
                log.warning("支付监控异常 order=%s: %s", order.order_no, e)
            # 自适应等待：事件实时唤醒或短周期轮询（前 2 分钟每 2 秒，之后每 10 秒）
            elapsed = _time.time() - start
            poll_timeout = 2.0 if elapsed < 120 else 10.0
            try:
                await asyncio.wait_for(paid_event.wait(), timeout=poll_timeout)
            except asyncio.TimeoutError:
                pass
        await browser_order.close(order.order_no)
        log.info("三层支付检测超时，保持 WAITING_USER（用户仍可回复“付好了”确认）: order=%s", order.order_no)

    async def _handle_order_query(self, db: AsyncSession, user_id: int, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        orders = await order_crud.list_orders(db, user_id)
        if not orders:
            msg = OutboundMessage(channel=state.channel.value, text="你还没有任何订单。需要我帮你规划一次出行吗？")
            return self._finish(db, state, ctx, msg)
        lines = ["你的订单如下："]
        blocks = []
        for o in orders:
            trip = await trip_crud.get_trip(db, o.trip_id)
            date_label = str(trip.start_date) if trip and trip.start_date else ""
            header = f"- {o.order_no}：{o.type} / {o.status} / ¥{o.price:.0f}"
            if date_label:
                header += f" / {date_label} 出发"
            lines.append(header)
            legs = self._order_legs(o)
            if legs:
                lines.extend(self._leg_lines(legs, indent="   "))
            blocks.append({
                "orderNo": o.order_no,
                "type": o.type,
                "status": o.status,
                "price": o.price,
                "tripDate": date_label,
                "legs": legs,
            })
        is_web = getattr(state.channel, "value", str(state.channel)) == "web"
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="CARD",
            text=f"已为您查询到 {len(orders)} 笔历史订单。" if is_web else "\n".join(lines),
            blocks=blocks,
        )
        ctx.record_event("ORDER_QUERIED", "ORDER", {"userId": user_id}, {"count": len(orders)})
        new_state = state.model_copy(update={"currentIntent": Intent.ORDER_QUERY})
        return self._finish(db, new_state, ctx, msg)

    async def _handle_trip_query(self, db: AsyncSession, user_id: int, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        """查行程：展示行程单（车次/站点/时刻），与订单列表区分开。"""
        orders = await order_crud.list_orders(db, user_id)
        active_statuses = {
            OrderStatus.PAID.value, OrderStatus.BOOKING.value, OrderStatus.CONFIRMED.value,
            OrderStatus.CHANGING.value, OrderStatus.CHANGED.value,
        }
        active = [o for o in orders if o.status in active_statuses]
        # 同一行程（trip_id）只展示最新一条；无 trip_id 的订单按订单号独立展示
        seen_trips = set()
        items = []
        for o in active:
            key = o.trip_id or f"ord:{o.order_no}"
            if key in seen_trips:
                continue
            seen_trips.add(key)
            items.append(o)

        lines: List[str] = []
        blocks = []
        if len(items) > 1:
            lines.append(f"共 {len(items)} 个进行中行程：")
        for i, order in enumerate(items, 1):
            legs = self._order_legs(order)
            if not legs:
                continue
            trip = await trip_crud.get_trip(db, order.trip_id)
            date_label = str(trip.start_date) if trip and trip.start_date else "日期未知"
            dest = (trip.destination if trip and trip.destination else None) or (legs[-1].get("to_city") or "目的地")
            lines.append("─" * 26)
            lines.append(f"【行程{i}】{legs[0].get('from_city') or '出发地'} → {dest} · {date_label} 出发")
            lines.extend(self._leg_lines(legs))
            lines.append(f"共 {len(legs)} 段 · 合计 ¥{sum(float(l.get('price') or 0) for l in legs):.0f}")
            blocks.append({"orderNo": order.order_no, "tripDate": date_label, "legs": legs})
        if lines:
            msg = OutboundMessage(
                channel=state.channel.value,
                kind="CARD",
                text="📋 行程单\n" + "\n".join(lines),
                blocks=blocks,
            )
            ctx.record_event("TRIP_QUERIED", "TRIP", {"userId": user_id}, {"count": len(items), "orders": [o.order_no for o in items]})
            new_state = state.model_copy(update={"currentIntent": Intent.ORDER_QUERY})
            return self._finish(db, new_state, ctx, msg)

        # 无有效订单：回退当前会话已选方案
        if state.selectedPlanId:
            plan_row = await trip_crud.get_plan(db, int(state.selectedPlanId))
            if plan_row:
                plan = PlanOption(**plan_row.plan_json)
                trip = await trip_crud.get_trip(db, plan_row.trip_id)
                date_label = str(trip.start_date) if trip and trip.start_date else "日期未知"
                legs = [l.model_dump() for l in plan.legs]
                dest = (trip.destination if trip and trip.destination else None) or (legs[-1].get("to_city") or "目的地")
                lines = [f"📋 行程单（规划中）· {date_label} 出发"]
                lines.append(f"{legs[0].get('from_city') or '出发地'} → {dest}")
                lines.append("─" * 26)
                lines.extend(self._leg_lines(legs))
                lines.append("─" * 26)
                lines.append(f"共 {len(legs)} 段 · 合计 ¥{sum(float(l.get('price') or 0) for l in legs):.0f}")
                msg = OutboundMessage(
                    channel=state.channel.value,
                    kind="CARD",
                    text="\n".join(lines),
                    blocks=[{"tripDate": date_label, "legs": legs}],
                )
                ctx.record_event("TRIP_QUERIED", "TRIP", {"userId": user_id}, {"source": "plan"})
                return self._finish(db, state, ctx, msg)

        msg = OutboundMessage(
            channel=state.channel.value,
            text="你还没有已预订或进行中的行程。回复“帮我规划一下”开始安排出行。",
        )
        return self._finish(db, state, ctx, msg)

    async def _handle_order_change(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        state: SessionState,
        ctx: TraceContext,
        revised: IntentResultSchema,
    ) -> OutboundMessage:
        target_order_no = None
        m = re.search(r"ORD\d+", text or "")
        if m:
            target_order_no = m.group(0)
        elif state.orderNo:
            target_order_no = state.orderNo

        order = None
        if target_order_no:
            order = await order_crud.get_order_by_no(db, user_id, target_order_no)
        if not order:
            order = await self._latest_active_order(db, user_id)

        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="主人喵，鱼鱼没有找到可以改签的有效订单喵~")
            return self._finish(db, state, ctx, msg)

        # 状态互斥校验：已退票/已改签/处理中订单拦截
        if order.status in (OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value):
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】已经处于退票/取消状态，无法办理改签了喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.REFUNDING.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】正在退票处理中，不能办理改签喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.CHANGED.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】已经办理过一次改签啦，根据铁路/航司客规，每笔订单仅支持改签一次，不能再次改签了喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.CHANGING.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】正在改签处理中，请稍候查看改签结果，无需重复申请喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status not in (OrderStatus.PAID.value, OrderStatus.CONFIRMED.value):
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】当前状态为【{order.status}】，暂不支持改签操作喵~",
            )
            return self._finish(db, state, ctx, msg)

        merged = self._merge_slots(state.slots, revised.slots)
        merged, fuzzy = await self._resolve_dates(db, merged)
        target_date = (merged.tripDate or [None])[0]
        if not target_date:
            msg = OutboundMessage(channel=state.channel.value, text="主人想改到哪一天呢喵？请告诉我具体出行日期，鱼鱼来为您对比改签方案喵~")
            new_state = state.model_copy(update={"phase": SessionPhase.ORDER, "slots": merged, "orderNo": order.order_no})
            await self._save_state(db, new_state)
            return self._finish(db, new_state, ctx, msg)

        profile = await self.memory.get_profile(db, user_id)
        request = ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.USER_CHANGE, target_date=target_date)
        change_ctx = await self.memory_builder.build_for_change(db, user_id, order)
        decision = await self.change_decision.decide(db, request, order, profile, context=change_ctx)
        ctx.record_event("ORDER_CHANGE_DECISION", "DECISION", request.model_dump(), decision.model_dump())

        new_state = state.model_copy(update={
            "phase": SessionPhase.ORDER,
            "currentIntent": Intent.ORDER_CHANGE,
            "orderNo": order.order_no,
            "slots": merged,
        })
        await self._save_state(db, new_state)
        msg = self._decision_card(state.channel.value, decision, prefix="🔀 改签方案对比")
        ctx.record_event("RESPONSE_READY", "DECISION", new_state.model_dump(), msg.model_dump())
        return self._finish(db, new_state, ctx, msg)

    async def _confirm_change(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        target_order_no = None
        m = re.search(r"ORD\d+", text or "")
        if m:
            target_order_no = m.group(0)
        elif state.orderNo:
            target_order_no = state.orderNo

        order = None
        if target_order_no:
            order = await order_crud.get_order_by_no(db, user_id, target_order_no)
        if not order:
            order = await self._latest_active_order(db, user_id)

        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="主人喵，没有可改签的订单喵。")
            return self._finish(db, state, ctx, msg)

        if order.status in (OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value, OrderStatus.CHANGED.value, OrderStatus.CHANGING.value, OrderStatus.REFUNDING.value):
            msg = OutboundMessage(channel=state.channel.value, text=f"主人喵，订单【{order.order_no}】当前状态为【{order.status}】，不支持改签喵~")
            return self._finish(db, state, ctx, msg)

        target_date = (state.slots.tripDate or [None])[0] or (await self._today_plus(2))
        profile = await self.memory.get_profile(db, user_id)
        decision = await self.change_decision.decide(
            db,
            ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.USER_CHANGE, target_date=target_date),
            order,
            profile,
            context=await self.memory_builder.build_for_change(db, user_id, order),
        )
        task_id = await self.task_service.create(
            db, user_id, TaskType.change.value,
            {"order_no": order.order_no, "target_date": target_date},
            channel=state.channel.value, session_id=state.sessionId, order_id=order.id,
        )
        asyncio.create_task(self.task_service.run(task_id, lambda db: self.booking.execute_change(db, task_id, order, decision)))
        ctx.record_event(EventType.ORDER_CHANGED, "CHANGE", {"orderNo": order.order_no}, {"taskId": task_id, "decision": decision.reason})
        await record_user_event(
            db, user_id=user_id, event_type=UserEventType.CHANGE_CONFIRMED,
            session_id=state.sessionId, task_id=task_id, trace_id=ctx.trace_id, order_no=order.order_no,
            context={"targetDate": target_date, "reason": decision.reason[:200]},
        )
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="TASK_PROGRESS",
            text=f"改签任务已启动（{task_id}）：{decision.reason}",
            task_progress={"taskId": task_id, "status": "RUNNING", "progress": 10},
        )
        return self._finish(db, state, ctx, msg)

    async def _handle_order_cancel(
        self,
        db: AsyncSession,
        user_id: int,
        text: str,
        state: SessionState,
        ctx: TraceContext,
    ) -> OutboundMessage:
        target_order_no = None
        m = re.search(r"ORD\d+", text or "")
        if m:
            target_order_no = m.group(0)
        elif state.orderNo:
            target_order_no = state.orderNo

        order = None
        if target_order_no:
            order = await order_crud.get_order_by_no(db, user_id, target_order_no)
        if not order:
            order = await self._latest_active_order(db, user_id)

        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="主人喵，鱼鱼没有找到可以退票的有效订单喵~")
            return self._finish(db, state, ctx, msg)

        # 状态机互斥校验：已退票/已改签/处理中订单拦截
        if order.status in (OrderStatus.REFUNDED.value, OrderStatus.CANCELLED.value):
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】已经处于退票/取消状态啦，不能再次申请退票或改签了喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.REFUNDING.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】正在退票处理中，款项会原路退回，请勿重复申请喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.CHANGING.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】正在改签处理中，请稍候查看改签结果，暂不可申请退票喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status == OrderStatus.CHANGED.value:
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】已经办理过改签啦，根据客运规定已改签订单不可再次办理退改喵~",
            )
            return self._finish(db, state, ctx, msg)

        if order.status not in (OrderStatus.PAID.value, OrderStatus.CONFIRMED.value):
            msg = OutboundMessage(
                channel=state.channel.value,
                text=f"主人喵，订单【{order.order_no}】当前状态为【{order.status}】，暂不支持退票操作喵~",
            )
            return self._finish(db, state, ctx, msg)

        # 退票直接退：无需再走损失模型两阶段对比
        task_id = await self.task_service.create(
            db, user_id, TaskType.refund.value,
            {"order_no": order.order_no}, channel=state.channel.value, session_id=state.sessionId, order_id=order.id,
        )
        await self.booking.execute_refund(db, task_id, order)
        ctx.record_event(EventType.ORDER_REFUNDED, "REFUND", {"orderNo": order.order_no}, {"taskId": task_id, "refundAmount": float(order.price or 0)})
        await record_user_event(
            db, user_id=user_id, event_type=UserEventType.REFUND_CONFIRMED,
            session_id=state.sessionId, task_id=task_id, trace_id=ctx.trace_id, order_no=order.order_no,
            context={"refundAmount": float(order.price or 0)},
        )

        legs_data = (order.legs or {}).get("legs", []) if isinstance(order.legs, dict) else []
        route_desc = f"{legs_data[0].get('from_city', '')} ➔ {legs_data[-1].get('to_city', '')}" if legs_data else "行程车票"
        vehicle_code = legs_data[0].get("vehicle_no") if legs_data else None
        vehicle_desc = f"（{vehicle_code}）" if vehicle_code else ""
        price = float(order.price or 0)

        refund_text = (
            f"主人喵~ 订单【{order.order_no}】已经为您成功办理退票与退款啦！🎉\n\n"
            f"• **退票车票**：{route_desc} {vehicle_desc}\n"
            f"• **退款金额**：¥{price:.2f}（全额原路退款，0 手续费）\n"
            f"• **退款渠道**：原支付方式原路退回\n"
            f"• **预计到账**：1~3 个工作日内\n"
            f"• **订单状态**：【已全额退票】\n\n"
            f"鱼鱼已经把订单中心的履约状态更新为【已退票】啦，主人可以安心去吃香喷喷的白米饭咯喵~ (开心地摆摆尾巴)"
        )

        new_state = state.model_copy(update={
            "phase": SessionPhase.ORDER,
            "currentIntent": Intent.ORDER_CANCEL,
            "orderNo": order.order_no,
        })
        await self._save_state(db, new_state)

        msg = OutboundMessage(
            channel=state.channel.value,
            kind="CARD",
            text=refund_text,
            task_progress={"taskId": task_id, "status": "SUCCESS", "progress": 100},
        )
        return self._finish(db, new_state, ctx, msg)

    async def _confirm_cancel(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        return await self._handle_order_cancel(db, user_id, text, state, ctx)

    async def _handle_price_monitor(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        profile = await self.memory.get_profile(db, user_id)
        prefs = dict(profile.preferences) if profile and profile.preferences else {}
        turning_off = "关" in text or "停" in text or "不要" in text
        prefs["price_monitor"] = False if turning_off else True
        await self.memory.update_profile(db, user_id, preferences=prefs)
        enabled = not turning_off
        await record_user_event(
            db, user_id=user_id, event_type=UserEventType.MONITOR_TOGGLED,
            session_id=state.sessionId, trace_id=ctx.trace_id,
            context={"enabled": enabled, "reason": text[:80]},
        )
        status = "已关闭" if turning_off else "已开启（默认开启）"
        msg = OutboundMessage(channel=state.channel.value, text=f"价格监控{status}，降价超过阈值时我会推送方案。")
        ctx.record_event("PRICE_MONITOR_TOGGLED", "MONITOR", {"userId": user_id}, {"enabled": not turning_off})
        return self._finish(db, state, ctx, msg)

    async def _handle_checklist(self, db: AsyncSession, user_id: int, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        orders = await self.booking.list_orders(db, user_id)
        legs = []
        destination = "目的地"
        if orders:
            latest = orders[0]
            legs = [TransportLeg(**l) for l in latest.legs]
            if legs:
                destination = legs[-1].to_city
        weather = await self.collector.hourly_weather(db, 30.0, 110.0, hours=12)
        md = await self.checklist.generate(db, legs, destination, weather, skill_context=load_skill("travel-checklist"))
        ctx.record_event("CHECKLIST_GENERATED", "CHECKLIST", {"destination": destination}, {"legs": len(legs)})
        msg = OutboundMessage(channel=state.channel.value, text=md, kind="CARD")
        return self._finish(db, state, ctx, msg)

    async def _handle_other(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        passed, reasons, rewrite = self.risk_guard.check(text, Intent.OTHER, CHITCHAT_REPLY)
        reply = rewrite if not passed else CHITCHAT_REPLY
        if not passed:
            ctx.record_event("NUTRITION_GUARD_REWRITTEN", "GUARD", reasons, {"speechText": reply})
        msg = OutboundMessage(channel=state.channel.value, text=reply)
        return self._finish(db, state, ctx, msg)

    # ---------- 工具方法 ----------

    @staticmethod
    def _memory_confirm_question(resolved) -> str:
        """记忆推断确认话术（Commit 2）：模板生成，确定性可测，避免每次确认都调 LLM。"""
        parts = []
        slots = resolved.slots
        for name in resolved.pending_confirm:
            if name == "origin":
                parts.append(f"从{slots.origin[0]}出发")
            elif name == "budget":
                parts.append(f"{slots.budget[0]}预算")
            elif name == "transportMode":
                parts.append(f"偏好{slots.transportMode[0]}")
            else:
                parts.append(str(resolved.inferred[name].value))
        return "好的。还是按你平时常用的" + "、".join(parts) + "来帮你规划吗？回复“好”即可，或直接告诉我需要调整的地方。"

    async def _ask_clarify(self, db, state, ctx, agent_set, user_input, merged, missing) -> str:
        try:
            question = await traced_agent_call(
                agent_name="ClarifyAgent",
                model_name=self.agent_factory.prompt_version,
                chain=agent_set.clarify.chain,
                inputs={
                    "user_input": user_input,
                    "known_slots": str(merged.model_dump()),
                    "missing_slots": str(missing),
                },
                user_input_text=user_input,
            )
            question = (question or "").strip()
            return question if question else self.clarify_rules.fallback_question(missing)
        except Exception:  # noqa: BLE001
            return self.clarify_rules.fallback_question(missing)

    async def _recommend_speech(
        self, db, state, ctx, agent_set, user_input, slots, top_plans, fallback_reason,
        memory_context: str = "", similar_context: str = "",
    ) -> str:
        body = self._plan_template(top_plans, fallback_reason)
        try:
            res = await traced_agent_call(
                agent_name="PlanRecommendAgent",
                model_name=self.agent_factory.prompt_version,
                chain=agent_set.recommend_plan.chain,
                inputs={
                    "user_input": user_input,
                    "slots": str(slots.model_dump()),
                    "top_plans": str(top_plans),
                    "memory_context": memory_context or "（暂无）",
                    "similar_context": similar_context or "（暂无相似案例）",
                },
                user_input_text=user_input,
            )
            intro = (res.speechText or "").strip()
            return f"{intro}\n{body}" if intro else body
        except Exception:  # noqa: BLE001
            return body

    def _plan_template(self, top_plans: List[dict], reason: str) -> str:
        lines = [f"为你找到 {len(top_plans)} 个出行方案（按综合评分排序）："]
        for idx, p in enumerate(top_plans, 1):
            lines.append("─" * 26)
            lines.append(f"【方案{idx}】总价 ¥{p['totalPrice']:.0f} · 总耗时约 {p['totalDurationH']:.1f}h")
            lines.extend(self._leg_lines(p["legs"]))
        lines.append("─" * 26)
        if reason:
            lines.append(f"推荐理由：{reason}")
        lines.append("回复“就订第一个”或“方案2”可下单；“换一批”重新生成。")
        return "\n".join(lines)

    @staticmethod
    def _leg_lines(legs: List[dict], indent: str = "  ") -> List[str]:
        """行程段格式化：车次/航班、站点、时刻、席别、段价。"""
        lines = []
        for l in legs:
            mode_label = {
                "FLIGHT": "飞机", "TRAIN": "火车", "BUS": "大巴", "TRANSFER": "换乘",
            }.get(l.get("mode"), l.get("mode") or "")
            arrive_day = int(l.get("arrive_day") or 1)
            day_mark = "（次日到达）" if arrive_day > 1 else ""
            lines.append(
                f"{indent}第{l.get('leg_no', 1)}段 · {mode_label} {l.get('vehicle_no') or '-'}："
                f"{l.get('from_station') or l.get('from_city')} {l.get('depart')} → "
                f"{l.get('to_station') or l.get('to_city')} {l.get('arrive')}{day_mark}，"
                f"{l.get('seat') or '-'} ¥{float(l.get('price') or 0):.0f}"
            )
        return lines

    @staticmethod
    def _order_legs(order) -> List[dict]:
        """订单 legs 兼容 dict（{"legs": [...]}）与 list 两种存储形态。"""
        raw = getattr(order, "legs", None)
        if isinstance(raw, dict):
            return raw.get("legs") or []
        return raw or []

    @staticmethod
    def _is_trip_query(text: str) -> bool:
        """ORDER_QUERY 下的细分：含“行程”且不含“订单/票”时按行程单展示。"""
        t = text or ""
        if "订单" in t or "票" in t:
            return False
        return "行程" in t

    def _plan_card(self, o: PlanOption, plan_no: int = 0) -> dict:
        return {
            "planNo": plan_no,
            "planId": o.plan_id,
            "legs": [l.model_dump() for l in o.legs],
            "totalPrice": o.total_price,
            "totalDurationH": o.total_duration_h,
            "meetsBudget": o.meets_budget,
            "score": o.score,
            "summary": o.summary(),
        }

    def _decision_card(self, channel: str, decision, prefix: str) -> OutboundMessage:
        lines = [prefix, "─────────────────────────"]
        for i, opt in enumerate(decision.options):
            kind = {
                "CHANGE": "改签", "CANCEL_REBOOK": "取消重买", "CANCEL": "取消退票", "KEEP": "保持原行程",
            }.get(opt.kind.value, opt.kind.value)
            lines.append(
                f"方案{'ABCD'[i] if i < 4 else str(i)} {kind}："
                f"损失 ¥{opt.total_loss:.0f}" + (f"（省 ¥{-opt.total_loss:.0f}）" if opt.total_loss < 0 else "")
            )
            for risk in opt.risks:
                lines.append(f"  风险：{risk}")
        lines.append(f"推荐：{decision.reason}")
        lines.append("回复“确认改签”/“确认退票”执行。")

        req = getattr(decision, "request", None)
        rec = getattr(decision, "recommended", None)
        rec_kind = rec.kind.value if (rec and hasattr(rec.kind, "value")) else ("CHANGE" if rec else None)

        decision_block = {
            "blockType": "CHANGE_DECISION",
            "orderNo": getattr(req, "order_no", None),
            "targetDate": getattr(req, "target_date", None),
            "reason": decision.reason,
            "recommendedKind": rec_kind,
            "options": [
                {
                    "kind": o.kind.value if hasattr(o.kind, "value") else str(o.kind),
                    "old_price": float(o.old_price or 0),
                    "new_price": float(o.new_price or 0),
                    "change_fee": float(o.change_fee or 0),
                    "refund_fee": float(o.refund_fee or 0),
                    "total_loss": float(o.total_loss or 0),
                    "risks": o.risks or [],
                    "original_leg": o.original_leg,
                    "new_leg": o.new_leg,
                    "detail": o.detail or {},
                }
                for o in decision.options
            ],
        }

        return OutboundMessage(
            channel=channel,
            kind="CARD",
            text="\n".join(lines),
            blocks=[decision_block, *(o.model_dump() for o in decision.options)],
        )

    async def _resolve_dates(self, db, slots: TravelSlotBundle):
        """将 tripDate 自由值解析为具体日期；模糊则保留原值并置 fuzzy。"""
        fuzzy = False
        resolved: List[str] = []
        for raw in slots.tripDate:
            result = self.date_resolver.resolve(raw)
            if result.fuzzy:
                fuzzy = True
            resolved.extend(result.dates)
        if resolved and not fuzzy:
            # 去重保序
            seen = set()
            unique = [d for d in resolved if not (d in seen or seen.add(d))]
            slots = slots.model_copy(update={"tripDate": unique})
        return slots, fuzzy

    def _merge_slots(self, history: TravelSlotBundle, current: TravelSlotBundle) -> TravelSlotBundle:
        def choose(h: List[str], c: List[str]) -> List[str]:
            return c if c else h
        return TravelSlotBundle(
            origin=choose(history.origin, current.origin),
            destination=choose(history.destination, current.destination),
            tripDate=choose(history.tripDate, current.tripDate),
            returnDate=choose(history.returnDate, current.returnDate),
            budget=choose(history.budget, current.budget),
            travelStyle=choose(history.travelStyle, current.travelStyle),
            transportMode=choose(history.transportMode, current.transportMode),
            companion=choose(history.companion, current.companion),
            passengers=choose(history.passengers, current.passengers),
        )

    async def _latest_active_order(self, db: AsyncSession, user_id: int) -> Optional[TravelOrderRow]:
        orders = await order_crud.list_orders(db, user_id)
        active = [o for o in orders if o.status in (
            OrderStatus.PAID.value, OrderStatus.BOOKING.value,
            OrderStatus.CONFIRMED.value, OrderStatus.CHANGING.value, OrderStatus.CHANGED.value,
        )]
        return active[0] if active else None

    @staticmethod
    def _is_early_departure(depart: str) -> bool:
        """是否早班：首段出发时刻早于 08:00（Commit 0 规则写入 early_bird 偏好）。"""
        if not depart:
            return False
        try:
            hour = int(str(depart).split(":", 1)[0])
        except (TypeError, ValueError):
            return False
        return 0 <= hour < 8

    async def _write_profile_after_booking(self, db, user_id, order, state):
        legs = (order.legs or {}).get("legs", [])
        home_city = legs[0].get("from_city") if legs else None
        passengers = (order.passengers or {}).get("list", [])
        budget_label = (state.slots.budget or [None])[0]
        budget_level = {"经济型": "economy", "舒适型": "comfort", "高端型": "premium"}.get(budget_label) if budget_label else None
        fields = {}
        if home_city:
            fields["home_city"] = home_city
        if passengers:
            fields["passengers"] = passengers
        if budget_level:
            fields["budget_level"] = budget_level
        if legs and self._is_early_departure(legs[0].get("depart", "")):
            fields["preferences"] = {"early_bird": True}
        if fields:
            await self.memory.update_profile(db, user_id, **fields)
            ctx = active_trace_ctx.get()
            if ctx:
                ctx.record_event("MEMORY_WRITTEN", "MEMORY", {"userId": user_id}, fields)

    async def _write_summary_async(self, user_id: int, order, state):
        """L2 行程摘要：轻量 LLM 生成 + 模板兜底（后台异步）。"""
        try:
            async with async_session_maker() as db:
                legs = (order.legs or {}).get("legs", [])
                md = await self._build_summary_md(db, user_id, order, legs)
                episode = self._build_episode(user_id, order, state, legs)
                await self.memory.add_trip_summary(db, user_id, order.trip_id, md, episode=episode)
        except Exception as e:  # noqa: BLE001
            log.warning("L2 摘要写入失败: %s", e)

    def _build_episode(self, user_id: int, order, state, legs: List[dict]) -> dict:
        """构造结构化 Episode（L2，Commit 1）：程序字段落库；decision_reason/rating 本轮留空。"""
        first = legs[0] if legs else {}
        last = legs[-1] if legs else {}
        passengers = (order.passengers or {}).get("list", [])
        slots = state.slots.model_dump() if state and state.slots else {}
        return {
            "trip_id": order.trip_id,
            "user_id": user_id,
            "passengers": [
                p.get("passenger_id") or p.get("id_no") or p.get("name")
                for p in passengers
            ],
            "context": {
                "origin": first.get("from_city"),
                "destination": last.get("to_city"),
                "purpose": (slots.get("travelStyle") or [None])[0],
            },
            "constraints": {
                k: slots.get(k)
                for k in (
                    "origin", "destination", "tripDate", "returnDate", "budget",
                    "travelStyle", "transportMode", "companion",
                )
                if slots.get(k)
            },
            "selected_plan": {
                "mode": first.get("mode"),
                "vehicle_no": first.get("vehicle_no", ""),
                "depart": first.get("depart"),
                "price": order.price,
                "order_no": order.order_no,
            },
            "decision_reason": [],
            "outcome": {"booking_success": order.status == OrderStatus.PAID.value, "rating": None},
            "trace_refs": [],
        }

    async def _build_summary_md(self, db, user_id, order, legs) -> str:
        try:
            agent_set = self.agent_factory.get(f"summary_{user_id}")
            return await agent_set.summary.call(
                user_input="订单支付完成",
                order_data=str({
                    "order_no": order.order_no,
                    "type": order.type,
                    "status": order.status,
                    "price": order.price,
                    "legs": legs,
                }),
            )
        except Exception:  # noqa: BLE001
            seg = " → ".join(f"{l.get('from_city')}{l.get('depart')}" for l in legs) if legs else order.order_no
            return (
                f"## 行程摘要\n"
                f"- 订单：{order.order_no}（{order.status}，¥{order.price:.0f}）\n"
                f"- 行程：{seg}\n"
                f"- 决策：用户确认方案后完成 Mock 下单支付\n"
                f"- 结果：已出票"
            )

    async def _save_state(self, db, state: SessionState):
        await session_crud.save_session_state(db, state)

    async def _record_feedback(
        self, db: AsyncSession, state: SessionState, action: str,
        plan_id: Optional[str] = None, reason: str = "", trace_id: Optional[str] = None,
    ):
        """把对话中的方案选择/调整落成反馈（推荐反馈表），供评估的用户反馈维度使用。"""
        try:
            rating = 5 if action.upper() in ("LIKE", "ADOPT", "ACCEPT") else (2 if action.upper() in ("DISLIKE", "REJECT") else None)
            fb = FeedbackRow(
                user_id=state.userId,
                session_id=state.sessionId,
                plan_id=plan_id,
                trace_id=trace_id,
                action=action,
                rating=rating,
                reason=(reason or "")[:512],
            )
            db.add(fb)
            await db.commit()
            log.info("方案反馈已记录: user=%s action=%s plan=%s", state.userId, action, plan_id)
        except Exception as e:  # noqa: BLE001
            log.warning("方案反馈记录失败: %s", e)

    def _finish(self, db, state: SessionState, ctx: TraceContext, msg: OutboundMessage, clarify: bool = False):
        """追加助手消息到对话流（不阻塞响应）。"""
        intent = state.currentIntent.value if state.currentIntent else (Intent.CLARIFY_NEEDED.value if clarify else None)

        async def _persist():
            async with async_session_maker() as s:
                await session_crud.append_message(s, state.sessionId, "assistant", msg.text, intent, ctx.trace_id)

        asyncio.create_task(_persist())
        return msg

    @staticmethod
    def _contains_any(text: str, keywords: List[str]) -> bool:
        return any(k in text for k in keywords)

    @staticmethod
    async def _today_plus(days: int) -> str:
        from datetime import datetime, timedelta
        return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    @staticmethod
    def _fallback_intent(text: str) -> TravelIntentResult:
        """关键词规则兜底（意图识别异常时接管，低置信度标记）。"""
        rules = [
            (["改签", "改到", "改期", "改一下"], Intent.ORDER_CHANGE),
            (["查订单", "我的票", "订单", "订的票"], Intent.ORDER_QUERY),
            (["退票", "退了吧", "退掉", "退款", "取消订单"], Intent.ORDER_CANCEL),
            (["下单", "购买", "买票", "订票", "就订", "订第一个", "订这个", "订方案"], Intent.PLAN_BOOK),
            (["降价", "价格提醒", "价格监控"], Intent.PRICE_MONITOR),
            (["清单", "准备什么", "出行准备"], Intent.CHECKLIST_EXPORT),
            (["换一批", "换一个", "太贵", "改坐", "换方案", "不要"], Intent.PLAN_ADJUST),
            (["去", "规划", "怎么走", "出行", "机票", "高铁", "火车"], Intent.PLAN_RECOMMENDATION),
        ]
        for kws, intent in rules:
            if any(k in text for k in kws):
                return TravelIntentResult(
                    intent=intent.value,
                    slots=TravelOrchestratorService._fallback_slots(text),
                    confidence=0.3,
                )
        return TravelIntentResult(
            intent=Intent.CLARIFY_NEEDED.value,
            slots=TravelOrchestratorService._fallback_slots(text),
            confidence=0.3,
        )

    @staticmethod
    def _fallback_slots(text: str) -> TravelSlotBundle:
        """规则槽位抽取（LLM 不可用时的兜底）：城市/日期/预算/风格/交通/同行人。"""
        import re as _re
        from app.services.collector.base import KNOWN_CITIES

        slots = TravelSlotBundle()

        # 起点/终点：优先 "从X(去|到)Y" / "X(去|到|前往|飞往)Y"
        city_pat = "[" + "".join(KNOWN_CITIES) + "]"
        m = _re.search(rf"从({city_pat}{{2,8}})(?:去|到|前往|飞往|至)({city_pat}{{2,8}})", text)
        if not m:
            m = _re.search(rf"({city_pat}{{2,8}})(?:去|到|前往|飞往|至)({city_pat}{{2,8}})", text)
        if m:
            slots.origin.append(m.group(1))
            slots.destination.append(m.group(2))
        for city in KNOWN_CITIES:
            if city in text and city not in slots.destination and city not in slots.origin:
                slots.destination.append(city)

        # 返程/游玩天数（兜底规则）
        if _re.search(r"不用算返程|没有返程|不需要返程|单程|不回程|不用返程|无返程|只去不回", text):
            slots.returnDate.append("不需要")
        else:
            m_ret = _re.search(r"(?:返程|回程|回来|玩|待|停留)\s*(\d{1,2})\s*天", text)
            if m_ret:
                slots.returnDate.append(f"{m_ret.group(1)}天")
            else:
                m_ret2 = _re.search(r"返程[是为：: ]*([0-9.年月日\-~到至]+)", text)
                if m_ret2:
                    slots.returnDate.append(m_ret2.group(1).strip())

        budget_map = {
            "不限预算": "不限预算", "不限": "不限预算", "无预算要求": "不限预算",
            "经济": "经济型", "舒适": "舒适型", "高端": "高端型", "豪华": "高端型", "穷游": "经济型"
        }
        for kw, val in budget_map.items():
            if kw in text and val not in slots.budget:
                slots.budget.append(val)

        style_map = {"紧凑": "紧凑", "休闲": "休闲", "美食": "美食", "购物": "购物", "亲子": "亲子", "商务": "商务"}
        for kw, val in style_map.items():
            if kw in text and val not in slots.travelStyle:
                slots.travelStyle.append(val)

        transport_map = {
            "机票优先": "飞机", "机票": "飞机", "飞机": "飞机", "航班": "飞机",
            "高铁优先": "高铁", "高铁": "高铁", "动车": "高铁",
            "普通火车": "火车", "火车优先": "火车", "火车": "火车",
            "大巴": "大巴"
        }
        for kw, val in transport_map.items():
            if kw in text and val not in slots.transportMode:
                slots.transportMode.append(val)

        companion_map = {"独自": "独自", "一个人": "独自", "情侣": "情侣", "亲子": "亲子", "带小孩": "亲子", "商务": "商务"}
        for kw, val in companion_map.items():
            if kw in text and val not in slots.companion:
                slots.companion.append(val)

        # 乘车人员抽取（支持如“我选择：张三(本人)”或“本人/我一个人”等兜底模式，且严格排除偏好选项关键词）
        pref_keywords = ("机票", "飞机", "航班", "高铁", "动车", "火车", "大巴", "经济", "舒适", "高端", "预算", "不限", "商务", "休闲", "紧凑", "美食", "亲子", "无特别偏好")
        choice_match = _re.search(r"我选择[：:]\s*([^\n]+)", text)
        if choice_match:
            raw_c = choice_match.group(1).strip()
            for item in _re.split(r"[,，、\s]+", raw_c):
                name_clean = _re.sub(r"\(.*?\)|（.*?）", "", item).strip()
                if name_clean and not any(pk in name_clean for pk in pref_keywords) and name_clean not in slots.passengers:
                    slots.passengers.append(name_clean)
        else:
            passenger_map = {"本人": "本人", "只有我": "本人", "我一个人": "本人", "就我": "本人"}
            for kw, val in passenger_map.items():
                if kw in text and val not in slots.passengers:
                    slots.passengers.append(val)

        date_pattern = (
            r"(今天|明天|后天|大后天|下下周[一二三四五六日天]?|下周[一二三四五六日天]?|"
            r"本周[一二三四五六日天]?|这周[一二三四五六日天]?|星期[一二三四五六日天]|周[一二三四五六日天]|"
            r"\d{1,2}月\d{1,2}日?|\d{1,2}[./-]\d{1,2}(?:[到至~\-—]\d{1,2}[./-]\d{1,2})?|"
            r"国庆|春节|五一|元旦)"
        )
        slots.tripDate = list(dict.fromkeys(re.findall(date_pattern, text)))
        return slots

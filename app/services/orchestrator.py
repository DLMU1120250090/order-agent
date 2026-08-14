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
from app.services.mock_supplier import mock_supplier
from app.services.planner import ItineraryPlanner
from app.services.push import PushService
from app.services.risk_guard import RiskGuardService
from app.services.task import TaskService
from app.services.trace import TraceContext, TraceScope, active_trace_ctx, traced_agent_call
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
        # ① 支付确认快捷路径（BOOKING 阶段回复"付好了"）
        if state.orderNo and state.phase == SessionPhase.BOOKING and self._contains_any(text, PAYMENT_CONFIRM_KEYWORDS):
            return await self._confirm_payment(db, user_id, text, state, ctx)

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
        return await self._route(db, user_id, text, state, ctx, agent_set, revised, target)

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
    ) -> OutboundMessage:
        if intent in (Intent.PLAN_RECOMMENDATION, Intent.CLARIFY_NEEDED):
            return await self._handle_plan(db, user_id, text, state, ctx, agent_set, revised, adjust=False)
        if intent == Intent.PLAN_ADJUST:
            return await self._handle_plan(db, user_id, text, state, ctx, agent_set, revised, adjust=True)
        if intent == Intent.PLAN_BOOK:
            return await self._handle_book(db, user_id, text, state, ctx)
        if intent == Intent.ORDER_QUERY:
            if self._is_trip_query(text):
                return await self._handle_trip_query(db, user_id, state, ctx)
            return await self._handle_order_query(db, user_id, state, ctx)
        if intent == Intent.ORDER_CHANGE:
            return await self._handle_order_change(db, user_id, text, state, ctx, revised)
        if intent == Intent.ORDER_CANCEL:
            return await self._handle_order_cancel(db, user_id, state, ctx)
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
    ) -> OutboundMessage:
        # 调整方案即对上一批推荐的负向反馈（非 Web 通道也能通过对话产生反馈）
        if adjust:
            rejected = state.selectedPlanId or (state.currentBatch[-1] if state.currentBatch else None)
            action = "DISLIKE" if any(k in text for k in ("太贵", "不好", "不喜欢", "不满意")) else "SWITCH"
            await self._record_feedback(db, state, action, plan_id=rejected, reason=f"用户调整方案: {text[:80]}")

        merged = self._merge_slots(state.slots, revised.slots)
        merged, fuzzy = await self._resolve_dates(db, merged)
        ctx.record_event("SLOTS_MERGED", "SLOT", {"stateSlots": state.slots.model_dump(), "intentSlots": revised.slots.model_dump()}, merged.model_dump())

        missing = self.clarify_rules.missing_slots(merged, fuzzy_date=fuzzy)
        ctx.record_event("CLARIFY_DECISION", "CLARIFY", merged.model_dump(), {"action": "ASK" if missing else "READY", "missingSlots": missing})

        if missing:
            # 日期先后校验（存在范围时）
            ok, reason = self.date_consistency.check(merged.tripDate, [])
            if not ok and not fuzzy:
                missing.append("tripDate")
                ctx.record_event("DATE_CONFLICT_CHECKED", "CLARIFY", merged.tripDate, {"ok": False, "reason": reason})
            question = await self._ask_clarify(db, state, ctx, agent_set, text, merged, missing)
            clarify_state = state.model_copy(update={
                "phase": SessionPhase.CLARIFY,
                "currentIntent": Intent.CLARIFY_NEEDED,
                "slots": merged,
            })
            await self._save_state(db, clarify_state)
            msg = OutboundMessage(
                channel=state.channel.value,
                kind="CLARIFY",
                text=question,
                blocks=[],
            )
            ctx.record_event("RESPONSE_READY", "CLARIFY", {"missing": missing}, msg.model_dump())
            return self._finish(db, clarify_state, ctx, msg, clarify=True)

        # 记忆注入（L1 画像 + L2 摘要）
        profile = await self.memory.get_profile(db, user_id)
        ctx.record_event("MEMORY_INJECTED", "MEMORY", {"userId": user_id}, {"profile": profile.model_dump() if profile else None})

        decision = await self.planner.plan(db, user_id, merged, profile)
        ctx.record_event("PLAN_RANKED", "PLAN", merged.model_dump(), {"optionCount": len(decision.options), "options": [o.plan_id for o in decision.options]})

        if not decision.options:
            reply = "没有满足约束的出行方案，请调整日期、目的地或预算。"
            msg = OutboundMessage(channel=state.channel.value, text=reply)
            return self._finish(db, state, ctx, msg)

        blocks = [self._plan_card(o) for o in decision.options]
        top_plans = [{"planId": o.plan_id, "legs": [l.model_dump() for l in o.legs], "totalPrice": o.total_price, "totalDurationH": o.total_duration_h, "score": o.score} for o in decision.options]
        speech = await self._recommend_speech(db, state, ctx, agent_set, text, merged, top_plans, decision.reason)

        plan_ids = [o.plan_id for o in decision.options]
        new_state = state.model_copy(update={
            "phase": SessionPhase.PLAN,
            "currentIntent": Intent.PLAN_RECOMMENDATION,
            "slots": merged,
            "lastRecommendations": list(state.lastRecommendations) + plan_ids,
            "currentBatch": plan_ids,
            "selectedPlanId": decision.recommended.plan_id if decision.recommended else (plan_ids[0] if plan_ids else None),
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

        # 用户以消息方式选择方案 → 记录正向反馈（LIKE），供评估系统使用
        await self._record_feedback(db, state, "LIKE", plan_id=str(selected), reason=f"用户选择方案下单: {text[:80]}")

        plan_row = await trip_crud.get_plan(db, int(selected))
        if not plan_row:
            msg = OutboundMessage(channel=state.channel.value, text="所选方案已失效，请重新规划。")
            return self._finish(db, state, ctx, msg)
        plan = PlanOption(**plan_row.plan_json)

        profile = await self.memory.get_profile(db, user_id)
        passengers = profile.passengers if profile and profile.passengers else None
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
        })
        await self._save_state(db, new_state)

        # 后台执行下单（Playwright Mock 收银台：确认订单 → 截图二维码 → WAITING_USER）
        asyncio.create_task(self.task_service.run(task_id, lambda db: self.booking.execute_booking(db, task_id, order)))
        # 三层支付检测监控（第1层页面变化 / 第2层订单轮询；第3层用户确认走快捷路径）
        asyncio.create_task(self._payment_monitor(user_id, order, new_state))
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="TASK_PROGRESS",
            text=f"已开始下单（任务 {task_id}），请稍候…支付完成后回复『付好了』。",
            task_progress={"taskId": task_id, "status": "RUNNING", "progress": 10},
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
        new_state = state.model_copy(update={"phase": SessionPhase.ORDER, "currentIntent": Intent.ORDER_QUERY})
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
                        target = cur or order
                        updated = await self.booking.confirm_payment(
                            db, target.task_id, target, push_success=True,
                        )
                        await self._finalize_payment(db, user_id, updated, state)
                        await browser_order.close(order.order_no)
                        return
            except Exception as e:  # noqa: BLE001
                log.warning("支付监控异常 order=%s: %s", order.order_no, e)
            # 自适应轮询：前 2 分钟每 30 秒，之后每 90 秒（1~2 分钟），总超时 15 分钟
            elapsed = _time.time() - start
            interval = (
                _settings.TRAVEL_PAYMENT_POLL_SECONDS_FAST
                if elapsed < 120
                else _settings.TRAVEL_PAYMENT_POLL_SECONDS_SLOW
            )
            await asyncio.sleep(interval)
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
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="CARD",
            text="\n".join(lines),
            blocks=blocks,
        )
        ctx.record_event("ORDER_QUERIED", "ORDER", {"userId": user_id}, {"count": len(orders)})
        return self._finish(db, state, ctx, msg)

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
            return self._finish(db, state, ctx, msg)

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
        order = await self._latest_active_order(db, user_id)
        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="没有可改签的订单。")
            return self._finish(db, state, ctx, msg)

        merged = self._merge_slots(state.slots, revised.slots)
        merged, fuzzy = await self._resolve_dates(db, merged)
        target_date = (merged.tripDate or [None])[0]
        if not target_date:
            msg = OutboundMessage(channel=state.channel.value, text="改到哪一天？告诉我具体日期，我来对比方案。")
            new_state = state.model_copy(update={"phase": SessionPhase.ORDER, "slots": merged, "orderNo": order.order_no})
            await self._save_state(db, new_state)
            return self._finish(db, new_state, ctx, msg)

        profile = await self.memory.get_profile(db, user_id)
        request = ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.USER_CHANGE, target_date=target_date)
        decision = await self.change_decision.decide(db, request, order, profile)
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
        order = await self._latest_active_order(db, user_id)
        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="没有可改签的订单。")
            return self._finish(db, state, ctx, msg)
        target_date = (state.slots.tripDate or [None])[0] or (await self._today_plus(2))
        profile = await self.memory.get_profile(db, user_id)
        decision = await self.change_decision.decide(
            db,
            ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.USER_CHANGE, target_date=target_date),
            order,
            profile,
        )
        task_id = await self.task_service.create(
            db, user_id, TaskType.change.value,
            {"order_no": order.order_no, "target_date": target_date},
            channel=state.channel.value, session_id=state.sessionId, order_id=order.id,
        )
        asyncio.create_task(self.task_service.run(task_id, lambda db: self.booking.execute_change(db, task_id, order, decision)))
        ctx.record_event("BOOKING_STARTED", "CHANGE", {"orderNo": order.order_no}, {"taskId": task_id, "decision": decision.reason})
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="TASK_PROGRESS",
            text=f"改签任务已启动（{task_id}）：{decision.reason}",
            task_progress={"taskId": task_id, "status": "RUNNING", "progress": 10},
        )
        return self._finish(db, state, ctx, msg)

    async def _handle_order_cancel(self, db: AsyncSession, user_id: int, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        order = await self._latest_active_order(db, user_id)
        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="没有可退票的订单。")
            return self._finish(db, state, ctx, msg)
        profile = await self.memory.get_profile(db, user_id)
        decision = await self.change_decision.decide(
            db,
            ChangeRequest(order_no=order.order_no, scenario=ChangeScenario.USER_CANCEL),
            order,
            profile,
        )
        ctx.record_event("ORDER_CHANGE_DECISION", "DECISION", {"scenario": "USER_CANCEL"}, decision.model_dump())
        new_state = state.model_copy(update={
            "phase": SessionPhase.ORDER,
            "currentIntent": Intent.ORDER_CANCEL,
            "orderNo": order.order_no,
        })
        await self._save_state(db, new_state)
        msg = self._decision_card(state.channel.value, decision, prefix="🗑 退票方案")
        return self._finish(db, new_state, ctx, msg)

    async def _confirm_cancel(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        order = await self._latest_active_order(db, user_id)
        if not order:
            msg = OutboundMessage(channel=state.channel.value, text="没有可退票的订单。")
            return self._finish(db, state, ctx, msg)
        task_id = await self.task_service.create(
            db, user_id, TaskType.refund.value,
            {"order_no": order.order_no}, channel=state.channel.value, session_id=state.sessionId, order_id=order.id,
        )
        asyncio.create_task(self.task_service.run(task_id, lambda db: self.booking.execute_refund(db, task_id, order)))
        ctx.record_event("BOOKING_STARTED", "REFUND", {"orderNo": order.order_no}, {"taskId": task_id})
        msg = OutboundMessage(
            channel=state.channel.value,
            kind="TASK_PROGRESS",
            text=f"退票任务已启动（{task_id}），正在处理…",
            task_progress={"taskId": task_id, "status": "RUNNING", "progress": 10},
        )
        return self._finish(db, state, ctx, msg)

    async def _handle_price_monitor(self, db: AsyncSession, user_id: int, text: str, state: SessionState, ctx: TraceContext) -> OutboundMessage:
        profile = await self.memory.get_profile(db, user_id)
        prefs = dict(profile.preferences) if profile and profile.preferences else {}
        turning_off = "关" in text or "停" in text or "不要" in text
        prefs["price_monitor"] = False if turning_off else True
        await self.memory.update_profile(db, user_id, preferences=prefs)
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
        md = await self.checklist.generate(db, legs, destination, weather)
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

    async def _recommend_speech(self, db, state, ctx, agent_set, user_input, slots, top_plans, fallback_reason) -> str:
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

    def _plan_card(self, o: PlanOption) -> dict:
        return {
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
        return OutboundMessage(
            channel=channel,
            kind="CARD",
            text="\n".join(lines),
            blocks=[o.model_dump() for o in decision.options],
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
        )

    async def _latest_active_order(self, db: AsyncSession, user_id: int) -> Optional[TravelOrderRow]:
        orders = await order_crud.list_orders(db, user_id)
        active = [o for o in orders if o.status in (
            OrderStatus.PAID.value, OrderStatus.BOOKING.value,
            OrderStatus.CONFIRMED.value, OrderStatus.CHANGING.value, OrderStatus.CHANGED.value,
        )]
        return active[0] if active else None

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
                await self.memory.add_trip_summary(db, user_id, order.trip_id, md)
        except Exception as e:  # noqa: BLE001
            log.warning("L2 摘要写入失败: %s", e)

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

    async def _record_feedback(self, db: AsyncSession, state: SessionState, action: str, plan_id: Optional[str] = None, reason: str = ""):
        """把对话中的方案选择/调整落成反馈（推荐反馈表），供评估的用户反馈维度使用。"""
        try:
            rating = 5 if action.upper() in ("LIKE", "ADOPT", "ACCEPT") else (2 if action.upper() in ("DISLIKE", "REJECT") else None)
            fb = FeedbackRow(
                user_id=state.userId,
                session_id=state.sessionId,
                plan_id=plan_id,
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

        budget_map = {"经济": "经济型", "舒适": "舒适型", "高端": "高端型", "豪华": "高端型", "穷游": "经济型"}
        for kw, val in budget_map.items():
            if kw in text and val not in slots.budget:
                slots.budget.append(val)

        style_map = {"紧凑": "紧凑", "休闲": "休闲", "美食": "美食", "购物": "购物", "亲子": "亲子", "商务": "商务"}
        for kw, val in style_map.items():
            if kw in text and val not in slots.travelStyle:
                slots.travelStyle.append(val)

        transport_map = {"飞机": "飞机", "航班": "飞机", "高铁": "高铁", "动车": "高铁", "火车": "火车", "大巴": "大巴"}
        for kw, val in transport_map.items():
            if kw in text and val not in slots.transportMode:
                slots.transportMode.append(val)

        companion_map = {"独自": "独自", "一个人": "独自", "情侣": "情侣", "亲子": "亲子", "带小孩": "亲子", "商务": "商务"}
        for kw, val in companion_map.items():
            if kw in text and val not in slots.companion:
                slots.companion.append(val)

        date_pattern = (
            r"(今天|明天|后天|大后天|下下周[一二三四五六日天]?|下周[一二三四五六日天]?|"
            r"本周[一二三四五六日天]?|这周[一二三四五六日天]?|星期[一二三四五六日天]|周[一二三四五六日天]|"
            r"\d{1,2}月\d{1,2}日?|\d{1,2}[./-]\d{1,2}(?:[到至~\-—]\d{1,2}[./-]\d{1,2})?|"
            r"国庆|春节|五一|元旦)"
        )
        slots.tripDate = list(dict.fromkeys(re.findall(date_pattern, text)))
        return slots

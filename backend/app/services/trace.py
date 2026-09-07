import time
import json
import uuid
import contextvars
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import RequestTraceRow
from app.services.trace_schema import EventType, TraceEventSchema

log = logging.getLogger("diet.trace")

# 核心：使用 contextvars.ContextVar 维护当前异步协程链路下的 Trace 上下文
# 确保在单线程多协程并发状态下，各用户请求的日志完全隔离，绝不串话
active_trace_ctx = contextvars.ContextVar("active_trace_ctx", default=None)


class TraceEvent:
    """单条 Trace 轨迹事件明细（Commit 5：字段由 TraceEventSchema 统一约束）。"""

    def __init__(
        self,
        step_order: int,
        event_type: str,
        phase: str,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        input_payload: Optional[str] = None,
        output_payload: Optional[str] = None,
        latency_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        error_recoverable: Optional[bool] = None,
        retry_no: Optional[int] = None,
        decision: Optional[Dict[str, Any]] = None,
        state_before: Any = None,
        state_after: Any = None,
        memory_sources: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
        memory_version: Optional[str] = None,
        inferred_fields: Optional[Dict[str, Any]] = None,
    ):
        self.step_order = step_order
        self.event_type = event_type
        self.phase = phase
        self.agent_name = agent_name
        self.model_name = model_name
        self.tool_name = tool_name
        self.input_payload = input_payload
        self.output_payload = output_payload
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.total_tokens = total_tokens
        self.error_message = error_message
        self.error_type = error_type
        self.error_recoverable = error_recoverable
        self.retry_no = retry_no
        self.decision = decision
        self.state_before = state_before
        self.state_after = state_after
        self.memory_sources = memory_sources
        self.memory_ids = memory_ids
        self.memory_version = memory_version
        self.inferred_fields = inferred_fields
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        """经 TraceEventSchema 校验并序列化（排除 None，老解析 get 缺失键返回 None 兼容）。"""
        try:
            return TraceEventSchema(
                stepOrder=self.step_order,
                eventType=self.event_type,
                phase=self.phase,
                agentName=self.agent_name,
                modelName=self.model_name,
                toolName=self.tool_name,
                inputPayload=self.input_payload,
                outputPayload=self.output_payload,
                latencyMs=self.latency_ms,
                inputTokens=self.input_tokens,
                outputTokens=self.output_tokens,
                totalTokens=self.total_tokens,
                errorMessage=self.error_message,
                errorType=self.error_type,
                errorRecoverable=self.error_recoverable,
                retryNo=self.retry_no,
                decision=self.decision,
                stateBefore=self.state_before,
                stateAfter=self.state_after,
                memorySources=self.memory_sources,
                memoryIds=self.memory_ids,
                memoryVersion=self.memory_version,
                inferredFields=self.inferred_fields,
                createdAt=self.created_at,
            ).model_dump(exclude_none=True)
        except Exception as e:  # noqa: BLE001
            log.warning("TraceEvent schema 校验失败，回退旧结构: %s", e)
            return {
                "stepOrder": self.step_order,
                "eventType": self.event_type,
                "phase": self.phase,
                "agentName": self.agent_name,
                "modelName": self.model_name,
                "inputPayload": self.input_payload,
                "outputPayload": self.output_payload,
                "latencyMs": self.latency_ms,
                "inputTokens": self.input_tokens,
                "outputTokens": self.output_tokens,
                "totalTokens": self.total_tokens,
                "errorMessage": self.error_message,
                "createdAt": self.created_at,
            }


class TraceContext:
    """单个请求生命周期内的 Trace 上下文管理器。"""

    def __init__(self, trace_id: str, session_id: str, user_id: int):
        self.trace_id = trace_id
        self.session_id = session_id
        self.user_id = user_id
        self.events: List[TraceEvent] = []
        self.status = "SUCCESS"
        self.error_message: Optional[str] = None
        self.start_time_ns = time.time_ns()
        self.step_counter = 0
        self.task_id: Optional[str] = None

    def set_task_id(self, task_id: Optional[str]):
        """任务创建后回填 task_id（scheduler 先建 scope 再建 task 的场景）。"""
        self.task_id = task_id

    def next_step(self) -> int:
        """步骤序号累加器"""
        self.step_counter += 1
        return self.step_counter

    def record_event(
        self,
        event_type: str,
        phase: str,
        input_payload: Any,
        output_payload: Any,
        latency_ms: Optional[int] = None,
        tool_name: Optional[str] = None,
        state_before: Any = None,
        state_after: Any = None,
        decision: Optional[dict] = None,
        memory_sources: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
        memory_version: Optional[str] = None,
        inferred_fields: Optional[dict] = None,
        error_type: Optional[str] = None,
        error_recoverable: Optional[bool] = None,
        retry_no: Optional[int] = None,
    ):
        """记录普通业务流事件（Commit 5：支持 schema 化扩展字段）。"""
        self.record(
            event_type=event_type,
            phase=phase,
            input_payload=input_payload,
            output_payload=output_payload,
            latency_ms=latency_ms,
            tool_name=tool_name,
            state_before=state_before,
            state_after=state_after,
            decision=decision,
            memory_sources=memory_sources,
            memory_ids=memory_ids,
            memory_version=memory_version,
            inferred_fields=inferred_fields,
            error_type=error_type,
            error_recoverable=error_recoverable,
            retry_no=retry_no,
        )

    def record_error(self, event_type: str, phase: str, input_payload: Any, error: Exception):
        """记录异常崩溃事件，将整体请求标为失败状态"""
        self.status = "FAILED"
        self.error_message = f"{error.__class__.__name__}: {str(error)}"
        self.record(
            event_type=event_type,
            phase=phase,
            input_payload=input_payload,
            output_payload=None,
            error_message=self.error_message,
            error_type=error.__class__.__name__,
            error_recoverable=False,
        )

    def record_agent_call(
        self,
        agent_name: str,
        model_name: str,
        input_text: str,
        output_text: Optional[str],
        latency_ms: int,
        token_usage: Optional[dict] = None,
        error: Optional[Exception] = None,
    ):
        """特定于大模型/Agent 调用的日志记录，捕获 Token 用量计入指标。"""
        input_tokens = None
        output_tokens = None
        total_tokens = None

        if token_usage:
            input_tokens = token_usage.get("prompt_tokens")
            output_tokens = token_usage.get("completion_tokens")
            total_tokens = token_usage.get("total_tokens")

        error_msg = f"{error.__class__.__name__}: {str(error)}" if error else None

        self.record(
            event_type=EventType.AGENT_CALL,
            phase="AGENT",
            agent_name=agent_name,
            model_name=model_name,
            input_payload=input_text,
            output_payload=output_text,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_message=error_msg,
            error_type=error.__class__.__name__ if error else None,
            error_recoverable=False if error else None,
        )

    def record(
        self,
        event_type: str,
        phase: str,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        input_payload: Any = None,
        output_payload: Any = None,
        latency_ms: Optional[int] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        error_recoverable: Optional[bool] = None,
        retry_no: Optional[int] = None,
        decision: Optional[dict] = None,
        state_before: Any = None,
        state_after: Any = None,
        memory_sources: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
        memory_version: Optional[str] = None,
        inferred_fields: Optional[dict] = None,
    ):
        """通用事件落盘序列化（最大 20000 字符截断保护，防 DB 溢出崩溃）。"""

        def to_str(p: Any) -> Optional[str]:
            if p is None:
                return None
            if isinstance(p, str):
                return p[:20000] + "...[truncated]" if len(p) > 20000 else p
            try:
                val = json.dumps(p, ensure_ascii=False)
                return val[:20000] + "...[truncated]" if len(val) > 20000 else val
            except Exception:
                return str(p)[:20000]

        event = TraceEvent(
            step_order=self.next_step(),
            event_type=event_type,
            phase=phase,
            agent_name=agent_name,
            model_name=model_name,
            tool_name=tool_name,
            input_payload=to_str(input_payload),
            output_payload=to_str(output_payload),
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            error_message=to_str(error_message),
            error_type=error_type,
            error_recoverable=error_recoverable,
            retry_no=retry_no,
            decision=decision,
            state_before=state_before,
            state_after=state_after,
            memory_sources=memory_sources,
            memory_ids=memory_ids,
            memory_version=memory_version,
            inferred_fields=inferred_fields,
        )
        self.events.append(event)


class TraceScope:
    """
    异步 Trace 范围上下文管理器（ThreadLocal 的 asyncio 版本）。

    使用示例：
    async with TraceScope(db, sessionId, userId) as ctx:
        ctx.record_event(...)
        # 退出 async with 时自动计算耗时并完成数据库保存
    """

    def __init__(
        self,
        db: AsyncSession,
        session_id: Optional[str],
        user_id: Optional[int],
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        self.db = db
        # Commit 4：后台任务/调度器无会话时允许空值；保存时用空串/0 占位（表列非空）
        self.session_id = session_id or ""
        self.user_id = user_id or 0
        self.run_id = run_id
        self.task_id = task_id
        self.trace_id = f"trace_{uuid.uuid4().hex}"
        self.context = TraceContext(self.trace_id, self.session_id, self.user_id)
        if task_id:
            self.context.set_task_id(task_id)
        self.token = None

    def set_task_id(self, task_id: Optional[str]):
        """任务创建后回填 task_id（scheduler 先建 scope 再建 task 的场景）。"""
        self.task_id = task_id
        self.context.set_task_id(task_id)

    async def __aenter__(self) -> TraceContext:
        # 将当前请求的 TraceContext 塞入协程变量中，并保留还原 Token
        self.token = active_trace_ctx.set(self.context)
        return self.context

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # 还原协程上下文变量状态
        active_trace_ctx.reset(self.token)

        # 计算请求端到端总时间
        end_time_ns = time.time_ns()
        duration_ms = (end_time_ns - self.context.start_time_ns) // 1_000_000

        if exc_val is not None:
            self.context.record_error(EventType.REQUEST_FAILED, "HTTP", {}, exc_val)

        # Commit 5：事件级注入 runId/taskId（老事件无这些字段，不覆盖既有值）
        effective_task_id = self.context.task_id or self.task_id
        events = [e.to_dict() for e in self.context.events]
        for ev in events:
            if self.run_id and "runId" not in ev:
                ev["runId"] = self.run_id
            if effective_task_id and "taskId" not in ev:
                ev["taskId"] = effective_task_id

        trace_json = {
            "traceId": self.trace_id,
            "sessionId": self.session_id,
            "userId": self.user_id,
            "runId": self.run_id,
            "taskId": effective_task_id,
            "status": self.context.status,
            "durationMs": duration_ms,
            "events": events,
        }

        # 组装 RequestTraceRow 实体写入数据库
        db_trace = RequestTraceRow(
            trace_id=self.trace_id,
            session_id=self.session_id,
            user_id=self.user_id,
            status=self.context.status,
            event_count=len(self.context.events),
            duration_ms=duration_ms,
            error_message=self.context.error_message,
            run_id=self.run_id,
            task_id=effective_task_id,
            trace_json=trace_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        try:
            self.db.add(db_trace)
            await self.db.commit()
        except Exception as e:
            log.warning(f"无法保存 Trace 链路日志，traceId={self.trace_id}。异常为: {str(e)}")


async def traced_agent_call(agent_name: str, model_name: str, chain: Any, inputs: dict, user_input_text: str) -> Any:
    """无侵入式包装函数：运行任意 LangChain 链，并自动收集 Trace 信息。"""
    ctx: Optional[TraceContext] = active_trace_ctx.get()

    # 若传入的是自定义 Agent 包装类对象，自动解包出底层的 LangChain chain 实例
    if hasattr(chain, "chain"):
        chain = chain.chain

    start_time_ns = time.time_ns()
    try:
        # 判断是异步 chain.ainvoke 还是同步 invoke
        if hasattr(chain, "ainvoke"):
            response = await chain.ainvoke(inputs)
        else:
            response = chain.invoke(inputs)

        latency_ms = (time.time_ns() - start_time_ns) // 1_000_000

        token_usage = None
        output_text = None

        # 尝试提取 LangChain 各种标准对象携带的 Token 使用量元数据和内容字段
        if hasattr(response, "response_metadata"):
            token_usage = response.response_metadata.get("token_usage")
        if hasattr(response, "content"):
            output_text = response.content
        else:
            output_text = str(response)

        if ctx:
            ctx.record_agent_call(
                agent_name=agent_name,
                model_name=model_name,
                input_text=user_input_text,
                output_text=output_text,
                latency_ms=latency_ms,
                token_usage=token_usage,
            )
        return response
    except Exception as e:
        latency_ms = (time.time_ns() - start_time_ns) // 1_000_000
        if ctx:
            ctx.record_agent_call(
                agent_name=agent_name,
                model_name=model_name,
                input_text=user_input_text,
                output_text=None,
                latency_ms=latency_ms,
                error=e,
            )
        raise e

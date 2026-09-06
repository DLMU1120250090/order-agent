"""Trace 事件 Schema（Commit 5：schema 先行）。

- TraceEventSchema：写入与解析共用的事件字段定义（存储为驼峰 key，兼容既有 trace_json）；
- EventType：事件类型常量集中表，写方与解析方都引用它，消除字符串漂移。
"""
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventType:
    """Trace 事件类型常量（集中登记，新增事件请在此补充）。"""
    REQUEST_RECEIVED = "REQUEST_RECEIVED"
    USER_MESSAGE_RECORDED = "USER_MESSAGE_RECORDED"
    REQUEST_FINISHED = "REQUEST_FINISHED"
    REQUEST_FAILED = "REQUEST_FAILED"

    INTENT_FALLBACK = "INTENT_FALLBACK"
    INTENT_RECOGNIZED = "INTENT_RECOGNIZED"
    INTENT_REVISED = "INTENT_REVISED"
    ROUTE_SELECTED = "ROUTE_SELECTED"
    SLOTS_MERGED = "SLOTS_MERGED"
    CLARIFY_DECISION = "CLARIFY_DECISION"
    DATE_CONFLICT_CHECKED = "DATE_CONFLICT_CHECKED"
    RESPONSE_READY = "RESPONSE_READY"

    MEMORY_INJECTED = "MEMORY_INJECTED"
    MEMORY_RESOLVED = "MEMORY_RESOLVED"
    MEMORY_WRITTEN = "MEMORY_WRITTEN"
    MEMORY_DISTILL_STARTED = "MEMORY_DISTILL_STARTED"
    MEMORY_DISTILL_SUCCEEDED = "MEMORY_DISTILL_SUCCEEDED"
    MEMORY_DISTILL_FAILED = "MEMORY_DISTILL_FAILED"

    PLAN_RANKED = "PLAN_RANKED"
    BOOKING_STARTED = "BOOKING_STARTED"
    PAYMENT_DETECTED = "PAYMENT_DETECTED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    ORDER_STATUS_CHANGED = "ORDER_STATUS_CHANGED"
    ORDER_CHANGE_DECISION = "ORDER_CHANGE_DECISION"
    ORDER_CHANGED = "ORDER_CHANGED"
    ORDER_REFUNDED = "ORDER_REFUNDED"
    ORDER_REGISTERED_MANUAL = "ORDER_REGISTERED_MANUAL"
    PRICE_MONITOR_TOGGLED = "PRICE_MONITOR_TOGGLED"
    PRICE_WATCH_SCANNED = "PRICE_WATCH_SCANNED"
    PRICE_DROP_DETECTED = "PRICE_DROP_DETECTED"
    PRICE_DROP_NOTIFIED = "PRICE_DROP_NOTIFIED"
    CHECKLIST_GENERATED = "CHECKLIST_GENERATED"
    ADJUST_CONTEXT_RESOLVED = "ADJUST_CONTEXT_RESOLVED"
    NUTRITION_GUARD_REWRITTEN = "NUTRITION_GUARD_REWRITTEN"

    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_PROGRESS = "TASK_PROGRESS"
    TASK_WAITING_USER = "TASK_WAITING_USER"
    TASK_SUCCEEDED = "TASK_SUCCEEDED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"

    AGENT_CALL = "AGENT_CALL"


class TraceEventSchema(BaseModel):
    """单条 Trace 事件（驼峰存储，与既有 trace_json 一致；新字段均可选，老事件兼容）。"""
    stepOrder: int = 0
    eventType: str = Field(..., description="事件类型，取值见 EventType")
    phase: str = Field(..., description="业务阶段（HTTP/INTENT/PLAN/ORDER/TASK/MEMORY 等）")
    eventId: str = Field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    parentEventId: Optional[str] = None
    runId: Optional[str] = None
    taskId: Optional[str] = None
    agentName: Optional[str] = None
    modelName: Optional[str] = None
    toolName: Optional[str] = None
    inputPayload: Optional[str] = None
    outputPayload: Optional[str] = None
    latencyMs: Optional[int] = None
    inputTokens: Optional[int] = None
    outputTokens: Optional[int] = None
    totalTokens: Optional[int] = None
    errorMessage: Optional[str] = None
    errorType: Optional[str] = None
    errorRecoverable: Optional[bool] = None
    retryNo: Optional[int] = None
    decision: Optional[Dict[str, Any]] = None
    stateBefore: Optional[Any] = None
    stateAfter: Optional[Any] = None
    memorySources: Optional[List[str]] = None
    memoryIds: Optional[List[str]] = None
    memoryVersion: Optional[str] = None
    inferredFields: Optional[Dict[str, Any]] = None
    createdAt: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

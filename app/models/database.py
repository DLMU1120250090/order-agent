from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy.dialects.mysql import JSON


class SessionRow(SQLModel, table=True):
    """会话状态物理表模型（L0：复用现有 diet_sessions）"""
    __tablename__ = "diet_sessions"

    id: str = Field(primary_key=True, max_length=64)
    user_id: int = Field(index=True)
    phase: str = Field(max_length=64)
    # slots JSON：6 维出行槽位 + _meta（channel/currentIntent/selectedPlanId/orderNo）
    slots: str = Field(sa_column=Column(JSON, nullable=False))
    last_recommendations: str = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SessionMessageRow(SQLModel, table=True):
    """会话对话明细消息物理表模型（L0：复用现有 diet_messages）"""
    __tablename__ = "diet_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(max_length=64, index=True)
    role: str = Field(max_length=32)
    content: str = Field(...)
    intent: Optional[str] = Field(default=None, max_length=64)
    agent_trace_id: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RequestTraceRow(SQLModel, table=True):
    """请求链路日志及标定数据表模型（复用 diet_request_trace）"""
    __tablename__ = "diet_request_trace"

    id: Optional[int] = Field(default=None, primary_key=True)
    trace_id: str = Field(max_length=128, unique=True, index=True)
    session_id: str = Field(max_length=64, index=True)
    user_id: int = Field(index=True)
    status: str = Field(max_length=32, index=True)
    event_count: int = Field(default=0)
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    trace_json: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    expected_intent: Optional[str] = Field(default=None, max_length=64)
    expected_slots: Optional[str] = Field(sa_column=Column(JSON, nullable=True))
    expected_clarify_action: Optional[str] = Field(default=None, max_length=32)
    labeled_by: Optional[int] = None
    labeled_at: Optional[datetime] = None
    label_note: Optional[str] = Field(default=None, max_length=512)


class SlotOptionRow(SQLModel, table=True):
    """槽位选项字典表模型（复用 diet_slot_option 机制，换出行数据）"""
    __tablename__ = "diet_slot_option"

    id: Optional[int] = Field(default=None, primary_key=True)
    slot_name: str = Field(max_length=64, index=True)
    option_value: str = Field(max_length=64)
    sort_order: int = Field(default=0)
    enabled: int = Field(default=1)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FeedbackRow(SQLModel, table=True):
    """方案反馈表（复用 recommend_feedback：LIKE/DISLIKE → L1 偏好微调）"""
    __tablename__ = "recommend_feedback"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    session_id: str = Field(max_length=64)
    item_id: Optional[int] = None
    plan_id: Optional[str] = Field(default=None, max_length=64)
    action: str = Field(max_length=32)
    rating: Optional[int] = None
    reason: Optional[str] = Field(default=None, max_length=512)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TravelTripRow(SQLModel, table=True):
    """行程主表"""
    __tablename__ = "travel_trip"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    status: str = Field(default="PLANNING", max_length=32)
    destination: str = Field(max_length=64)
    start_date: Optional[str] = Field(default=None, max_length=16)
    end_date: Optional[str] = Field(default=None, max_length=16)
    budget: Optional[str] = Field(default=None, max_length=32)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TravelPlanRow(SQLModel, table=True):
    """候选方案表（供换一批/评估）"""
    __tablename__ = "travel_plan"

    id: Optional[int] = Field(default=None, primary_key=True)
    trip_id: Optional[int] = None
    score: Optional[float] = None
    plan_json: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    budget_deviation: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TravelOrderRow(SQLModel, table=True):
    """订单表（C3 定稿状态机）"""
    __tablename__ = "travel_order"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    trip_id: Optional[int] = None
    task_id: Optional[str] = Field(default=None, max_length=64)
    order_no: str = Field(max_length=64, unique=True)
    supplier: str = Field(default="mock", max_length=16)
    type: str = Field(max_length=16)
    status: str = Field(default="DRAFT", max_length=32, index=True)
    idempotency_key: str = Field(max_length=128, unique=True)
    price: float = Field(default=0)
    tax_fee: float = Field(default=0)
    passengers: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    legs: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    refund_rule: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    channel: str = Field(default="web", max_length=16)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TravelTaskRow(SQLModel, table=True):
    """后台长任务 + 定时扫描记录（A3 定稿）"""
    __tablename__ = "travel_task"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(max_length=64, unique=True)
    user_id: int = Field(index=True)
    session_id: Optional[str] = Field(default=None, max_length=64)
    type: str = Field(max_length=32)
    status: str = Field(default="PENDING", max_length=32, index=True)
    params: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    progress: int = Field(default=0)
    result: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    error_message: Optional[str] = Field(default=None, max_length=512)
    retry_count: int = Field(default=0)
    next_run_at: Optional[datetime] = None
    channel: str = Field(default="web", max_length=16)
    order_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserProfileRow(SQLModel, table=True):
    """L1 用户画像（C2 定稿）"""
    __tablename__ = "user_profile"

    user_id: int = Field(primary_key=True)
    home_city: Optional[str] = Field(default=None, max_length=32)
    passengers: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    budget_level: Optional[str] = Field(default=None, max_length=16)
    preferences: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TripSummaryRow(SQLModel, table=True):
    """L2 行程摘要（表 + md 双写）"""
    __tablename__ = "trip_summary"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    trip_id: Optional[int] = None
    summary_md: str = Field(...)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UserChannelBindingRow(SQLModel, table=True):
    """跨通道身份绑定（A2 定稿）"""
    __tablename__ = "user_channel_binding"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    channel: str = Field(max_length=16)
    channel_user_id: str = Field(max_length=128)
    bound_at: datetime = Field(default_factory=datetime.utcnow)


class PoiStationRow(SQLModel, table=True):
    """机场/车站 POI 位置表（C1 定稿）"""
    __tablename__ = "poi_station"

    id: Optional[int] = Field(default=None, primary_key=True)
    city: str = Field(max_length=32)
    name: str = Field(max_length=64)
    kind: str = Field(max_length=16)
    lat: Optional[float] = None
    lng: Optional[float] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TransferTimeCacheRow(SQLModel, table=True):
    """机场↔车站通勤时间缓存（C1 定稿，TTL 30 天）"""
    __tablename__ = "transfer_time_cache"

    id: Optional[int] = Field(default=None, primary_key=True)
    from_key: str = Field(max_length=64)
    to_key: str = Field(max_length=64)
    minutes: int = Field(default=30)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DataCacheRow(SQLModel, table=True):
    """数据 API 结果缓存（C1 定稿）"""
    __tablename__ = "data_cache"

    id: Optional[int] = Field(default=None, primary_key=True)
    cache_key: str = Field(max_length=128, unique=True)
    payload: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=True))
    expire_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)

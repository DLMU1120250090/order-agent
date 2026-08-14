from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from app.models.enums import (
    Intent, ClarifyAction, SessionPhase, Channel, TransportMode, BudgetTier,
    OrderStatus, TaskStatus, TaskType, OrderType, Supplier, ChangeKind, ChangeScenario
)


def _normalize_slot_values(value: Any) -> List[str]:
    """
    容错归一化大模型输出的槽位值。
    兼容 intent.txt 提示词中"字符串或 null"的输出格式：
    - null / 空字符串 -> []
    - "成都" -> ["成都"]
    - "飞机,高铁"（提示词约定逗号分隔多值） -> ["飞机", "高铁"]
    - 已是列表 -> 原样保留并剔除空值
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                item = item.strip()
                if item:
                    result.append(item)
            else:
                result.append(item)
        return result
    return [value] if value else []


class TravelSlotBundle(BaseModel):
    """
    出行槽位结构体（A1 定稿，6 维）。
    - origin 为出发地（可选，缺省用常住地/北京）
    - tripDate 为自由值（不走字典白名单），单元素=单日，双元素=[start,end] 范围
    """
    origin: List[str] = Field(default_factory=list, description="出发地")
    destination: List[str] = Field(default_factory=list, description="目的地")
    tripDate: List[str] = Field(default_factory=list, description="出行日期（自由值，YYYY-MM-DD）")
    returnDate: List[str] = Field(default_factory=list, description="返程日期/游玩天数（自由值；用户明确不需要返程时为 ['不需要']）")
    budget: List[str] = Field(default_factory=list, description="预算档位：经济型/舒适型/高端型")
    travelStyle: List[str] = Field(default_factory=list, description="出行风格：紧凑/休闲/美食/购物/亲子/商务")
    transportMode: List[str] = Field(default_factory=list, description="交通偏好集合：飞机/高铁/火车/大巴")
    companion: List[str] = Field(default_factory=list, description="同行人：独自/情侣/亲子/商务")

    @field_validator("origin", "destination", "tripDate", "returnDate", "budget", "travelStyle", "transportMode", "companion", mode="before")
    @classmethod
    def _coerce_slot_value(cls, v):
        return _normalize_slot_values(v)

    def model_dump(self, *args, **kwargs):
        """保持与现有 Trace/序列化代码兼容的驼峰输出"""
        return super().model_dump(*args, **kwargs)


class TravelIntentResult(BaseModel):
    """意图分类与槽位提取结果（IntentAgent 结构化输出）"""
    intent: str = Field(description="必须是 Intent 枚举之一：PLAN_RECOMMENDATION, CLARIFY_NEEDED, PLAN_ADJUST, PLAN_BOOK, ORDER_QUERY, ORDER_CHANGE, ORDER_CANCEL, PRICE_MONITOR, CHECKLIST_EXPORT, OTHER")
    slots: TravelSlotBundle = Field(..., description="提取到的 6 维出行槽位")
    confidence: float = Field(..., description="意图识别置信度分数 (0.0 到 1.0)")


class InboundMessage(BaseModel):
    """各通道进来的消息统一模型（A2 定稿）"""
    channel: str = Field(..., description='"web" | "dingtalk" | "wechat" | "qq"')
    channel_user_id: str = Field(..., description="通道内用户标识（web=userId，钉钉=ding_xxx）")
    user_id: Optional[int] = Field(default=None, description="系统统一 userId（首次进入绑定）")
    session_key: str = Field(..., description='会话键 = "web:1" / "dingtalk:ding_123"')
    text: str = Field(..., description="消息文本")
    attachments: List[str] = Field(default_factory=list, description="图片/文件")
    timestamp: datetime = Field(default_factory=datetime.now)


class OutboundMessage(BaseModel):
    """所有要发出去的内容统一模型（A2 定稿）"""
    kind: str = Field(default="TEXT", description="TEXT / CARD / IMAGE / TASK_PROGRESS")
    channel: str = Field(default="web")
    channel_user_id: str = Field(default="")
    session_id: Optional[str] = Field(default=None, description="会话ID（回传前端继续多轮）")
    text: str = Field(default="", description="文本内容")
    blocks: List[dict] = Field(default_factory=list, description="方案卡片等结构化内容")
    image_path: Optional[str] = Field(default=None, description="二维码/图片")
    task_progress: Optional[dict] = Field(default=None, description='{"taskId","status","progress"}')
    correlation_id: Optional[str] = Field(default=None, description="关联 traceId / taskId")
    sync_reply: bool = Field(default=False, description="Web 同步回复（HTTP 响应已返回，SSE 不再重复推送）")


class TravelChatRequest(BaseModel):
    """Web 通道对话请求参数（A2：POST /api/v1/travel/chat）"""
    sessionId: Optional[str] = Field(default=None, description="会话唯一ID")
    message: str = Field(..., description="用户发来的消息文本")
    channel: str = Field(default="web", description="默认 web 通道")


class TravelChatResponse(BaseModel):
    """对话响应结构（与前端契约保持兼容：ANSWER/CLARIFY）"""
    sessionId: str
    traceId: Optional[str] = None
    responseType: str = Field(..., description="ANSWER / CLARIFY / TASK_PROGRESS")
    speechText: str
    displayBlocks: List[dict] = Field(default_factory=list, description="方案/订单卡片集")
    nextAction: str = Field(default="WAIT_USER")
    clarifyQuestion: Optional[str] = None
    missingSlots: List[str] = Field(default_factory=list)
    taskId: Optional[str] = None
    orderNo: Optional[str] = None


class CreateSessionResponse(BaseModel):
    """创建会话成功返回结构"""
    sessionId: str


class TransportLeg(BaseModel):
    """单段行程（B2 定稿）"""
    leg_no: int = Field(default=1)
    mode: str = Field(..., description="FLIGHT / TRAIN / BUS / TRANSFER")
    from_city: str
    to_city: str
    from_station: Optional[str] = Field(default=None, description="乘车站/出发机场（如 北京南站/大兴国际机场）")
    to_station: Optional[str] = Field(default=None, description="到达站/抵达机场")
    arrive_day: int = Field(default=1, description="到达日数（火车跨天为 2，用于展示与耗时计算）")
    depart: str = Field(..., description="出发时刻 HH:MM")
    arrive: str = Field(..., description="到达时刻 HH:MM")
    price: float
    vehicle_no: str = Field(default="", description="航班号/车次")
    seat: Optional[str] = Field(default=None, description="舱位/席别")
    carrier: Optional[str] = Field(default=None, description="航司/承运")


class PlanOption(BaseModel):
    """候选出行方案（B2 定稿）"""
    plan_id: Optional[str] = Field(default=None, description="方案ID（落库后回填）")
    trip_id: Optional[int] = Field(default=None)
    legs: List[TransportLeg]
    total_price: float
    total_duration_h: float
    meets_budget: bool = True
    score: float = 0.0
    budget_deviation: Optional[float] = Field(default=None, description="相对档位参考价偏差")

    def summary(self) -> str:
        """方案的一行摘要（用于方案卡片文本）"""
        seg = " → ".join(
            f"{l.vehicle_no or l.mode} {l.from_station or l.from_city}{l.depart}→{l.to_station or l.to_city}{l.arrive}"
            for l in self.legs
        )
        return f"方案 {self.plan_id or '-'}：{seg}，总价 ¥{self.total_price:.0f}，耗时 {self.total_duration_h:.1f}h，评分 {self.score:.2f}"


class PlanDecision(BaseModel):
    """规划器输出（B2 定稿）"""
    options: List[PlanOption]
    recommended: Optional[PlanOption] = None
    reason: str = ""


class TrainItem(BaseModel):
    """火车班次统一数据模型（C1 定稿）"""
    origin: str
    destination: str
    depart_time: str
    arrive_time: str
    train_no: str
    seat_class: str = "二等座"
    price: float
    remaining: int = 99


class FlightItem(BaseModel):
    """航班统一数据模型（C1 定稿）"""
    origin: str
    destination: str
    depart_time: str
    arrive_time: str
    flight_no: str
    airline: str = ""
    price: float
    remaining: int = 99


class GeoPoint(BaseModel):
    """地理编码/POI 统一模型（C1 定稿）"""
    city: str
    name: str
    kind: str = ""  # airport / station
    lat: float = 0.0
    lng: float = 0.0


class HourlyWeather(BaseModel):
    """和风逐小时天气统一模型（C1 定稿）"""
    time: str
    temp: float = 0.0
    feels_like: float = 0.0
    wind: str = ""
    precip_prob: float = 0.0
    text: str = "晴"


class ChangeRequest(BaseModel):
    """改签/退票/降价决策请求（B1 定稿）"""
    order_no: str
    scenario: ChangeScenario = ChangeScenario.USER_CHANGE
    target_date: Optional[str] = Field(default=None, description="目标出行日期 YYYY-MM-DD")
    target_time_pref: Optional[str] = Field(default=None, description="目标时刻偏好（软约束）")
    budget: Optional[str] = Field(default=None, description="预算档位")


class ChangeOption(BaseModel):
    """改签/退票候选方案（B1 定稿）"""
    kind: ChangeKind
    original_leg: Optional[dict] = None
    new_leg: Optional[dict] = None
    old_price: float = 0.0
    new_price: float = 0.0
    change_fee: float = 0.0
    refund_fee: float = 0.0
    total_loss: float = 0.0  # 可为负（省钱）
    satisfies_need: bool = True  # 仅内部打分，展示层不输出
    time_pref_match: bool = True  # 仅内部打分
    risks: List[str] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)
    score: float = 0.0  # 内部打分值（展示层不输出）


class ChangeDecision(BaseModel):
    """决策服务输出（B1 定稿）"""
    request: ChangeRequest
    options: List[ChangeOption]
    recommended: Optional[ChangeOption] = None
    reason: str = ""


class UserProfile(BaseModel):
    """L1 用户画像（C2 定稿）"""
    user_id: int
    home_city: Optional[str] = None
    passengers: List[dict] = Field(default_factory=list)  # [{name, id_type, id_no, id_expiry}]
    budget_level: Optional[str] = None  # economy / comfort / premium
    preferences: dict = Field(default_factory=dict)  # cost_vs_time/tolerate_change/preferred_transport/seat_pref/early_bird


class TripSummary(BaseModel):
    """L2 行程摘要"""
    id: Optional[int] = None
    user_id: int
    trip_id: Optional[int] = None
    summary_md: str
    created_at: Optional[datetime] = None


class OrderDraftOut(BaseModel):
    """订单草稿/查询输出"""
    order_no: str
    supplier: str
    type: str
    status: str
    price: float
    tax_fee: float
    passengers: List[dict] = Field(default_factory=list)
    legs: List[dict] = Field(default_factory=list)
    qr_image_path: Optional[str] = None
    pending: Optional[str] = None  # PAYMENT / MANUAL_STEP / USER_CONFIRM


class TaskOut(BaseModel):
    """任务查询输出"""
    task_id: str
    type: str
    status: str
    progress: int = 0
    result: Optional[dict] = None
    error_message: Optional[str] = None


class FeedbackRequest(BaseModel):
    """方案反馈（LIKE/DISLIKE/SWITCH → L1 偏好微调）"""
    sessionId: str
    itemId: Optional[int] = None
    planId: Optional[str] = None
    action: str = Field(..., description="LIKE / DISLIKE / SWITCH")
    rating: Optional[int] = Field(default=None, description="评分(1-5星)")
    reason: Optional[str] = None


class EvaluationRequest(BaseModel):
    """评估任务运行请求体"""
    startAt: datetime
    endAt: datetime
    includeLlmJudge: Optional[bool] = False
    limit: Optional[int] = None


class TraceEvaluationResult(BaseModel):
    """单条 Trace 的评估明细记录"""
    traceId: str
    sessionId: str
    createdAt: datetime
    score: Optional[float] = None
    ruleScore: Optional[float] = None
    llmJudgeScore: Optional[float] = None
    userFeedbackScore: Optional[float] = None
    metrics: Dict[str, Optional[float]]
    detail: Dict[str, Any]


class EvaluationReport(BaseModel):
    """完整的系统离线评估报告"""
    startAt: datetime
    endAt: datetime
    totalTraces: int
    labeledTraces: int
    avgScore: Optional[float] = None
    metricAverages: Dict[str, Optional[float]]
    traceResults: List[TraceEvaluationResult]


class TraceLabelRequest(BaseModel):
    """人工标定金标准答案请求"""
    expectedIntent: Optional[Intent] = None
    expectedSlots: Optional[TravelSlotBundle] = None
    expectedClarifyAction: Optional[ClarifyAction] = None
    labelNote: Optional[str] = None


class TraceRowOut(BaseModel):
    """Trace 记录对外输出模型（驼峰命名）"""
    traceId: str
    sessionId: str
    userId: int
    status: str
    eventCount: int
    durationMs: Optional[int] = None
    errorMessage: Optional[str] = None
    traceJson: Any
    createdAt: datetime
    updatedAt: datetime
    expectedIntent: Optional[str] = None
    expectedSlots: Optional[Any] = None
    expectedClarifyAction: Optional[str] = None
    labeledBy: Optional[int] = None
    labeledAt: Optional[datetime] = None
    labelNote: Optional[str] = None


class SessionState(BaseModel):
    """
    会话状态机运行上下文。
    维护槽位合并、当前意图、阶段、已推荐方案与进行中的订单。
    """
    sessionId: str
    userId: int
    phase: SessionPhase
    channel: Channel = Channel.web
    currentIntent: Optional[Intent] = None
    slots: TravelSlotBundle = Field(default_factory=TravelSlotBundle)
    lastRecommendations: List[str] = Field(default_factory=list)  # 已推荐方案 plan_id 列表
    currentBatch: List[str] = Field(default_factory=list)  # 当前批次方案 plan_id（用于“方案2”下单）
    selectedPlanId: Optional[str] = None
    orderId: Optional[int] = None
    orderNo: Optional[str] = None

from enum import Enum


class Intent(str, Enum):
    """出行 Agent 对话意图枚举（A1 定稿，10 类）"""
    # 出行方案推荐
    PLAN_RECOMMENDATION = "PLAN_RECOMMENDATION"
    # 信息不足追问
    CLARIFY_NEEDED = "CLARIFY_NEEDED"
    # 调整方案（换一批/太贵/换交通方式等）
    PLAN_ADJUST = "PLAN_ADJUST"
    # 确认下单
    PLAN_BOOK = "PLAN_BOOK"
    # 查订单
    ORDER_QUERY = "ORDER_QUERY"
    # 改签
    ORDER_CHANGE = "ORDER_CHANGE"
    # 取消/退票
    ORDER_CANCEL = "ORDER_CANCEL"
    # 价格监控开关（默认开启）
    PRICE_MONITOR = "PRICE_MONITOR"
    # 出行清单导出
    CHECKLIST_EXPORT = "CHECKLIST_EXPORT"
    # 兜底闲聊 + 安全风险
    OTHER = "OTHER"


class ClarifyAction(str, Enum):
    """澄清对话判定动作"""
    ASK = "ASK"
    READY = "READY"


class SessionPhase(str, Enum):
    """会话所处生命周期状态阶段（A1 定稿）"""
    START = "START"
    CLARIFY = "CLARIFY"
    PLAN = "PLAN"
    BOOKING = "BOOKING"
    ORDER = "ORDER"
    MONITORING = "MONITORING"


class Channel(str, Enum):
    """消息通道类型（A2 定稿）"""
    web = "web"
    dingtalk = "dingtalk"
    wechat = "wechat"
    qq = "qq"


class TransportMode(str, Enum):
    """交通方式"""
    FLIGHT = "FLIGHT"
    TRAIN = "TRAIN"
    BUS = "BUS"
    TRANSFER = "TRANSFER"


class BudgetTier(str, Enum):
    """预算相对档位（不存绝对金额）"""
    economy = "economy"
    comfort = "comfort"
    premium = "premium"


class OrderStatus(str, Enum):
    """订单状态机（C3 定稿）"""
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    BOOKING = "BOOKING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    CHANGING = "CHANGING"
    CHANGED = "CHANGED"
    CHANGE_CANCELLED = "CHANGE_CANCELLED"
    REFUNDING = "REFUNDING"


class TaskStatus(str, Enum):
    """后台任务状态机（A3 定稿）"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskType(str, Enum):
    """后台任务类型"""
    book = "book"
    change = "change"
    refund = "refund"
    price_watch = "price_watch"
    flight_monitor = "flight_monitor"
    advisory = "advisory"
    checklist = "checklist"
    memory_distill = "memory_distill"


class OrderType(str, Enum):
    """订单类型"""
    FLIGHT = "FLIGHT"
    TRAIN = "TRAIN"


class Supplier(str, Enum):
    """供应商（供应商可替换原则）"""
    ctrip = "ctrip"
    airline = "airline"
    mock = "mock"


class PaymentPending(str, Enum):
    """WAITING_USER 等待用户操作的类型（A3 定稿）"""
    PAYMENT = "PAYMENT"
    MANUAL_STEP = "MANUAL_STEP"
    USER_CONFIRM = "USER_CONFIRM"


class ChangeKind(str, Enum):
    """改签/退票决策候选类型（B1 定稿）"""
    CHANGE = "CHANGE"
    CANCEL_REBOOK = "CANCEL_REBOOK"
    CANCEL = "CANCEL"
    KEEP = "KEEP"


class ChangeScenario(str, Enum):
    """决策服务场景（B1 定稿）"""
    USER_CHANGE = "USER_CHANGE"
    USER_CANCEL = "USER_CANCEL"
    PRICE_DROP = "PRICE_DROP"
    FLIGHT_CHANGE = "FLIGHT_CHANGE"

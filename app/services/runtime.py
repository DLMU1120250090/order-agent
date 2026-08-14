"""
运行时装配（单例）：集中构建 Agent 工厂 / 通道 / 服务依赖，供路由与调度使用。
"""
from app.agents.factory import AgentFactory
from app.channels.manager import ChannelManager
from app.services.booking import BookingService
from app.services.browser import browser_order
from app.services.change_decision import ChangeDecisionService
from app.services.checklist import ChecklistService
from app.services.collector import DataCollectorService
from app.services.memory import MemoryService
from app.services.mock_supplier import mock_supplier
from app.services.monitor import FlightMonitorService, PriceMonitorService
from app.services.orchestrator import TravelOrchestratorService
from app.services.push import PushService
from app.services.qr_capture import QrCaptureService
from app.services.reminder import ReminderService
from app.services.scheduler import SchedulerService
from app.services.task import TaskService
from app.services.weather_advice import WeatherAdvisoryService

# ---- 基础服务 ----
agent_factory = AgentFactory()
push_service = PushService()
task_service = TaskService(push_service)
qr_capture = QrCaptureService()
collector = DataCollectorService()
change_decision = ChangeDecisionService(collector)
checklist = ChecklistService()

# ---- 领域服务 ----
booking = BookingService(qr_capture, push_service, task_service)
memory = MemoryService()
orchestrator = TravelOrchestratorService(
    agent_factory,
    push_service,
    task_service,
    booking,
    memory,
    collector,
    change_decision,
    checklist,
)
channel_manager = ChannelManager(orchestrator, push_service)

# ---- 主动服务（定时任务） ----
weather_advice = WeatherAdvisoryService()
reminder = ReminderService(memory, weather_advice, checklist, push_service, task_service, collector)
price_monitor = PriceMonitorService(collector, change_decision, push_service)
flight_monitor = FlightMonitorService(change_decision, push_service)
scheduler = SchedulerService(task_service, reminder, price_monitor, flight_monitor, memory)

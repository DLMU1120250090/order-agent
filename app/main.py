import os
import asyncio
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

def _setup_logging():
    """控制台 + 文件双写：travel.* 强制可见，其余（uvicorn/钉钉SDK等）写日志文件便于排查。"""
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

    # 1) travel.* 业务日志：控制台 + 文件（不传播到 root，避免与 root 文件句柄重复）
    travel_logger = logging.getLogger("travel")
    if not travel_logger.handlers:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        travel_logger.addHandler(console)
    travel_logger.setLevel(logging.INFO)
    travel_logger.propagate = False

    # 2) 文件日志（logs/app.log，10MB 轮转保留 5 份）
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(project_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.INFO)

    # root：捕获 uvicorn.error、钉钉 SDK 等所有向上传播的日志
    logging.getLogger().addHandler(file_handler)
    # propagate=False 的 logger 各自挂文件句柄
    for name in ("travel", "uvicorn", "uvicorn.access"):
        logging.getLogger(name).addHandler(file_handler)


_setup_logging()

from app.channels.dingtalk import dingtalk_channel
from app.database import async_session_maker
from app.routers import (
    chat, debug, evaluation, events, feedback, mock_supplier, orders, profiles,
    session, tasks, webhook_dingtalk, webhook_wechat,
)
from app.services.dingtalk_stream import dingtalk_stream_service
from app.services.runtime import scheduler

log = logging.getLogger("travel.main")


async def _on_dingtalk_message(text: str, msg):
    """钉钉 Stream 收到文本 -> 走统一分发管线"""
    from app.services.runtime import channel_manager

    inbound = dingtalk_channel.to_inbound_chatbot(msg)
    log.info("钉钉消息进入分发: user=%s text=%r", inbound.channel_user_id, text)
    try:
        async with async_session_maker() as db:
            await channel_manager.dispatch(db, inbound)
    except Exception as e:  # noqa: BLE001
        log.exception("钉钉消息处理失败: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动定时任务：price_watch / flight_monitor / departure_reminder / memory_distill / retry_worker
    scheduler.start()
    loop = asyncio.get_running_loop()
    dingtalk_stream_service.start(loop, _on_dingtalk_message)
    yield
    dingtalk_stream_service.stop()
    scheduler.shutdown()


# 初始化 FastAPI 应用程序
app = FastAPI(
    title="出行规划与预订 Agent API",
    version="2.0.0",
    description="Diet Agent → 出行规划与预订 Agent（FastAPI + LangChain）。动作型 Agent：规划/下单/改签/退票/监控/记忆。",
    lifespan=lifespan,
)

# CORS（本地调试）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"message": str(exc) or "服务异常"})


# 注册出行域路由（含 Mock 供应商 / 微信 Mock 桥）
app.include_router(chat.router)
app.include_router(session.router)
app.include_router(events.router)
app.include_router(tasks.router)
app.include_router(orders.router)
app.include_router(profiles.router)
app.include_router(feedback.router)
app.include_router(evaluation.router)
app.include_router(webhook_dingtalk.router)
app.include_router(webhook_wechat.router)
app.include_router(mock_supplier.router)
app.include_router(debug.router)

# 出行 Agent 自有前端静态资源（order-agent/static）
# 包含 Mock 收银台页（/mock/checkout.html，Playwright 下单自动化演示）
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(project_dir, "static")
if os.path.exists(static_dir):
    # 记忆产物（二维码截图、L2/L3 md）通过 /media 暴露，供前端展示
    media_dir = os.path.join(project_dir, "memory")
    if os.path.exists(media_dir):
        app.mount("/media", StaticFiles(directory=media_dir), name="media")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    print(f"警告: 静态资源目录 '{static_dir}' 未找到。前端网页将无法托管服务。")

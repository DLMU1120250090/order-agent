"""Playwright 下单自动化（Mock 收银台）。
真实模式：持久化登录态（launch_persistent_context）操作携程；
当前演示：导航到本服务自带的 Mock 收银台页面，模拟确认订单并截图二维码元素，
页面自动/手动模拟支付后，第 1 层页面变化检测通过 #pay-success 元素判定支付成功。

注意：Windows 下 uvicorn --reload 的工作进程可能使用 Selector 事件循环，
asyncio 子进程会抛 NotImplementedError，因此这里把 Playwright（sync API）
放到独立的浏览器线程执行，与事件循环类型无关。
"""

import asyncio
import concurrent.futures
import logging
import os
import queue
import threading
from datetime import datetime
from typing import Callable, Dict, Optional

from app.config import settings
from app.models.database import TravelOrderRow

log = logging.getLogger("travel.browser")


class _BrowserThread:
    """专用浏览器线程：所有 Playwright 调用都在同一线程内串行执行（线程安全）。"""

    def __init__(self):
        self._jobs: "queue.Queue" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="playwright-browser", daemon=True)
        self._thread.start()

    def _run(self):
        while True:
            fut, fn = self._jobs.get()
            try:
                fut.set_result(fn())
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)

    def submit(self, fn: Callable[[], object]) -> concurrent.futures.Future:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._jobs.put((fut, fn))
        return fut


class BrowserOrderService:
    """Playwright 下单 + 收银台二维码截图 + 页面变化检测（sync API + 专用线程）。"""

    def __init__(self):
        self._thread = _BrowserThread()
        self._sessions: Dict[str, dict] = {}
        self._user_data_dir = ""

    def user_data_dir(self) -> str:
        if not self._user_data_dir:
            base = settings.TRAVEL_PLAYWRIGHT_USER_DATA_DIR.strip()
            if base:
                self._user_data_dir = os.path.abspath(base)
            else:
                project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                self._user_data_dir = os.path.join(project_dir, "memory", "playwright", "ctx")
            os.makedirs(self._user_data_dir, exist_ok=True)
        return self._user_data_dir

    async def place_and_capture_qr(self, order: TravelOrderRow) -> str:
        """打开 Mock 收银台 → 确认订单 → 等待二维码元素 → 截图保存，返回图片路径。"""
        fut = self._thread.submit(lambda: self._place_sync(order))
        return await asyncio.wrap_future(fut)

    def _place_sync(self, order: TravelOrderRow) -> str:
        from playwright.sync_api import sync_playwright

        base = settings.TRAVEL_MOCK_CHECKOUT_BASE_URL.rstrip("/")
        passenger = ((order.passengers or {}).get("list") or [{}])[0].get("name", "演示乘客")
        url = (
            f"{base}/mock/checkout.html"
            f"?order_no={order.order_no}"
            f"&price={order.price:.0f}"
            f"&passenger={passenger}"
            f"&auto_pay={settings.TRAVEL_MOCK_CHECKOUT_AUTO_PAY_SECONDS}"
        )
        log.info("Playwright 打开 Mock 收银台: %s", url)

        pw = sync_playwright().start()
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir(),
                headless=settings.TRAVEL_PLAYWRIGHT_HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                viewport={"width": 960, "height": 720},
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(url, wait_until="networkidle", timeout=20000)
            # 模拟自动化步骤：点击「确认订单」进入收银台
            page.click("#btn-confirm", timeout=10000)
            page.wait_for_selector("#qr-code", timeout=15000)
            qr_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "memory", "qr",
            )
            os.makedirs(qr_dir, exist_ok=True)
            path = os.path.join(qr_dir, f"qr_{order.order_no}_{datetime.now().strftime('%H%M%S')}.png")
            page.locator("#qr-code").screenshot(path=path)
            log.info("Playwright 已截图收银台二维码: %s", path)
        except Exception:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass
            raise

        # 保留会话供第 1 层页面变化检测（模拟支付后 #pay-success 出现）
        self._sessions[order.order_no] = {"pw": pw, "context": context, "page": page}
        return path

    async def check_paid(self, order_no: str) -> bool:
        """第 1 层：页面变化检测——Mock 收银台出现「支付成功」元素。"""
        session = self._sessions.get(order_no)
        if session is None:
            return False
        fut = self._thread.submit(lambda: self._check_paid_sync(session))
        return bool(await asyncio.wrap_future(fut))

    @staticmethod
    def _check_paid_sync(session: dict) -> bool:
        try:
            # 元素常驻但默认隐藏（display:none），支付成功后才可见，因此只统计可见元素
            return session["page"].locator("#pay-success:visible").count() > 0
        except Exception as e:  # noqa: BLE001
            log.warning("第1层页面检测异常: %s", e)
            return False

    async def close(self, order_no: str):
        session = self._sessions.pop(order_no, None)
        if session is None:
            return
        fut = self._thread.submit(lambda: self._close_sync(session, order_no))
        await asyncio.wrap_future(fut)

    @staticmethod
    def _close_sync(session: dict, order_no: str):
        try:
            session["context"].close()
        except Exception:  # noqa: BLE001
            pass
        try:
            session["pw"].stop()
        except Exception:  # noqa: BLE001
            pass
        log.info("Playwright 会话已关闭: order_no=%s", order_no)

    async def close_all(self):
        for order_no in list(self._sessions):
            await self.close(order_no)


browser_order = BrowserOrderService()

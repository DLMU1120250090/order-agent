"""Playwright 下单自动化（Mock 收银台 + 真实携程尝试）。
真实模式：持久化登录态（launch_persistent_context）操作携程；
  开启 TRAVEL_CTRIP_REAL_ENABLED 后，先探测携程页面：被 whaleguard 反爬/
  登录墙拦截（当前实测即为 whaleguard block）→ 自动回退 Mock 收银台；
  若未来页面可访问，可在 _place_ctrip_sync 中继续适配 搜索→选方案→收银台 流程。
当前演示（默认）：导航到本服务自带的 Mock 收银台页面，模拟确认订单并截图二维码元素，
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


class CtripUnavailable(RuntimeError):
    """真实携程自动化不可用（反爬/登录墙/页面未适配）——由上层捕获并回退 Mock。"""


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
        """下单 + 二维码截图。
        真实携程模式开启时优先尝试真实携程（登录/反爬拦截自动回退）；
        否则直接走 Mock 收银台。
        """
        fut = self._thread.submit(lambda: self._place_auto(order))
        return await asyncio.wrap_future(fut)

    def _place_auto(self, order: TravelOrderRow) -> str:
        if settings.TRAVEL_CTRIP_REAL_ENABLED:
            try:
                return self._place_ctrip_sync(order)
            except Exception as e:  # noqa: BLE001
                log.warning("真实携程自动化不可用，自动回退 Mock 收银台: order=%s err=%s", order.order_no, e)
        return self._place_sync(order)

    def _place_ctrip_sync(self, order: TravelOrderRow) -> str:
        """真实携程下单尝试（尽力而为）：
        1) 打开携程国内机票频道，探测登录态/反爬拦截（whaleguard、安全验证、passport 跳转）；
        2) 被拦截 → 抛 CtripUnavailable，由上层自动回退 Mock 收银台；
        3) 若未来页面可访问，在此继续适配「搜索 → 选方案 → 收银台二维码」流程。
        """
        from playwright.sync_api import sync_playwright

        base = settings.TRAVEL_CTRIP_BASE_URL.rstrip("/")
        log.info("Playwright 尝试真实携程下单: %s order=%s", base, order.order_no)
        pw = sync_playwright().start()
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir(),
                headless=settings.TRAVEL_PLAYWRIGHT_HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(base, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(settings.TRAVEL_CTRIP_PROBE_TIMEOUT * 1000)

            # ① 登录态 / 反爬拦截探测（实测 whaleguard 直接拦截无头访问）
            url = page.url.lower()
            body = ""
            try:
                body = (page.inner_text("body") or "")[:3000].lower()
            except Exception:  # noqa: BLE001
                pass
            if any(k in url for k in ("passport.ctrip.com", "/login")) or any(
                k in body for k in ("whaleguard", "安全验证", "滑动验证", "验证码", "请登录", "立即登录")
            ):
                raise CtripUnavailable("携程反爬/登录拦截（whaleguard），无法自动下单")

            # ② 未拦截但未进入收银台：当前未适配真实 DOM，回退 Mock（后续在此扩展）
            raise CtripUnavailable("真实携程页面未进入收银台（DOM 未适配）")
        finally:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass

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

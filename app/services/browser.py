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

    def user_data_dir(self, ctrip: bool = False) -> str:
        if not self._user_data_dir:
            if ctrip:
                base = (settings.TRAVEL_CTRIP_USER_DATA_DIR or settings.TRAVEL_PLAYWRIGHT_USER_DATA_DIR or "").strip()
            else:
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
        3) 未被拦截（真实 Chrome 实测可过鲸盾）→ 尽力推进「搜索」；
        4) 搜索/选座/收银台任一环节未完成 → 同样回退 Mock（真实下单还需登录态与页面适配）。
        """
        from playwright.sync_api import sync_playwright

        base = settings.TRAVEL_CTRIP_BASE_URL.rstrip("/")
        log.info("Playwright 尝试真实携程下单: %s order=%s", base, order.order_no)
        pw = sync_playwright().start()
        try:
            channel = settings.TRAVEL_CTRIP_CHANNEL.strip() or None
            try:
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir(ctrip=True),
                    channel=channel,
                    headless=settings.TRAVEL_CTRIP_HEADLESS,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                    viewport={"width": 1440, "height": 900},
                    locale="zh-CN",
                )
            except Exception as e:  # noqa: BLE001
                # 通道不可用（如本机无 Chrome）→ 回退内置 Chromium（大概率被 whaleguard 拦，随后自动回退 Mock）
                log.warning("携程真实模式通道 %s 启动失败，回退内置 Chromium: %s", channel, e)
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir(ctrip=True),
                    headless=settings.TRAVEL_CTRIP_HEADLESS,
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

            # ② 未被拦截：尽力推进搜索（真实 DOM 随版本变化，失败即回退 Mock）
            legs = (order.legs or {}).get("legs", [])
            origin = legs[0].get("from_city") if legs else ""
            destination = legs[-1].get("to_city") if legs else ""
            if not (origin and destination):
                raise CtripUnavailable("订单缺少出发/到达城市，无法真实搜索")
            searched = self._try_ctrip_search(page, origin, destination)
            if not searched:
                raise CtripUnavailable("携程搜索表单未适配（DOM 变化），回退 Mock")

            # ③ 已进入搜索结果：选座/收银台仍需登录态与页面适配，交由 Mock 完成支付演示
            raise CtripUnavailable("已进入携程搜索结果页，选座/收银台待适配，回退 Mock 完成支付演示")
        finally:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass

    def _try_ctrip_search(self, page, origin: str, destination: str) -> bool:
        """尽力在携程搜索页填写 出发地/目的地 并点击搜索（候选选择器随版本维护）。
        任一步失败返回 False，由上层回退 Mock。
        """
        try:
            # 1) 关闭可能的营销弹层
            for sel in (".mt_tips_close", "[class*='close']:visible", ".pop-close", ".dialog-close"):
                try:
                    el = page.locator(sel).first
                    if el.count() and el.is_visible():
                        el.click(timeout=2000)
                        page.wait_for_timeout(500)
                except Exception:  # noqa: BLE001
                    pass

            # 2) 城市输入（自定义城市选择器：点击城市框 → 输入城市名 → 选首个候选项）
            if not self._fill_ctrip_city(page, origin):
                log.warning("携程出发地填写失败")
                return False
            if not self._fill_ctrip_city(page, destination):
                log.warning("携程目的地填写失败")
                return False

            # 3) 点击搜索
            btn = page.locator(".search-btn").first
            if not (btn.count() and btn.is_visible()):
                log.warning("携程搜索按钮未找到")
                return False
            btn.click(timeout=5000)
            page.wait_for_timeout(8000)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("携程搜索推进异常: %s", e)
            return False

    def _fill_ctrip_city(self, page, city: str) -> bool:
        """点击城市输入框 → 输入城市名 → 选择首个候选；选择器失败则返回 False。"""
        for box_sel in (
            "input[placeholder*='出发']",
            "input[placeholder*='到达']",
            "input[placeholder*='目的地']",
            "input[placeholder*='城市']",
            "[class*='city'] input:visible",
            "[class*='search'] input:visible",
        ):
            try:
                box = page.locator(box_sel).first
                if not (box.count() and box.is_visible()):
                    continue
                box.click(timeout=3000)
                page.wait_for_timeout(600)
                box.fill(city)
                page.wait_for_timeout(1200)
                for opt_sel in (".city-result li:visible", "[class*='city'] li:visible", ".search-list li:visible"):
                    opt = page.locator(opt_sel).first
                    if opt.count() and opt.is_visible():
                        opt.click(timeout=3000)
                        return True
            except Exception:  # noqa: BLE001
                continue
        return False

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

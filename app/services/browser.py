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


class BrowserOrderService:
    """Playwright 下单 + 收银台二维码截图 + 页面变化检测（sync API + 每会话独立线程）。

    注意：sync_playwright 会在所在线程创建并持有自己的事件循环，且会话存活期间该循环
    一直处于「运行中」。若多个订单复用一个线程，第二次 sync_playwright 启动会报
    "Sync API inside the asyncio loop"。因此每个下单任务使用独立线程，会话存活期间
    由该线程持续服务（check_paid/close 命令循环），直到会话关闭。
    """

    def __init__(self):
        self._sessions: Dict[str, dict] = {}
        self._session_queues: Dict[str, "queue.Queue"] = {}
        self._lock = threading.Lock()
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

    async def place_and_capture_qr(self, order: TravelOrderRow, trip_date: str = "") -> str:
        """下单 + 二维码截图。
        真实携程模式开启时优先尝试真实携程（登录/反爬拦截自动回退）；
        否则直接走 Mock 收银台。每个订单在独立线程执行（sync Playwright 循环隔离）。
        trip_date 为真实携程搜索的出行日期（YYYY-MM-DD）。
        """
        fut: concurrent.futures.Future = concurrent.futures.Future()

        def job():
            try:
                path = self._place_auto(order, trip_date)
                fut.set_result(path)
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)
            # 下单成功且保留了会话（第1层页面变化检测）→ 本线程继续服务该会话直至 close
            with self._lock:
                q = self._session_queues.get(order.order_no)
            if q is not None:
                self._serve_session(order.order_no, q)

        threading.Thread(target=job, name=f"playwright-{order.order_no}", daemon=True).start()
        return await asyncio.wrap_future(fut)

    def _serve_session(self, order_no: str, q: "queue.Queue") -> None:
        """会话线程命令循环：check / close。"""
        while True:
            cmd, fut, fn = q.get()
            try:
                result = fn()
                fut.set_result(result)
            except Exception as e:  # noqa: BLE001
                fut.set_exception(e)
            if cmd == "close":
                return

    def _submit_session(self, order_no: str, cmd: str, fn) -> concurrent.futures.Future:
        fut: concurrent.futures.Future = concurrent.futures.Future()
        with self._lock:
            q = self._session_queues.get(order_no)
        if q is None:
            fut.set_exception(RuntimeError(f"会话不存在: {order_no}"))
            return fut
        q.put((cmd, fut, fn))
        return fut

    def _cleanup_session(self, order_no: str) -> None:
        """关闭会话的浏览器上下文并停止 Playwright 驱动。"""
        session = self._sessions.pop(order_no, None)
        if session:
            try:
                session["context"].close()
            except Exception:  # noqa: BLE001
                pass
            try:
                session["pw"].stop()
            except Exception:  # noqa: BLE001
                pass
            log.info("Playwright 会话已关闭: order_no=%s", order_no)

    def _place_auto(self, order: TravelOrderRow, trip_date: str = "") -> str:
        if settings.TRAVEL_CTRIP_REAL_ENABLED:
            try:
                return self._place_ctrip_sync(order, trip_date)
            except Exception as e:  # noqa: BLE001
                log.warning("真实携程自动化不可用，自动回退 Mock 收银台: order=%s err=%s", order.order_no, e)
        return self._place_sync(order)

    def _place_ctrip_sync(self, order: TravelOrderRow, trip_date: str = "") -> str:
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
            searched = self._try_ctrip_search(page, origin, destination, trip_date)
            if not searched:
                raise CtripUnavailable("携程搜索表单未适配（DOM 变化），回退 Mock")

            # ③ 已进入搜索结果：选座/收银台仍需登录态与页面适配，交由 Mock 完成支付演示
            raise CtripUnavailable("已进入携程搜索结果页，选座/收银台待适配，回退 Mock 完成支付演示")
        finally:
            try:
                pw.stop()
            except Exception:  # noqa: BLE001
                pass

    def _try_ctrip_search(self, page, origin: str, destination: str, trip_date: str = "") -> bool:
        """尽力在携程搜索页推进：单程 → 出发地/目的地 → 出行日期 → 关闭城市选择器 → 点击搜索。
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

            # 1.5) 切到「单程」（页面默认「往返」）
            try:
                one_way = page.locator(".form-select-radio-group li").first
                if one_way.count() and one_way.is_visible():
                    one_way.click(timeout=3000)
                    page.wait_for_timeout(600)
            except Exception:  # noqa: BLE001
                pass

            # 2) 城市输入：出发地 .flt-depart / 目的地 .flt-arrival（自定义城市选择器）
            if not self._fill_ctrip_city(page, origin, "depart"):
                log.warning("携程出发地填写失败")
                return False
            if not self._fill_ctrip_city(page, destination, "arrival"):
                log.warning("携程目的地填写失败")
                return False
            self._close_city_picker(page)

            # 3) 设置出行日期（页面默认是明天，必须按行程日期选择）
            if trip_date:
                if not self._set_trip_date(page, trip_date):
                    log.warning("携程日期设置失败: %s", trip_date)
                    return False
                self._close_city_picker(page)

            # 搜索前记录字段实际值（innerText + input.value 双源），便于确认出发/到达/日期
            try:
                dep_state = page.evaluate(
                    """() => {
                        const el = document.querySelector(".flt-depart");
                        if (!el) return "";
                        const p = [el.innerText || ""];
                        const inp = el.querySelector("input");
                        if (inp && inp.value) p.push(inp.value);
                        return p.join("|").replace(/\\s+/g, " ").slice(0, 30);
                    }"""
                )
                arr_state = page.evaluate(
                    """() => {
                        const el = document.querySelector(".flt-arrival");
                        if (!el) return "";
                        const p = [el.innerText || ""];
                        const inp = el.querySelector("input");
                        if (inp && inp.value) p.push(inp.value);
                        return p.join("|").replace(/\\s+/g, " ").slice(0, 30);
                    }"""
                )
                date_state = (page.locator("input[placeholder='yyyy-mm-dd']").first.input_value() or "")
                log.info("携程搜索前字段状态: 出发=%r 到达=%r 日期=%r", dep_state, arr_state, date_state)
            except Exception:  # noqa: BLE001
                pass

            # 4) 点击搜索（若仍被城市选择器遮挡，force 点击兜底）
            btn = page.locator(".search-btn").first
            if not (btn.count() and btn.is_visible()):
                log.warning("携程搜索按钮未找到")
                return False
            try:
                btn.click(timeout=5000)
            except Exception as e:  # noqa: BLE001
                log.warning("搜索按钮被遮挡，force 点击兜底: %s", e)
                btn.click(force=True, timeout=5000)
            page.wait_for_timeout(8000)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("携程搜索推进异常: %s", e)
            return False

    @staticmethod
    def _set_trip_date(page, trip_date: str) -> bool:
        """点击日期显示区 → 日历面板 → 按 data-testid 精确点击目标日期（可跨月翻页）。"""
        try:
            year, month, day = (int(x) for x in trip_date.split("-"))
        except Exception:  # noqa: BLE001
            log.warning("携程日期格式错误: %s", trip_date)
            return False
        try:
            date_field = page.locator(".modifyDate.depart-date").first
            if not (date_field.count() and date_field.is_visible()):
                return False
            date_field.click(timeout=5000)
            page.wait_for_timeout(1000)
            target = f"date-day-{year:04d}-{month:02d}-{day:02d}"
            for _ in range(13):  # 最多翻 13 个月
                cell = page.locator(f"div.date-day[data-testid='{target}']").first
                if cell.count():
                    cell.click(timeout=5000)
                    page.wait_for_timeout(600)
                    return True
                nxt = page.locator("span.in-date-picker.next-ico, span.next-ico").first
                if not (nxt.count() and nxt.is_visible()):
                    return False
                nxt.click(timeout=3000)
                page.wait_for_timeout(700)
            return False
        except Exception as e:  # noqa: BLE001
            log.warning("携程日期选择异常: %s", e)
            return False

    def _fill_ctrip_city(self, page, city: str, field: str) -> bool:
        """点击城市字段（depart/arrival）→ 输入城市名 → 文本匹配候选项/回车兜底。
        填写后校验字段值，失败自动重试一次；返回是否成功。
        """
        field_sel = ".flt-depart" if field == "depart" else ".flt-arrival"
        for attempt in range(2):
            try:
                self._close_city_picker(page)
                field_el = page.locator(field_sel).first
                if not (field_el.count() and field_el.is_visible()):
                    return False
                field_el.click(timeout=5000)
                page.wait_for_timeout(800)

                box = None
                # 关键：城市面板同时存在 owDCity（出发地）与 owACity（目的地）两个输入框，
                # 必须按字段取对应的输入框，否则永远填进出发地
                box_sels = (
                    ("input[name='owDCity'][placeholder*='城市']", "input[name='owDCity'][u_key='poi_input']")
                    if field == "depart"
                    else ("input[name='owACity'][placeholder*='城市']", "input[name='owACity'][u_key='poi_input']")
                )
                for sel in box_sels:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        box = loc
                        break
                if box is None:
                    log.warning(
                        "携程城市面板输入框未找到 field=%s 面板结构=%s",
                        field, self._picker_ancestors(page),
                    )
                    return False
                box.fill(city)
                page.wait_for_timeout(1500)

                picked = self._pick_city_option(page, city)
                if not picked:
                    box.press("Enter")
                    page.wait_for_timeout(800)
                self._close_city_picker(page)

                # 校验字段值是否真的生效：innerText + 字段内 input.value 双重判定
                # （城市可能渲染在文本里，也可能只存在于 input.value，单一读取会误报失败）
                try:
                    shown = page.evaluate(
                        """(sel) => {
                            const el = document.querySelector(sel);
                            if (!el) return "";
                            const parts = [el.innerText || ""];
                            const inp = el.querySelector("input");
                            if (inp && inp.value) parts.push(inp.value);
                            return parts.join("|");
                        }""",
                        field_sel,
                    ) or ""
                except Exception:  # noqa: BLE001
                    shown = ""
                if city in shown:
                    return True
                log.warning(
                    "携程城市未生效 field=%s city=%s 当前字段=%r 第%d次重试",
                    field, city, shown.strip()[:30], attempt + 2,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("携程城市填写异常 field=%s city=%s attempt=%d err=%s", field, city, attempt, e)
        return False

    @staticmethod
    def _picker_ancestors(page) -> str:
        """诊断：城市面板输入框的祖先结构（填写失败时打日志，便于迭代选择器）。"""
        try:
            return page.evaluate(
                """() => {
                    const el = document.querySelector("input[u_key='poi_input']");
                    if (!el) return "no-input";
                    const out = [];
                    let n = el.parentElement;
                    for (let i = 0; n && i < 4; i++, n = n.parentElement) {
                        out.push(n.className ? n.className.toString().slice(0, 80) : n.tagName);
                    }
                    return out.join(" > ");
                }"""
            )
        except Exception:  # noqa: BLE001
            return "?"

    @staticmethod
    def _pick_city_option(page, city: str) -> bool:
        """点击文本匹配的城市候选项（携程候选项是文本节点，如「北京(所有机场)BJSBJ」）；
        面板存在多份副本，只点击可见项。
        """
        try:
            for pattern in (f"{city}(所有机场)", f"{city}首都国际机场", f"{city}站"):
                locs = page.get_by_text(pattern, exact=False)
                for i in range(min(locs.count(), 8)):
                    item = locs.nth(i)
                    try:
                        if item.is_visible():
                            item.click(timeout=2500)
                            return True
                    except Exception:  # noqa: BLE001
                        continue
            # 通用兜底：点击第一个「以城市名开头」的可见叶子节点
            return bool(page.evaluate(
                """(city) => {
                    const els = document.querySelectorAll('div, li, span, p');
                    for (const el of els) {
                        if (el.offsetParent === null) continue;
                        const t = (el.innerText || '').trim();
                        if (t.startsWith(city) && t.length < 30 && !el.children.length) {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                city,
            ))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _close_city_picker(page) -> None:
        """关闭残留的城市选择器：Escape → 输入框失焦（不能点页面左上角，会命中携程 logo 跳页）。"""
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.evaluate("document.activeElement && document.activeElement.blur();")
            page.wait_for_timeout(200)
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
        # 同一订单重复下单（幂等复用）时，先关闭并清理旧会话
        with self._lock:
            old_q = self._session_queues.pop(order.order_no, None)
        if old_q is not None:
            old_fut: concurrent.futures.Future = concurrent.futures.Future()
            old_q.put(("close", old_fut, lambda: self._cleanup_session(order.order_no)))
            old_fut.result(timeout=15)
        self._sessions.pop(order.order_no, None)
        self._sessions[order.order_no] = {"pw": pw, "context": context, "page": page}
        with self._lock:
            self._session_queues[order.order_no] = queue.Queue()
        return path

    async def check_paid(self, order_no: str) -> bool:
        """第 1 层：页面变化检测——Mock 收银台出现「支付成功」元素。"""
        with self._lock:
            session = self._sessions.get(order_no)
        if session is None:
            return False
        fut = self._submit_session(order_no, "check", lambda: self._check_paid_sync(session))
        try:
            return bool(await asyncio.wrap_future(fut))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _check_paid_sync(session: dict) -> bool:
        try:
            # 元素常驻但默认隐藏（display:none），支付成功后才可见，因此只统计可见元素
            return session["page"].locator("#pay-success:visible").count() > 0
        except Exception as e:  # noqa: BLE001
            log.warning("第1层页面检测异常: %s", e)
            return False

    async def close(self, order_no: str):
        with self._lock:
            q = self._session_queues.pop(order_no, None)
        if q is None:
            return
        fut: concurrent.futures.Future = concurrent.futures.Future()
        q.put(("close", fut, lambda: self._cleanup_session(order_no)))
        await asyncio.wrap_future(fut)

    async def close_all(self):
        for order_no in list(self._session_queues):
            await self.close(order_no)


browser_order = BrowserOrderService()

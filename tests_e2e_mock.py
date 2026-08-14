"""端到端 Mock 测试：Playwright 下单 + 三层支付检测 + 微信 Mock 桥。
运行：D:\\tool\\anaconda\\python.exe tests_e2e_mock.py（自动起 8096 实例，全部模拟数据）
"""

import asyncio
import os
import sys

os.environ["TRAVEL_MOCK_CHECKOUT_BASE_URL"] = "http://127.0.0.1:8096"
os.environ["TRAVEL_MOCK_CHECKOUT_AUTO_PAY_SECONDS"] = "4"
os.environ["TRAVEL_PAYMENT_POLL_SECONDS_FAST"] = "1"
os.environ["TRAVEL_PAYMENT_POLL_SECONDS_SLOW"] = "1"
os.environ["TRAVEL_PAYMENT_MONITOR_TIMEOUT"] = "60"
os.environ["TRAVEL_CTRIP_REAL_ENABLED"] = "false"  # 端到端测试固定走 Mock 收银台，避免启动真实浏览器
sys.path.insert(0, r"E:\tmp\diet-agent\order-agent")

import uvicorn  # noqa: E402
import httpx  # noqa: E402

from app.main import app  # noqa: E402

PORT = 8096


async def wait_server_ready(client: httpx.AsyncClient, timeout: float = 30.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            r = await client.get("/mock/checkout.html", timeout=3)
            if r.status_code == 200:
                return True
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.5)
    return False


async def create_real_order():
    """按真实链路创建订单草稿 + book 任务，返回 (order, task_id)。"""
    from app.crud import order as order_crud
    from app.database import async_session_maker
    from app.models.schemas import PlanOption, TransportLeg
    from app.services.runtime import booking, task_service

    plan = PlanOption(
        plan_id=f"pwtest{int(asyncio.get_event_loop().time())}",
        legs=[TransportLeg(
            leg_no=1, mode="TRAIN", from_city="\u5317\u4eac", to_city="\u4e0a\u6d77",
            from_station="\u5317\u4eac\u5357", to_station="\u4e0a\u6d77\u8679\u6865",
            arrive_day=1, depart="09:00", arrive="13:00", price=288.0,
            vehicle_no="G1", seat="\u4e8c\u7b49\u5ea7",
        )],
        total_price=288.0, total_duration_h=4.0, score=0.9,
    )
    async with async_session_maker() as db:
        order = await booking.create_order_draft(
            db, 1, plan,
            passengers=[{"name": "\u6f14\u793a\u4e58\u5ba2", "id_type": "\u8eab\u4efd\u8bc1", "id_no": "110101199001011234"}],
            channel="web", trip_id=None,
        )
        task_id = await task_service.create(
            db, 1, "book", {"plan_id": "1", "order_no": order.order_no}, channel="web", order_id=order.id,
        )
        await order_crud.update_order(db, order.id, task_id=task_id)
        return order, task_id


async def main() -> int:
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())
    failed = 0

    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=30) as client:
        if not await wait_server_ready(client):
            print("FAIL: server not ready")
            server.should_exit = True
            await server_task
            return 1
        print("OK: mock server ready")

        # ---------- 1) 真实链路：建单 + Playwright 下单 + 二维码截图 ----------
        from app.database import async_session_maker
        from app.models.enums import Channel, Intent, SessionPhase
        from app.models.schemas import SessionState, TravelSlotBundle
        from app.services.browser import browser_order
        from app.services.mock_supplier import mock_supplier
        from app.services.runtime import orchestrator, task_service

        order, task_id = await create_real_order()
        print("order created:", order.order_no)

        from app.services.runtime import booking

        # execute_booking 在独立协程里跑（模拟 orchestrator 的后台任务）
        async def run_booking():
            async with async_session_maker() as db:
                return await booking.execute_booking(db, task_id, order)

        bk = asyncio.create_task(run_booking())
        await asyncio.sleep(2)

        # 启动三层支付检测监控（对应 orchestrator._handle_book 里的 spawn）
        state = SessionState(
            sessionId="web:1", userId=1, phase=SessionPhase.BOOKING, channel=Channel.web,
            currentIntent=Intent.PLAN_BOOK,
            slots=TravelSlotBundle(destination=["\u4e0a\u6d77"], tripDate=["2026-08-13"]),
            orderId=order.id, orderNo=order.order_no,
        )
        monitor = asyncio.create_task(orchestrator._payment_monitor(1, order, state))

        # 等待二维码生成（Playwright）
        qr_path = ""
        for _ in range(20):
            await asyncio.sleep(1)
            try:
                r = await client.get("/api/v1/travel/tasks/" + task_id, timeout=5)
                res = r.json()
                qr_path = (res.get("result") or {}).get("qr_image_path") or ""
                if qr_path and os.path.exists(qr_path):
                    break
            except Exception:  # noqa: BLE001
                pass
        print("QR via Playwright:", os.path.basename(qr_path) if qr_path else "NONE",
              "exists:", bool(qr_path and os.path.exists(qr_path)))
        if not (qr_path and os.path.exists(qr_path)):
            print("FAIL: Playwright QR not produced")
            failed += 1

        # 等待三层检测 → PAID
        paid = False
        for _ in range(30):
            await asyncio.sleep(1)
            async with async_session_maker() as db:
                from app.crud import order as order_crud
                cur = await order_crud.get_order_by_no(db, 1, order.order_no)
                if cur and cur.status == "PAID":
                    paid = True
                    break
        print("order status after payment monitor:", "PAID" if paid else "NOT PAID")
        if not paid:
            print("FAIL: payment detection did not mark PAID")
            failed += 1

        await bk
        await monitor
        layer1 = await browser_order.check_paid(order.order_no)
        layer2 = mock_supplier.is_paid(order.order_no)
        print("layer1(page change):", layer1, " layer2(supplier poll):", layer2)
        await browser_order.close(order.order_no)

        # 任务最终状态
        r = await client.get("/api/v1/travel/tasks/" + task_id, timeout=5)
        task_json = r.json()
        print("task status:", task_json.get("status"))
        if task_json.get("status") != "SUCCEEDED":
            print("FAIL: task not SUCCEEDED")
            failed += 1

        # ---------- 1.5) 第 3 层：用户「付好了」快捷路径 ----------
        from app.services.trace import TraceContext

        order2, task2 = await create_real_order()
        async def run_booking2():
            async with async_session_maker() as db:
                return await booking.execute_booking(db, task2, order2)

        bk2 = asyncio.create_task(run_booking2())
        await asyncio.sleep(3)  # 等二维码截图完成（不启动支付监控，保持 WAITING_USER）
        ctx3 = TraceContext("trace-layer3", "web:1", 1)
        state3 = SessionState(
            sessionId="web:1", userId=1, phase=SessionPhase.BOOKING, channel=Channel.web,
            currentIntent=Intent.PLAN_BOOK,
            slots=TravelSlotBundle(destination=["\u4e0a\u6d77"], tripDate=["2026-08-13"]),
            orderId=order2.id, orderNo=order2.order_no,
        )
        async with async_session_maker() as db:
            layer3_msg = await orchestrator._confirm_payment(db, 1, "\u4ed8\u597d\u4e86", state3, ctx3)
        print("layer3 quick-path reply:", (layer3_msg.text or "")[:50])
        async with async_session_maker() as db:
            from app.crud import order as order_crud
            cur2 = await order_crud.get_order_by_no(db, 1, order2.order_no)
            print("layer3 order status:", cur2.status if cur2 else "N/A")
            if not cur2 or cur2.status != "PAID":
                print("FAIL: layer3 quick path did not mark PAID")
                failed += 1
        await browser_order.close(order2.order_no)
        await bk2

        # ---------- 2) 微信 Mock 桥 ----------
        bind = await client.post("/api/v1/travel/webhook/wechat", json={"from": "wx_test_001", "text": "\u7ed1\u5b9a 1"})
        print("wechat bind:", bind.status_code, bind.json().get("reply", "")[:40])
        chat = await client.post(
            "/api/v1/travel/webhook/wechat",
            json={"from": "wx_test_001", "text": "\u67e5\u8ba2\u5355"},
        )
        print("wechat chat:", chat.status_code, chat.json().get("reply", "")[:60])
        outbox = await client.get("/api/v1/travel/debug/wechat/messages?from=wx_test_001")
        rows = outbox.json().get("messages", [])
        print("wechat outbox count:", len(rows), "last:", (rows[-1].get("text", "") if rows else "")[:60])
        if bind.status_code != 200 or chat.status_code != 200 or not rows:
            print("FAIL: wechat mock bridge")
            failed += 1

        # ---------- 3) Mock 供应商状态接口 ----------
        st = await client.get(f"/api/v1/travel/mock-supplier/orders/{order.order_no}/status")
        print("mock supplier status:", st.json())

    server.should_exit = True
    await server_task
    print("RESULT:", "PASS" if failed == 0 else f"FAIL({failed})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

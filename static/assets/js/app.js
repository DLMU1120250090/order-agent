(function () {
    "use strict";
    const app = document.getElementById("app");
    const toast = document.getElementById("toast");
    const userIdInput = document.getElementById("userIdInput");
    const SLOT_LABELS = {
        destination: "目的地",
        tripDate: "出行日期",
        budget: "预算档位",
        travelStyle: "出行风格",
        transportMode: "交通方式",
        companion: "同行人"
    };
    const INTENTS = [
        "PLAN_RECOMMENDATION",
        "CLARIFY_NEEDED",
        "PLAN_ADJUST",
        "PLAN_BOOK",
        "ORDER_QUERY",
        "ORDER_CHANGE",
        "ORDER_CANCEL",
        "PRICE_MONITOR",
        "CHECKLIST_EXPORT",
        "OTHER"
    ];
    const QUICK_QUESTIONS = [
        "帮我规划下周三去成都，经济型",
        "换一批",
        "就订第一个",
        "付好了",
        "查订单",
        "帮我改到周五",
        "确认改签",
        "把这张票退了吧",
        "确认退票",
        "给我列个出行清单"
    ];
    const state = {
        home: { loaded: false, orderCount: 0, profileReady: false },
        chat: {
            sessionId: null,
            sending: false,
            sseOn: false,
            restored: false,
            messages: [
                {
                    role: "assistant",
                    text: "你好，我是出行规划与预订助手。告诉我目的地和日期，我可以帮你规划行程、下单、查订单、改签或退票。试试问：帮我规划下周三去成都"
                }
            ]
        },
        orders: { rows: [], selected: null, loading: false },
        profile: { data: null, loading: false, saving: false },
        traces: {
            rows: [],
            selected: null,
            loading: false,
            filters: defaultTraceFilters()
        },
        evaluation: {
            report: null,
            loading: false,
            form: defaultRangeForm()
        }
    };
    let sseSource = null;

    function defaultRangeForm() {
        const end = new Date();
        const start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
        return {
            startAt: toLocalInputValue(start),
            endAt: toLocalInputValue(end),
            limit: 50,
            includeLlmJudge: false
        };
    }
    function defaultTraceFilters() {
        const range = defaultRangeForm();
        return {
            startAt: range.startAt,
            endAt: range.endAt,
            onlyUnlabeled: false,
            limit: 50,
            sessionId: ""
        };
    }
    function toLocalInputValue(date) {
        const pad = (value) => String(value).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }
    // datetime-local 的输入按浏览器本地时区解析，转成 UTC ISO 后提交（后端 trace/评估按 UTC 存储）
    function toUtcIso(localInput) {
        if (!localInput) {
            return "";
        }
        const d = new Date(localInput);
        return isNaN(d.getTime()) ? localInput : d.toISOString();
    }
    // 后端返回的 UTC 时间（无时区后缀）转成本地时间展示
    function formatLocalTime(utcValue) {
        if (!utcValue) {
            return "-";
        }
        const raw = String(utcValue).replace(" ", "T");
        const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(raw) ? raw : raw + "Z");
        if (isNaN(d.getTime())) {
            return String(utcValue);
        }
        return d.toLocaleString("zh-CN", { hour12: false });
    }
    // 会话持久化：按 userId 记住 sessionId，刷新后恢复同一会话与历史
    function defaultSessionId() {
        // Web 默认走稳定会话 web:<userId>，刷新后仍是同一个对话（与钉钉一致）
        return `web:${TravelApi.getUserId()}`;
    }
    function chatSessionKey() {
        return `travel.chat.sessionId.${TravelApi.getUserId()}`;
    }
    function loadSavedSessionId() {
        return localStorage.getItem(chatSessionKey()) || "";
    }
    function saveSessionId(sessionId) {
        if (sessionId) {
            localStorage.setItem(chatSessionKey(), sessionId);
        } else {
            localStorage.removeItem(chatSessionKey());
        }
    }
    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }
    function safeJson(value) {
        if (value === null || value === undefined || value === "") {
            return "";
        }
        try {
            const parsed = typeof value === "string" ? JSON.parse(value) : value;
            return JSON.stringify(parsed, null, 2);
        } catch (error) {
            return String(value);
        }
    }
    function showToast(message, type) {
        toast.textContent = message;
        toast.className = `toast show ${type === "error" ? "error" : ""}`;
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.className = "toast";
        }, 3200);
    }
    function setLoading(button, loadingText) {
        if (!button) {
            return () => {};
        }
        const oldText = button.textContent;
        button.disabled = true;
        button.textContent = loadingText || "处理中...";
        return () => {
            button.disabled = false;
            button.textContent = oldText;
        };
    }
    async function guard(action, successMessage) {
        try {
            const result = await action();
            if (successMessage) {
                showToast(successMessage);
            }
            return result;
        } catch (error) {
            showToast(error.message || "操作失败", "error");
            throw error;
        }
    }
    function currentRoute() {
        return (location.hash || "#/travel").slice(1).split("?")[0] || "/travel";
    }
    function navigate(route) {
        location.hash = route;
    }
    function setActiveNav(route) {
        document.querySelectorAll("[data-nav]").forEach((item) => {
            item.classList.toggle("active", item.dataset.nav === route);
        });
    }
    function toMediaUrl(path) {
        if (!path) {
            return "";
        }
        const marker = "memory";
        const idx = path.indexOf(marker);
        const rel = idx >= 0 ? path.slice(idx).replaceAll("\\", "/") : path.replaceAll("\\", "/");
        return `/media/${rel.startsWith("memory/") ? rel.slice("memory/".length) : rel}`;
    }
    function render() {
        const route = currentRoute();
        setActiveNav(route);
        if (route === "/travel") {
            renderHome();
        } else if (route === "/travel/chat") {
            if (!state.chat.restored) {
                state.chat.restored = true;
                restoreChat();
            } else {
                renderChat();
            }
        } else if (route === "/travel/orders") {
            renderOrders();
        } else if (route === "/travel/profile") {
            renderProfile();
        } else if (route === "/admin/traces") {
            renderTraces();
        } else if (route === "/admin/evaluations") {
            renderEvaluations();
        } else {
            navigate("/travel");
        }
        app.focus({ preventScroll: true });
    }

    // ---------------- 首页 ----------------
    function renderHome() {
        app.innerHTML = `
            <section class="hero">
                <div class="hero-panel">
                    <span class="badge">出行规划与预订 Agent</span>
                    <h1>规划、下单、改签、退票，一趟说走就走的旅行</h1>
                    <p>告诉助手目的地和日期，约束求解生成 Top3 出行方案；确认后一键下单（Mock 供应商），支持查订单、改签决策与退票，出发前还有清单和天气提醒。</p>
                    <div class="hero-actions">
                        <a class="btn primary" href="#/travel/chat">开始规划出行</a>
                        <a class="btn soft" href="#/travel/orders">查看我的订单</a>
                        <a class="btn ghost" href="#/admin/traces">查看 Trace</a>
                    </div>
                </div>
                <aside class="grid stats">
                    ${statCard("我的订单", state.home.loaded ? state.home.orderCount : "加载中", "已落库的出行订单（Mock 供应商）")}
                    ${statCard("用户画像", state.home.loaded ? (state.home.profileReady ? "已建立" : "未建立") : "加载中", "常驻城市 / 预算档位 / 偏好（L1 记忆）")}
                    ${statCard("当前用户", TravelApi.getUserId(), "所有请求会带上 X-User-Id")}
                </aside>
            </section>
            <section class="grid three" style="margin-top: 18px;">
                ${featureCard("出行聊天", "自然语言规划行程，页面展示方案卡片、澄清追问与订单进度。", "#/travel/chat")}
                ${featureCard("订单管理", "查看订单状态机（PAID/CHANGED/REFUNDED），支持改签与退票决策。", "#/travel/orders")}
                ${featureCard("评测后台", "查看请求 Trace，标注预期结果，并生成带出行指标的批量评估报告。", "#/admin/evaluations")}
            </section>
        `;
        loadHomeStats();
    }
    function statCard(label, value, desc) {
        return `
            <div class="stat-card">
                <span class="muted">${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
                <p class="muted">${escapeHtml(desc)}</p>
            </div>
        `;
    }
    function featureCard(title, desc, href) {
        return `
            <article class="card">
                <div class="card-title">
                    <div>
                        <h3>${escapeHtml(title)}</h3>
                        <p>${escapeHtml(desc)}</p>
                    </div>
                </div>
                <a class="btn soft" href="${href}">进入</a>
            </article>
        `;
    }
    async function loadHomeStats() {
        if (state.home.loaded) {
            return;
        }
        try {
            const [orders, profile] = await Promise.all([
                TravelApi.listOrders().catch(() => []),
                TravelApi.getProfile().catch(() => null)
            ]);
            state.home = {
                loaded: true,
                orderCount: Array.isArray(orders) ? orders.length : 0,
                profileReady: !!(profile && (profile.homeCity || profile.budgetLevel || (profile.preferences && Object.keys(profile.preferences).length)))
            };
            if (currentRoute() === "/travel") {
                renderHome();
            }
        } catch (error) {
            showToast(error.message || "首页数据加载失败", "error");
        }
    }

    // ---------------- 出行聊天 ----------------
    async function restoreChat() {
        const candidates = [];
        const saved = loadSavedSessionId();
        if (saved) {
            candidates.push(saved);
        }
        try {
            const latest = await TravelApi.latestSession();
            if (latest && latest.sessionId && !candidates.includes(latest.sessionId)) {
                candidates.push(latest.sessionId);
            }
        } catch (error) {
            // 忽略：继续走稳定会话兜底
        }
        candidates.push(defaultSessionId());

        for (const sessionId of candidates) {
            if (!sessionId) {
                continue;
            }
            state.chat.sessionId = sessionId;
            try {
                const history = await TravelApi.sessionMessages(sessionId, 50);
                if (Array.isArray(history) && history.length) {
                    saveSessionId(sessionId);
                    state.chat.messages = history.map((m) => ({
                        role: m.role === "user" ? "user" : "assistant",
                        text: m.content || "",
                        intent: m.intent || null,
                        sessionId: sessionId
                    }));
                    renderChat();
                    return;
                }
            } catch (error) {
                // 历史读取失败按新会话处理，避免阻塞页面
            }
        }
        state.chat.sessionId = defaultSessionId();
        saveSessionId(state.chat.sessionId);
        state.chat.messages = [{
            role: "assistant",
            text: "你好，我是出行规划与预订助手。告诉我目的地和日期，我可以帮你规划行程、下单、查订单、改签或退票。试试问：帮我规划下周三去成都"
        }];
        renderChat();
    }
    function renderChat() {
        app.innerHTML = `
            <section class="chat-layout">
                <div class="section chat-window">
                    <div class="card-title">
                        <div>
                            <h2>出行聊天</h2>
                            <p>当前会话：${state.chat.sessionId ? escapeHtml(state.chat.sessionId) : "尚未创建，发送消息时自动创建"}</p>
                        </div>
                        <div class="inline-actions">
                            <button class="btn ghost" data-action="new-session">新会话</button>
                        </div>
                    </div>
                    <div id="messages" class="messages">${state.chat.messages.map(renderMessage).join("")}</div>
                    <form id="chatForm" class="composer">
                        <textarea name="message" placeholder="例如：帮我规划下周三去成都，经济型" required></textarea>
                        <button class="btn primary" type="submit">${state.chat.sending ? "发送中..." : "发送"}</button>
                    </form>
                </div>
                <aside class="grid">
                    <div class="card">
                        <div class="card-title">
                            <div>
                                <h3>快捷问题</h3>
                                <p>点击后可直接填入输入框。</p>
                            </div>
                        </div>
                        <div class="chips">
                            ${QUICK_QUESTIONS.map((text) => `<button class="chip" data-action="quick-message" data-message="${escapeHtml(text)}">${escapeHtml(text)}</button>`).join("")}
                        </div>
                    </div>
                    <div class="card">
                        <h3>演示提示</h3>
                        <p class="muted">流程：规划方案 → 回复"就订第一个" → 收到二维码（模拟）→ 回复"付好了" → 已出票 → 查订单 / 改签 / 退票。资金操作必须本人确认，Agent 绝不代付。</p>
                        <div class="button-row">
                            <a class="btn soft" href="#/travel/orders">我的订单</a>
                            <a class="btn ghost" href="#/travel/profile">用户画像</a>
                        </div>
                    </div>
                </aside>
            </section>
        `;
        ensureSse();
        scrollMessagesToBottom();
    }
    function renderMessage(message) {
        const cards = (message.blocks || []).map((block) => renderBlockCard(block, message)).join("");
        const missingSlots = message.missingSlots && message.missingSlots.length
            ? `<div class="chips">${message.missingSlots.map((slot) => `<span class="chip selected">${escapeHtml(SLOT_LABELS[slot] || slot)}</span>`).join("")}</div>`
            : "";
        const image = message.imageUrl
            ? `<img src="${escapeHtml(message.imageUrl)}" alt="支付二维码" style="max-width:180px;border-radius:12px;border:1px solid var(--border)">`
            : "";
        const task = message.taskId
            ? `<div class="message-meta">任务：${escapeHtml(message.taskId)}${message.taskStatus ? ` · ${escapeHtml(message.taskStatus)}` : ""}</div>`
            : "";
        const trace = message.traceId
            ? `<span>traceId：<a href="#/admin/traces" data-action="open-trace" data-trace-id="${escapeHtml(message.traceId)}">${escapeHtml(message.traceId)}</a></span>`
            : "";
        return `
            <article class="message ${message.role}">
                <div class="bubble">${escapeHtml(message.text)}</div>
                ${image}
                ${missingSlots}
                ${cards ? `<div class="grid">${cards}</div>` : ""}
                ${(task || trace) ? `<div class="message-meta">${task}${trace}</div>` : ""}
            </article>
        `;
    }
    function renderBlockCard(block, message) {
        if (block.planId !== undefined && block.planId !== null) {
            const legs = (block.legs || []).map((leg) => {
                const mode = leg.mode === "FLIGHT" ? "✈️" : leg.mode === "TRAIN" ? "🚄" : "🚌";
                return `${mode} ${escapeHtml(leg.from_city)} ${escapeHtml(leg.depart)} → ${escapeHtml(leg.to_city)} ${escapeHtml(leg.arrive)}（${escapeHtml(leg.vehicle_no || "-")}）`;
            }).join("<br>");
            return `
                <article class="meal-card">
                    <header>
                        <div>
                            <h3>方案 ${escapeHtml(block.planNo ?? block.planId)}</h3>
                            <p class="muted">总价 ¥${Number(block.totalPrice ?? 0).toFixed(0)} · 耗时 ${escapeHtml(block.totalDurationH ?? "-")}h</p>
                        </div>
                        ${block.score ? `<span class="score">评分 ${Number(block.score).toFixed(2)}</span>` : ""}
                    </header>
                    <div>${legs}</div>
                    <div class="button-row">
                        <button class="btn soft" data-action="feedback" data-action-value="LIKE" data-plan-id="${escapeHtml(block.planId)}" data-session-id="${escapeHtml(message.sessionId || "")}">采纳</button>
                        <button class="btn ghost" data-action="feedback" data-action-value="DISLIKE" data-plan-id="${escapeHtml(block.planId)}" data-session-id="${escapeHtml(message.sessionId || "")}">不采纳</button>
                    </div>
                </article>
            `;
        }
        if (block.orderNo) {
            return `
                <article class="meal-card">
                    <header>
                        <div>
                            <h3>订单 ${escapeHtml(block.orderNo)}</h3>
                            <p class="muted">${escapeHtml(block.type || "-")} · ${escapeHtml(block.status || "-")} · ¥${Number(block.price ?? 0).toFixed(0)}</p>
                        </div>
                    </header>
                </article>
            `;
        }
        return `<article class="meal-card"><pre class="json-box">${escapeHtml(safeJson(block))}</pre></article>`;
    }
    function scrollMessagesToBottom() {
        const messages = document.getElementById("messages");
        if (messages) {
            messages.scrollTop = messages.scrollHeight;
        }
    }
    function ensureSse() {
        if (sseSource || state.chat.sseOn) {
            return;
        }
        state.chat.sseOn = true;
        sseSource = new EventSource(TravelApi.eventsUrl());
        sseSource.onmessage = (event) => {
            try {
                const payload = JSON.parse(event.data);
                if (!payload || (!payload.text && !payload.taskProgress)) {
                    return;
                }
                state.chat.messages.push({
                    role: "assistant",
                    text: payload.text || `任务进度：${payload.taskProgress.status} ${payload.taskProgress.progress}%`,
                    taskId: payload.taskProgress ? payload.taskProgress.taskId : null,
                    taskStatus: payload.taskProgress ? payload.taskProgress.status : null,
                    imageUrl: payload.imagePath ? toMediaUrl(payload.imagePath) : null,
                    blocks: payload.blocks || []
                });
                if (currentRoute() === "/travel/chat") {
                    renderChat();
                }
            } catch (error) {
                // 忽略非 JSON 心跳
            }
        };
        sseSource.onerror = () => {
            // 服务端可能断开，自动重连由 EventSource 处理
        };
    }
    async function submitChat(form) {
        const messageInput = form.elements.message;
        const message = messageInput.value.trim();
        if (!message || state.chat.sending) {
            return;
        }
        state.chat.messages.push({ role: "user", text: message });
        messageInput.value = "";
        state.chat.sending = true;
        renderChat();
        try {
            if (!state.chat.sessionId) {
                state.chat.sessionId = defaultSessionId();
                saveSessionId(state.chat.sessionId);
            }
            const response = await TravelApi.chat({
                sessionId: state.chat.sessionId,
                message
            });
            state.chat.sessionId = response.sessionId || state.chat.sessionId;
            saveSessionId(state.chat.sessionId);
            const assistant = {
                role: "assistant",
                text: response.clarifyQuestion || response.speechText || "我已经处理完这轮请求。",
                responseType: response.responseType,
                blocks: response.displayBlocks || [],
                missingSlots: response.missingSlots || [],
                traceId: response.traceId,
                taskId: response.taskId || null,
                taskStatus: response.responseType === "TASK_PROGRESS" ? "RUNNING" : null,
                sessionId: response.sessionId || state.chat.sessionId
            };
            state.chat.messages.push(assistant);
            if (response.taskId) {
                fetchTaskProgress(response.taskId, assistant);
            }
        } catch (error) {
            showToast(error.message || "聊天请求失败", "error");
            state.chat.messages.push({ role: "assistant", text: "这轮请求失败了，请稍后重试。" });
        } finally {
            state.chat.sending = false;
            renderChat();
        }
    }
    async function fetchTaskProgress(taskId, assistant) {
        try {
            const task = await TravelApi.getTask(taskId);
            assistant.taskStatus = task.status;
            if (task.result && task.result.qr_image_path) {
                assistant.imageUrl = toMediaUrl(task.result.qr_image_path);
                assistant.text += "\n\n（支付二维码已生成，请本人扫码支付，Agent 绝不代付。支付后回复“付好了”）";
            }
            if (currentRoute() === "/travel/chat") {
                renderChat();
            }
        } catch (error) {
            // 任务查询失败不影响主流程
        }
    }
    async function resetChat() {
        state.chat.sessionId = null;
        state.chat.messages = [
            {
                role: "assistant",
                text: "已开启新会话。告诉我目的地和日期，我来规划出行方案。"
            }
        ];
        try {
            const session = await TravelApi.createSession();
            state.chat.sessionId = session.sessionId;
            saveSessionId(state.chat.sessionId);
        } catch (error) {
            saveSessionId("");
        }
        if (currentRoute() === "/travel/chat") {
            renderChat();
        }
    }

    // ---------------- 订单 ----------------
    function renderOrders() {
        app.innerHTML = `
            <section class="section">
                <div class="card-title">
                    <div>
                        <h2>我的订单</h2>
                        <p>订单状态机：DRAFT → CONFIRMED → BOOKING → PAID；改签 CHANGING → CHANGED；退票 REFUNDING → REFUNDED。</p>
                    </div>
                    <button class="btn primary" data-action="refresh-orders">${state.orders.loading ? "刷新中..." : "刷新"}</button>
                </div>
                ${renderOrderTable()}
            </section>
        `;
        if (!state.orders.rows.length && !state.orders.loading) {
            loadOrders();
        }
    }
    function renderOrderTable() {
        if (!state.orders.rows.length) {
            return `<div class="empty">暂无订单。先去聊天页规划并下一单吧。</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>订单号</th>
                            <th>类型</th>
                            <th>状态</th>
                            <th>价格</th>
                            <th>行程</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.orders.rows.map((row) => {
                            const legs = (row.legs || []).map((l) => `${l.from_city}${l.depart}→${l.to_city}`).join("；") || "-";
                            return `
                                <tr>
                                    <td>${escapeHtml(row.order_no)}</td>
                                    <td>${escapeHtml(row.type)}</td>
                                    <td>${escapeHtml(row.status)}</td>
                                    <td>¥${Number(row.price ?? 0).toFixed(0)}</td>
                                    <td>${escapeHtml(legs)}</td>
                                    <td><button class="btn soft" data-action="select-order" data-order-no="${escapeHtml(row.order_no)}">详情</button></td>
                                </tr>
                            `;
                        }).join("")}
                    </tbody>
                </table>
            </div>
            ${state.orders.selected ? renderOrderDetail(state.orders.selected) : ""}
        `;
    }
    function renderOrderDetail(order) {
        return `
            <div class="subtle-divider"></div>
            <div class="card-title">
                <div>
                    <h3>订单详情</h3>
                    <p>${escapeHtml(order.order_no)}</p>
                </div>
            </div>
            <pre class="json-box">${escapeHtml(safeJson(order))}</pre>
        `;
    }
    async function loadOrders() {
        state.orders.loading = true;
        renderOrders();
        try {
            state.orders.rows = await TravelApi.listOrders();
            state.home.loaded = false;
        } catch (error) {
            showToast(error.message || "订单加载失败", "error");
        } finally {
            state.orders.loading = false;
            renderOrders();
        }
    }
    async function selectOrder(orderNo) {
        await guard(async () => {
            state.orders.selected = await TravelApi.getOrder(orderNo);
            renderOrders();
        });
    }

    // ---------------- 用户画像 ----------------
    function renderProfile() {
        const data = state.profile.data;
        app.innerHTML = `
            <section class="split">
                <div class="section">
                    <div class="card-title">
                        <div>
                            <h2>用户画像（L1）</h2>
                            <p>常驻城市 / 预算档位 / 乘客 / 偏好。规则确定性写入，规划、下单预填与决策都会注入。</p>
                        </div>
                    </div>
                    ${data ? renderProfileForm(data) : `<div class="empty">暂无画像数据。完成一次下单后会自动写入，或点击"加载画像"。</div>`}
                </div>
                <div class="section">
                    <h3>写入时机</h3>
                    <p class="muted">下单成功 → passengers / home_city；确认出发地 → home_city；LIKE / DISLIKE → preferences 微调；用户主动纠正 &gt; 记忆。</p>
                    <h3 style="margin-top:18px;">偏好键（起步）</h3>
                    <p class="muted">cost_vs_time / tolerate_change / preferred_transport / seat_pref / early_bird / price_monitor</p>
                </div>
            </section>
        `;
        if (!data && !state.profile.loading) {
            loadProfile(false);
        }
    }
    function renderProfileForm(data) {
        // 后端 GET /profiles 返回 snake_case（home_city / budget_level），兼容两种命名
        const homeCity = data.home_city || data.homeCity || "";
        const budgetLevel = data.budget_level || data.budgetLevel || "";
        const prefs = JSON.stringify(data.preferences || {}, null, 2);
        return `
            <form id="profileForm" class="form-grid">
                <div class="field">
                    <label for="homeCity">常驻城市</label>
                    <input id="homeCity" name="homeCity" value="${escapeHtml(homeCity)}" placeholder="例如：北京">
                </div>
                <div class="field">
                    <label for="budgetLevel">预算档位</label>
                    <select id="budgetLevel" name="budgetLevel">
                        <option value="">未设置</option>
                        <option value="economy" ${budgetLevel === "economy" ? "selected" : ""}>经济型 economy</option>
                        <option value="comfort" ${budgetLevel === "comfort" ? "selected" : ""}>舒适型 comfort</option>
                        <option value="premium" ${budgetLevel === "premium" ? "selected" : ""}>高端型 premium</option>
                    </select>
                </div>
                <div class="field full">
                    <label for="preferences">偏好 JSON</label>
                    <textarea id="preferences" name="preferences" style="min-height:150px">${escapeHtml(prefs)}</textarea>
                </div>
                <div class="field full">
                    <button class="btn primary" type="submit">${state.profile.saving ? "保存中..." : "保存画像"}</button>
                </div>
            </form>
        `;
    }
    async function loadProfile(notify) {
        state.profile.loading = true;
        renderProfile();
        try {
            state.profile.data = await TravelApi.getProfile().catch(() => null);
            state.home.loaded = false;
        } catch (error) {
            showToast(error.message || "画像加载失败", "error");
        } finally {
            state.profile.loading = false;
            renderProfile();
            if (notify) {
                showToast(state.profile.data ? "画像已刷新" : "暂无画像数据");
            }
        }
    }
    async function saveProfile(form) {
        const formData = new FormData(form);
        let preferences = {};
        const raw = formData.get("preferences").trim();
        if (raw) {
            try {
                preferences = JSON.parse(raw);
            } catch (error) {
                showToast("偏好必须是合法 JSON", "error");
                return;
            }
        }
        state.profile.saving = true;
        renderProfile();
        try {
            state.profile.data = await TravelApi.updateProfile({
                homeCity: formData.get("homeCity").trim() || null,
                budgetLevel: formData.get("budgetLevel") || null,
                preferences
            });
            state.home.loaded = false;
            showToast("画像已保存");
        } catch (error) {
            showToast(error.message || "画像保存失败", "error");
        } finally {
            state.profile.saving = false;
            renderProfile();
        }
    }

    // ---------------- Trace / 评估（沿用原逻辑，适配 travel 接口） ----------------
    function renderTraces() {
        const selected = state.traces.selected;
        app.innerHTML = `
            <div class="grid">
                <section class="section">
                    <div class="card-title">
                        <div>
                            <h2>Trace 调试</h2>
                            <p>按时间范围或会话查询请求链路，查看意图修正、槽位、规划与下单事件。</p>
                        </div>
                    </div>
                    <form id="traceFilterForm" class="form-grid">
                        <div class="field">
                            <label>开始时间</label>
                            <input type="datetime-local" name="startAt" value="${escapeHtml(state.traces.filters.startAt)}" required>
                        </div>
                        <div class="field">
                            <label>结束时间</label>
                            <input type="datetime-local" name="endAt" value="${escapeHtml(state.traces.filters.endAt)}" required>
                        </div>
                        <div class="field">
                            <label>会话 ID（可选）</label>
                            <input name="sessionId" value="${escapeHtml(state.traces.filters.sessionId)}" placeholder="填写后按会话查询">
                        </div>
                        <div class="field">
                            <label>数量上限</label>
                            <input type="number" min="1" max="500" name="limit" value="${escapeHtml(state.traces.filters.limit)}">
                        </div>
                        <div class="field">
                            <label>标注状态</label>
                            <select name="onlyUnlabeled">
                                <option value="false" ${!state.traces.filters.onlyUnlabeled ? "selected" : ""}>全部</option>
                                <option value="true" ${state.traces.filters.onlyUnlabeled ? "selected" : ""}>仅未标注</option>
                            </select>
                        </div>
                        <div class="field">
                            <span>&nbsp;</span>
                            <button class="btn primary" type="submit">${state.traces.loading ? "查询中..." : "查询 Trace"}</button>
                        </div>
                    </form>
                    <div class="subtle-divider"></div>
                    ${renderTraceTable()}
                </section>
                <section class="section">
                    ${selected ? renderTraceDetail(selected) : `<div class="empty">选择一条 Trace 查看详情和标注表单。</div>`}
                </section>
            </div>
        `;
    }
    function renderTraceTable() {
        if (!state.traces.rows.length) {
            return `<div class="empty">暂无 Trace 数据。可以先在聊天页发起几轮对话。</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Trace ID</th>
                            <th>会话</th>
                            <th>状态</th>
                            <th>事件</th>
                            <th>耗时</th>
                            <th>创建时间</th>
                            <th>标注</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${state.traces.rows.map((row) => `
                            <tr>
                                <td>${escapeHtml(row.traceId)}</td>
                                <td>${escapeHtml(row.sessionId)}</td>
                                <td>${escapeHtml(row.status || "-")}</td>
                                <td>${escapeHtml(row.eventCount ?? "-")}</td>
                                <td>${row.durationMs ? `${escapeHtml(row.durationMs)} ms` : "-"}</td>
                                <td>${escapeHtml(formatLocalTime(row.createdAt))}</td>
                                <td>${row.expectedIntent ? `<span class="badge">${escapeHtml(row.expectedIntent)}</span>` : "<span class=\"muted\">未标注</span>"}</td>
                                <td><button class="btn soft" data-action="select-trace" data-trace-id="${escapeHtml(row.traceId)}">查看</button></td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }
    function renderTraceDetail(trace) {
        return `
            <div class="card-title">
                <div>
                    <h3>Trace 详情</h3>
                    <p>${escapeHtml(trace.traceId)}</p>
                </div>
            </div>
            <div class="grid">
                <div>
                    <span class="badge">${escapeHtml(trace.status || "UNKNOWN")}</span>
                    <p class="muted">Session：${escapeHtml(trace.sessionId || "-")} · Events：${escapeHtml(trace.eventCount ?? "-")} · Duration：${escapeHtml(trace.durationMs ?? "-")} ms</p>
                </div>
                <details open>
                    <summary>Trace JSON</summary>
                    <pre class="json-box">${escapeHtml(safeJson(trace.traceJson))}</pre>
                </details>
                <form id="traceLabelForm" class="form-grid">
                    <input type="hidden" name="traceId" value="${escapeHtml(trace.traceId)}">
                    <div class="field">
                        <label>预期意图</label>
                        <select name="expectedIntent">
                            <option value="">不标注</option>
                            ${INTENTS.map((intent) => `<option value="${intent}" ${trace.expectedIntent === intent ? "selected" : ""}>${intent}</option>`).join("")}
                        </select>
                    </div>
                    <div class="field">
                        <label>澄清动作</label>
                        <select name="expectedClarifyAction">
                            <option value="">不标注</option>
                            <option value="ASK" ${trace.expectedClarifyAction === "ASK" ? "selected" : ""}>ASK</option>
                            <option value="READY" ${trace.expectedClarifyAction === "READY" ? "selected" : ""}>READY</option>
                        </select>
                    </div>
                    <div class="field full">
                        <label>预期槽位 JSON</label>
                        <textarea name="expectedSlots" placeholder='{"destination":["成都"],"tripDate":["2026-08-19"]}'>${escapeHtml(safeJson(trace.expectedSlots))}</textarea>
                    </div>
                    <div class="field full">
                        <label>备注</label>
                        <textarea name="labelNote" placeholder="标注说明">${escapeHtml(trace.labelNote || "")}</textarea>
                    </div>
                    <div class="field full">
                        <button class="btn primary" type="submit">保存标注</button>
                    </div>
                </form>
            </div>
        `;
    }
    async function searchTraces(form) {
        const formData = new FormData(form);
        state.traces.filters = {
            startAt: formData.get("startAt"),
            endAt: formData.get("endAt"),
            sessionId: formData.get("sessionId").trim(),
            onlyUnlabeled: formData.get("onlyUnlabeled") === "true",
            limit: Number(formData.get("limit") || 50)
        };
        state.traces.loading = true;
        renderTraces();
        try {
            if (state.traces.filters.sessionId) {
                state.traces.rows = await TravelApi.listSessionTraces(state.traces.filters.sessionId, state.traces.filters.limit);
            } else {
                state.traces.rows = await TravelApi.listTraces({
                    startAt: toUtcIso(state.traces.filters.startAt),
                    endAt: toUtcIso(state.traces.filters.endAt),
                    onlyUnlabeled: state.traces.filters.onlyUnlabeled,
                    limit: state.traces.filters.limit
                });
            }
            state.traces.selected = state.traces.rows[0] || null;
        } catch (error) {
            showToast(error.message || "Trace 查询失败", "error");
        } finally {
            state.traces.loading = false;
            renderTraces();
        }
    }
    async function selectTrace(traceId) {
        await guard(async () => {
            state.traces.selected = await TravelApi.getTrace(traceId);
            renderTraces();
        });
    }
    async function saveTraceLabel(form) {
        const formData = new FormData(form);
        const traceId = formData.get("traceId");
        const slotsText = formData.get("expectedSlots").trim();
        let expectedSlots = null;
        if (slotsText) {
            try {
                expectedSlots = JSON.parse(slotsText);
            } catch (error) {
                showToast("预期槽位必须是合法 JSON", "error");
                return;
            }
        }
        const payload = {
            expectedIntent: formData.get("expectedIntent") || null,
            expectedSlots,
            expectedClarifyAction: formData.get("expectedClarifyAction") || null,
            labelNote: formData.get("labelNote").trim()
        };
        await guard(async () => {
            await TravelApi.labelTrace(traceId, payload);
            state.traces.selected = await TravelApi.getTrace(traceId);
            const index = state.traces.rows.findIndex((row) => row.traceId === traceId);
            if (index >= 0) {
                state.traces.rows[index] = state.traces.selected;
            }
            renderTraces();
        }, "Trace 标注已保存");
    }
    function renderEvaluations() {
        app.innerHTML = `
            <section class="section">
                <div class="card-title">
                    <div>
                        <h2>评估报告</h2>
                        <p>基于已落库 Trace 生成规则评分、可选 LLM Judge 和反馈归因指标（含 planFeasibility / bookingSuccessRate 等出行指标）。</p>
                    </div>
                </div>
                <form id="evaluationForm" class="form-grid">
                    <div class="field">
                        <label>开始时间</label>
                        <input type="datetime-local" name="startAt" value="${escapeHtml(state.evaluation.form.startAt)}" required>
                    </div>
                    <div class="field">
                        <label>结束时间</label>
                        <input type="datetime-local" name="endAt" value="${escapeHtml(state.evaluation.form.endAt)}" required>
                    </div>
                    <div class="field">
                        <label>数量上限</label>
                        <input type="number" min="1" max="500" name="limit" value="${escapeHtml(state.evaluation.form.limit)}">
                    </div>
                    <div class="field">
                        <label>LLM Judge</label>
                        <select name="includeLlmJudge">
                            <option value="false" ${!state.evaluation.form.includeLlmJudge ? "selected" : ""}>关闭</option>
                            <option value="true" ${state.evaluation.form.includeLlmJudge ? "selected" : ""}>开启</option>
                        </select>
                    </div>
                    <div class="field full">
                        <button class="btn primary" type="submit">${state.evaluation.loading ? "评估中..." : "生成评估报告"}</button>
                    </div>
                </form>
            </section>
            <section class="section" style="margin-top: 18px;">
                ${renderEvaluationReport()}
            </section>
        `;
    }
    function renderEvaluationReport() {
        const report = state.evaluation.report;
        if (!report) {
            return `<div class="empty">暂无报告。选择时间范围后生成评估。</div>`;
        }
        return `
            <div class="grid three">
                ${statCard("Trace 总数", report.totalTraces, "本次纳入评估的请求数")}
                ${statCard("已标注", report.labeledTraces, "有人工标签的 Trace 数")}
                ${statCard("平均分", report.avgScore === null || report.avgScore === undefined ? "-" : Number(report.avgScore).toFixed(2), "综合评分")}
            </div>
            <div class="subtle-divider"></div>
            <div class="grid two">
                <div>
                    <h3>指标均值</h3>
                    ${renderMetrics(report.metricAverages)}
                </div>
                <div>
                    <h3>报告范围</h3>
                    <p class="muted">${escapeHtml(report.startAt)} 至 ${escapeHtml(report.endAt)}</p>
                </div>
            </div>
            <div class="subtle-divider"></div>
            ${renderEvaluationTable(report.traceResults || [])}
        `;
    }
    function renderMetrics(metrics) {
        const entries = Object.entries(metrics || {});
        if (!entries.length) {
            return `<div class="empty">暂无指标</div>`;
        }
        return `<div class="chips">${entries.map(([key, value]) => `<span class="chip selected">${escapeHtml(key)}：${Number(value).toFixed(2)}</span>`).join("")}</div>`;
    }
    function renderEvaluationTable(rows) {
        if (!rows.length) {
            return `<div class="empty">暂无 Trace 明细</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Trace ID</th>
                            <th>会话</th>
                            <th>综合分</th>
                            <th>规则分</th>
                            <th>LLM 分</th>
                            <th>反馈分</th>
                            <th>指标 / 明细</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows.map((row) => `
                            <tr>
                                <td>${escapeHtml(row.traceId)}</td>
                                <td>${escapeHtml(row.sessionId)}</td>
                                <td>${formatScore(row.score)}</td>
                                <td>${formatScore(row.ruleScore)}</td>
                                <td>${formatScore(row.llmJudgeScore)}</td>
                                <td>${formatScore(row.userFeedbackScore)}</td>
                                <td>
                                    <details>
                                        <summary>查看 JSON</summary>
                                        <pre class="json-box">${escapeHtml(JSON.stringify({ metrics: row.metrics, detail: row.detail }, null, 2))}</pre>
                                    </details>
                                </td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }
    function formatScore(value) {
        return value === null || value === undefined ? "-" : Number(value).toFixed(2);
    }
    async function runEvaluation(form) {
        const formData = new FormData(form);
        state.evaluation.form = {
            startAt: formData.get("startAt"),
            endAt: formData.get("endAt"),
            limit: Number(formData.get("limit") || 50),
            includeLlmJudge: formData.get("includeLlmJudge") === "true"
        };
        state.evaluation.loading = true;
        renderEvaluations();
        try {
            state.evaluation.report = await TravelApi.evaluate({
                ...state.evaluation.form,
                startAt: toUtcIso(state.evaluation.form.startAt),
                endAt: toUtcIso(state.evaluation.form.endAt)
            });
        } catch (error) {
            showToast(error.message || "评估失败", "error");
        } finally {
            state.evaluation.loading = false;
            renderEvaluations();
        }
    }
    async function saveFeedback(button) {
        await guard(async () => {
            await TravelApi.saveFeedback({
                sessionId: button.dataset.sessionId || state.chat.sessionId,
                planId: button.dataset.planId || null,
                action: button.dataset.actionValue,
                rating: button.dataset.actionValue === "DISLIKE" ? 2 : 5,
                reason: ""
            });
        }, "反馈已记录");
    }
    function handleClick(event) {
        const target = event.target.closest("[data-action]");
        if (!target) {
            return;
        }
        const action = target.dataset.action;
        if (action === "new-session") {
            resetChat();
        } else if (action === "quick-message") {
            const input = document.querySelector("#chatForm textarea[name=message]");
            if (input) {
                input.value = target.dataset.message;
                input.focus();
            }
        } else if (action === "feedback") {
            saveFeedback(target);
        } else if (action === "refresh-orders") {
            loadOrders();
        } else if (action === "select-order") {
            selectOrder(target.dataset.orderNo);
        } else if (action === "select-trace") {
            selectTrace(target.dataset.traceId);
        } else if (action === "open-trace") {
            state.traces.filters.sessionId = "";
            navigate("/admin/traces");
            selectTrace(target.dataset.traceId);
        }
    }
    function handleSubmit(event) {
        const form = event.target;
        if (form.id === "chatForm") {
            event.preventDefault();
            submitChat(form);
        } else if (form.id === "profileForm") {
            event.preventDefault();
            if (!form.checkValidity()) {
                form.reportValidity();
                return;
            }
            saveProfile(form);
        } else if (form.id === "traceFilterForm") {
            event.preventDefault();
            searchTraces(form);
        } else if (form.id === "traceLabelForm") {
            event.preventDefault();
            saveTraceLabel(form);
        } else if (form.id === "evaluationForm") {
            event.preventDefault();
            runEvaluation(form);
        }
    }
    function initUserField() {
        userIdInput.value = TravelApi.setUserId(TravelApi.getUserId());
        userIdInput.addEventListener("change", () => {
            TravelApi.setUserId(userIdInput.value);
            state.home.loaded = false;
            state.orders.rows = [];
            state.traces.rows = [];
            state.traces.selected = null;
            state.chat.sessionId = null;
            state.chat.restored = false;
            state.chat.messages = [];
            showToast("用户 ID 已切换");
            render();
        });
    }
    window.addEventListener("hashchange", render);
    app.addEventListener("click", handleClick);
    app.addEventListener("submit", handleSubmit);
    initUserField();
    if (!location.hash) {
        navigate("/travel");
    } else {
        render();
    }
})();

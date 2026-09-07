# Order-Agent 出行规划与预订智能体

面向「从想法到出行」的完整决策链，基于 FastAPI + LangChain + Playwright + APScheduler 打造的动作型出行 Agent：用户一句「帮我规划下周三去成都，经济型」，即可完成方案推荐、比价下单、扫码支付、出票，以及改签退票、降价/航变监控与出发提醒。

## 功能亮点

- 多 Agent 编排：编排中枢 + 专职 Worker 分层，10 类意图 + 6 阶段状态机，资金链路由确定性编排层统一管控
- 意图识别与规则兜底：日期自然语言自由解析、词典强约束防幻觉，叠加资金安全拦截、低置信降级与关键词兜底
- 行程规划：自研约束求解器枚举直连/中转组合，按价格、耗时、时刻、偏好加权打分取 Top3，LLM 仅生成文案
- 订单与支付：幂等防重复下单，Playwright 自动化收银台 → 二维码即推，三层支付检测，全程人机确认、绝不代付
- 改签退票：可解释成本模型自动推荐损失最小方案，改签/退票/降价/航变四场景复用
- 主动服务：后台任务状态机 + 定时调度，价格监控、航变监控、出发前提醒，Web/钉钉/微信多通道推送
- 记忆驱动决策：User/Passenger 分主体（本人固定 passenger_id=0、role 只分 self/others）；多乘客下单前先确认"给谁买"；L1 画像 / L2 结构化行程与 User 行为事件 / L3 按乘客蒸馏偏好；记忆补全缺失字段需用户显式确认，相似历史进入推荐解释，降价/改签/提醒按用户偏好调节，业务规则始终把关
- 可观测与评估：全链路 Trace（含后台任务的 run/task 关联与订单状态链）落库可查；离线 Replay dry-run 回放 + Failure Taxonomy 失败分类；规则 60% + 模型评审 10% + 用户反馈 30% 按业务链路聚合评估

## 技术栈

FastAPI · LangChain · Playwright · APScheduler · MySQL/SQLModel · 钉钉开放平台 · SSE

## 快速开始

项目分为 `backend/`（FastAPI）与 `frontend/`（Vue3 + Vite），本机可用 nginx（`nginx-1.30.4/`）组合演示。

> **一键启动（本机演示）**：双击根目录 `start_services.bat`（或执行 `start_services.bat --no-browser`）。
> 脚本会启动后端（8000）与 nginx（80）；若已在运行，会先停止旧进程再重启（重复运行=重启），并打开 <http://127.0.0.1>。

### 1. 后端

```bash
cd backend
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # 填写 DEEPSEEK_API_KEY 与 DATABASE_URL
alembic upgrade head   # 建全库表结构与种子数据
```

启动：

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 2. 前端

开发模式（/api、/media 自动代理到 127.0.0.1:8000）：

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

生产构建（输出到 `backend/static`，供 nginx 直接服务）：

```bash
cd frontend
npm run build
```

### 3. nginx 生产演示（本机）

```bash
cd nginx-1.30.4
nginx -p . -c conf/nginx.conf
```

访问 <http://127.0.0.1>：80 端口提供前端静态资源，`/api`、`/media`、`/api/v1/travel/events`(SSE) 反向代理到 127.0.0.1:8000。

## 目录结构

- `backend/`：后端（app / alembic / prompts / skills / sql / replays / tests / static 等；`static/` 为前端构建产物与 Mock 收银台）
- `frontend/`：Vue3 + Vite 前端源码（构建输出到 `backend/static`）
- `nginx-1.30.4/`：本机 nginx 演示目录（本地运行，不入库；配置见 `conf/nginx.conf`）
- `README.md`：本文件

## 调试与评估

- `POST /api/v1/travel/debug/replay`：单条 Trace 规则层 dry-run 重放，返回 before/after 字段级 diff（不调 LLM、不落业务数据）
- `POST /api/v1/travel/debug/replay/cases`：按失败主题（recovery / recommendation_reject）收集回归 case 集
- `POST /api/v1/travel/evaluations`：时间范围评估，返回业务链路级指标（linkResults / totalLinks）与失败分类分布（failureDistribution）
- `POST /api/v1/travel/feedback/post-trip`：出行后评分（1~5 星），落到对应订单 Episode 的 outcome

## 说明

- 默认 `TRAVEL_MOCK_MODE=true`，外部数据 API 使用内置模拟数据；接入真实供应商时填写 `.env` 中对应密钥并关闭 Mock。
- 真实 `.env` 不纳入版本控制，请勿提交。



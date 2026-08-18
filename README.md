# Order-Agent 出行规划与预订智能体

面向「从想法到出行」的完整决策链，基于 FastAPI + LangChain + Playwright + APScheduler 打造的动作型出行 Agent：用户一句「帮我规划下周三去成都，经济型」，即可完成方案推荐、比价下单、扫码支付、出票，以及改签退票、降价/航变监控与出发提醒。

## 功能亮点

- 多 Agent 编排：编排中枢 + 专职 Worker 分层，10 类意图 + 6 阶段状态机，资金链路由确定性编排层统一管控
- 意图识别与规则兜底：日期自然语言自由解析、词典强约束防幻觉，叠加资金安全拦截、低置信降级与关键词兜底
- 行程规划：自研约束求解器枚举直连/中转组合，按价格、耗时、时刻、偏好加权打分取 Top3，LLM 仅生成文案
- 订单与支付：幂等防重复下单，Playwright 自动化收银台 → 二维码即推，三层支付检测，全程人机确认、绝不代付
- 改签退票：可解释成本模型自动推荐损失最小方案，改签/退票/降价/航变四场景复用
- 主动服务：后台任务状态机 + 定时调度，价格监控、航变监控、出发前提醒，Web/钉钉/微信多通道推送，四级记忆体系
- 可观测与评估：全链路 Trace 落库回放，规则 + 模型评审 + 用户反馈加权评估闭环

## 技术栈

FastAPI · LangChain · Playwright · APScheduler · MySQL/SQLModel · 钉钉开放平台 · SSE

## 快速开始

1. 安装依赖：

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. 配置环境变量：

   ```bash
   cp .env.example .env
   ```

   填写 `.env` 中的 `DEEPSEEK_API_KEY`（必填）与 `DATABASE_URL`（MySQL）。

3. 初始化数据库：执行 `sql/travel_tables.sql` 建表。

4. 启动服务：

   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8090
   ```

   打开 <http://127.0.0.1:8090> 即可使用。

## 目录结构

- `app/`：后端代码（routers / services / agents / models / channels）
- `static/`：前端页面与 Mock 收银台
- `prompts/`：Agent 提示词
- `sql/`：建表 SQL
- `tests_e2e_mock.py`：端到端测试

## 说明

- 默认 `TRAVEL_MOCK_MODE=true`，外部数据 API 使用内置模拟数据；接入真实供应商时填写 `.env` 中对应密钥并关闭 Mock。
- 真实 `.env` 不纳入版本控制，请勿提交。


# Order-Agent 出行规划与预订智能体

面向「从想法到出行」的完整决策链，基于 FastAPI + LangChain + Playwright + APScheduler 打造的动作型出行 Agent：用户一句「帮我规划下周三去成都，经济型」，即可完成方案推荐、比价下单、扫码支付、出票，以及改签退票、降价/航变监控与出发提醒。

## 功能亮点

- 多 Agent 编排：编排中枢 + 专职 Worker 分层，10 类意图 + 6 阶段状态机，资金链路由确定性编排层统一管控
- 意图识别与规则兜底：日期自然语言自由解析、词典强约束防幻觉，叠加资金安全拦截、低置信降级与关键词兜底
- 行程规划：自研约束求解器枚举直连/中转组合，按价格、耗时、时刻、偏好加权打分取 Top3，LLM 仅生成文案
- 订单与支付：幂等防重复下单，Playwright 自动化收银台 → 二维码即推，三层支付检测，全程人机确认、绝不代付
- 改签退票：可解释成本模型自动推荐损失最小方案，改签/退票/降价/航变四场景复用
- 主动服务：后台任务状态机 + 定时调度，价格监控、航变监控、出发前提醒，Web/钉钉/微信多通道推送
- 记忆驱动决策：L1 画像 / L2 结构化行程 Episode / L3 蒸馏偏好；记忆补全缺失字段需用户显式确认，相似历史进入推荐解释，降价/改签/提醒按用户偏好调节，业务规则始终把关
- 可观测与评估：全链路 Trace（含后台任务的 run/task 关联与订单状态链）落库可查；离线 Replay dry-run 回放 + Failure Taxonomy 失败分类；规则 60% + 模型评审 10% + 用户反馈 30% 按业务链路聚合评估

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

3. 初始化数据库：在 `order-agent` 目录执行 `alembic upgrade head`（Alembic 自动建全库表结构并写入种子数据；旧版手动 SQL 保留在 `sql/travel_tables.sql` 供参考，不再手工执行）。

4. 启动服务：

   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8090
   ```

   打开 <http://127.0.0.1:8090> 即可使用。

## 目录结构

- `app/`：后端代码（routers / services / agents / models / channels）
- `alembic/`：数据库版本迁移（Alembic，含 baseline 全量建表）
- `static/`：前端页面与 Mock 收银台
- `prompts/`：Agent 提示词
- `skills/`：领域技能（SKILL.md，含 RAG retriever 预留位，改文本无需改代码）
- `sql/`：建表 SQL 存档（已被 Alembic 迁移取代）
- `sql/backfills/`：存量数据一次性回填脚本
- `replays/`：离线 Replay 实验留档
- `tests/`：单元测试（pytest）；`tests_e2e_mock.py`：端到端测试

## 调试与评估

- `POST /api/v1/travel/debug/replay`：单条 Trace 规则层 dry-run 重放，返回 before/after 字段级 diff（不调 LLM、不落业务数据）
- `POST /api/v1/travel/debug/replay/cases`：按失败主题（recovery / recommendation_reject）收集回归 case 集
- `POST /api/v1/travel/evaluations`：时间范围评估，返回业务链路级指标（linkResults / totalLinks）与失败分类分布（failureDistribution）

## 说明

- 默认 `TRAVEL_MOCK_MODE=true`，外部数据 API 使用内置模拟数据；接入真实供应商时填写 `.env` 中对应密钥并关闭 Mock。
- 真实 `.env` 不纳入版本控制，请勿提交。



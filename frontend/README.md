# order-agent Frontend (Vue 3 + TypeScript + Pinia)

全新重构的 `order-agent` 现代智能体工作台前端，基于 Vue 3、Vite 5、TypeScript、Element Plus 与 Pinia 搭建。

## 目录结构

```
order-agent/frontend/
├── public/                 # 静态资源与 Mock 收银台 (/mock/checkout.html)
├── src/
│   ├── api/                # API 请求封装 (Axios client, chat, trace, memory, evaluation, order)
│   ├── assets/             # 全局样式与变量
│   ├── components/
│   │   ├── chat/           # MessageBubble, ClarifyCard, PlanCard (👍/👎 反馈), ActionCard
│   │   ├── runtime/        # AgentStatus (流水状态), MemoryContext (记忆切片), TracePreview
│   │   ├── trace/          # Timeline (瀑布流), ReplayDrawer (离线比对), TraceLabelModal
│   │   ├── memory/         # MemoryCard (L1 画像), EpisodeCard (L2 经历), DistillViewer (L3 蒸馏)
│   │   └── evaluation/     # ScoreGauge (60-30-10 仪表盘), MetricsRadar, FailureDistribution
│   ├── router/             # Hash 路由 (createWebHashHistory，杜绝静态托管 404)
│   ├── services/           # 原生 EventSource (SSE) 封装与重连
│   ├── stores/             # Pinia 状态管理 (user, chat, runtime, trace, memory, evaluation, order)
│   ├── types/              # 严格 TypeScript 契约定义
│   ├── views/              # 5 大核心视图 (Chat, Memory, Trace, Evaluation, Order)
│   ├── App.vue             # 科技蓝白顶栏与全局 Shell
│   └── main.ts             # 应用入口
├── index.html              # HTML 模板
├── package.json
├── tsconfig.json
└── vite.config.ts          # 构建输出至 ../backend/static/
```

## 本地开发与联调

1. 安装依赖：
   ```bash
   npm install
   ```

2. 启动 Vite 开发服务器（默认代理到 `http://127.0.0.1:8000`）：
   ```bash
   npm run dev
   ```

3. 生产构建（自动打包编译至 `backend/static/`，直接由 FastAPI 静态托管）：
   ```bash
   npm run build
   ```

## 核心架构特性

- **Hash 模式路由 (`createWebHashHistory`)**：完全规避在 FastAPI 单页托管与反向代理环境下的子路由 404 刷新问题；
- **原生 SSE 通信 (`EventSource`)**：实现对话流式生成、异步锁座进度步进与全链路任务通知；
- **评测闭环与用户反馈**：PlanCard 内置 👍 / 👎 打分交互，直接贯通 30% 用户真实验收权重；
- **L1-L3 记忆全生命周期透视**：支持静态画像维护、结构化历史行程卡片与周期性偏好反思报告；
- **Trace 可观测与 Replay 验证**：支持多阶段节点瀑布流钻取、金标准人工标定与离线 dry-run 回归比对。

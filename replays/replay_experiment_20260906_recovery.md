# Replay 实验留档：Recovery 误标修复（2026-09-06）

> 依据拆解文档 Commit 10：从 Failure Taxonomy 选题 → 导出 case 集 → 改前/改后对比 → 留档。

## 一、问题定义（从数据出发）

Commit 9 上线后评估全量失败分布（2026-08-01 ~ 2026-09-07，user1）：

```text
before: {'Recommendation': 1, 'Recovery': 22}
```

最高频的 Recovery（22 条）全部是 08-11/08-12 的 trace，error_message 清一色 `APIConnectionError: Connection error.`
（当时 LLM 外网不通）。抽看事件链发现关键事实：

```text
AGENT_CALL 报错 → INTENT_FALLBACK → INTENT_RECOGNIZED → ROUTE_SELECTED → REQUEST_FINISHED
```

**这些请求其实都成功了**（意图 Agent 报错后走了关键词兜底并正常回复），只是 `record_agent_call`
在 Agent 调用失败时把整条 Trace 状态标成 FAILED——"步骤失败"被误当成"请求失败"。

## 二、改动

1. `app/services/trace.py`：Agent 调用失败只记录事件级错误，**不再把整体 Trace 标 FAILED**
   （请求是否失败由 TraceScope 出口是否抛异常决定，出口抛异常会记 REQUEST_FAILED 并置 FAILED）。
2. `app/services/evaluation.py`：Failure Taxonomy 的 Recovery 判定只认 `REQUEST_FAILED` 事件，
   不再用 `row.status == FAILED` 一刀切（历史误标行也不会再被错判）。

## 三、before / after（同一批历史数据，规则层对比，不重跑 LLM）

```text
before: Recovery = 22（19 条为"Agent 报错但已兜底恢复"的误标）
after : Recovery = 3 （仅剩真正存在 REQUEST_FAILED 事件的请求失败）
```

avgScore 不受影响（Taxonomy 只影响分类与选题，不影响 60/10/30 得分），符合预期。

## 四、回归 case 集（topic=recovery）

`POST /api/v1/travel/debug/replay/cases {"topic":"recovery","limit":5}` 可复现；
样例 case（均为意图兜底成功的 ORDER_QUERY）：

```text
trace_d118e9eba8eb46… intent=ORDER_QUERY goldenIntent=ORDER_QUERY
trace_6d74d422d79a47… intent=ORDER_QUERY goldenIntent=ORDER_QUERY
trace_5c1eff787bba44… intent=ORDER_QUERY goldenIntent=ORDER_QUERY
```

LLM golden（默认不重跑）：从 trace 事件取当时的意图输出与回复，供将来 `--rerun` 重跑时对照。

## 五、结论（可讲的叙事）

"我不凭感觉改 Agent：从 Trace 发现 Recovery 占比最高的 case 全是同一时段 LLM 网络失败，
进一步发现是'步骤失败被误标为请求失败'的标签语义 bug；修复后同一批数据 Recovery 从 22 降到 3。
剩余 3 条是真实请求失败，属于基础设施偶发，不属于业务逻辑问题。"

## 六、复现命令

```text
cd order-agent
python -m pytest tests/test_feedback_trace.py::test_recovered_agent_error_is_not_recovery -q
# 全量对比（需要本地 MySQL 与 .env）：
POST /api/v1/travel/evaluations   # 范围 2026-08-01~2026-09-07，看 failureDistribution
POST /api/v1/travel/debug/replay/cases {"topic":"recovery"}
```

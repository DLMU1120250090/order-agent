# L1 偏好 key 写读审计清单（Commit 0，2026-09-06）

> 目的：让每个偏好 key 都有明确的写方与读方，消灭"写而不读 / 读而无写"的死偏好。

## preferences 字典内 key

| key | 写方 | 读方 | 处置 | 说明 |
| --- | --- | --- | --- | --- |
| price_monitor | `app/services/orchestrator.py::_handle_price_monitor` | `app/services/scheduler.py::_price_watch`（Commit 0 新增） | 已对齐 | 默认开启；关闭后 price_watch 阶段 1/2 均跳过该用户，航变/出发提醒不受影响 |
| early_bird | `app/services/orchestrator.py::_write_profile_after_booking`（Commit 0 新增，首段出发 < 08:00） | `app/services/planner.py`（时刻分加分） | 已对齐 | 此前"读而无写"恒 False |
| tolerate_change | `app/routers/profiles.py` PUT preferences（人工/前端录入） | `app/services/change_decision.py::_score` | 保留 | 仅影响 preference 软分，成本最优选择优先 |
| positive_feedback / negative_feedback / switch_count | `app/routers/feedback.py` | 无直接业务读取；全量随 profile 进入 L3 distill 上下文 | 保留（供蒸馏） | 计数型，暂不参与排序 |
| cost_vs_time / preferred_transport / seat_pref | 无 | 无 | 已从 schemas 注释移除 | 未实现的 key 不再留在注释里误导 |

## profile 顶层字段（不属于 preferences，附注）

| 字段 | 写方 | 读方 |
| --- | --- | --- |
| home_city | 支付收尾 `_write_profile_after_booking` / profiles API | planner 出发地默认、memory.build_context |
| budget_level | 支付收尾 `_write_profile_after_booking` / profiles API | memory.build_context / distill |
| passengers | 支付收尾 `_write_profile_after_booking` / profiles API | booking 默认乘客、reminder 证件检查 |

## 修订记录

- 2026-09-06（Commit 0）：price_monitor 接入 scheduler 读方；early_bird 增加规则写方；schemas 注释清理；本清单落库（order-agent/memory/）。

## 补充：身份与角色定义（分化方案 A1，2026-09-06）

- 本人：`passenger_id = "0"` 且 `role = "self"`（读方判定：id=="0" 或 role=="self" 二选一/并用）；
- 其余乘客：`role = "others"`（历史 `companion` 并入 others，读方兼容期两者都接受）；
- 不记录 User↔Passenger 关系表；当前单 User（user_id=1）；
- 多乘客且无显式标记时不猜本人（不依赖列表位置）；单人无标记默认本人（本人购票兜底）。

## 补充：L3 蒸馏扩展登记（Commit 4，2026-09-06）

| key | 归属 | 写方 | 读方 | 处置 |
| --- | --- | --- | --- | --- |
| transport | passengers.{pid}（本人=0） | distill_preferences（按乘客分组，样本≥3 且占比≥60%） | MemoryResolver / Planner 软排序 | 已落地 |
| time_window | passengers.{pid} | distill_preferences（早班 05-08 占比≥60%） | Resolver 视图（消费待定） | 已落地（透传） |
| price_sensitivity | user | distill_preferences（价格事件接受率 ≥60% high / ≤30% low） | 登记，Monitor 阈值消费待定 | 已落地（蒸馏写） |
| confirmation_style / notification_channel / auto_action | user | 可手工写入（profiles API / update_preference） | 暂无（避免虚假消费） | 登记待消费 |
| conditions | 任意 entry 内可选字段 | update_preference(conditions=...) | Resolver 透传（暂不匹配） | 预留 |

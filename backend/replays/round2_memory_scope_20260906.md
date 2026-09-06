# 记忆分化方案（第二轮）实现留档 2026-09-06

> 依据：`order-agent 记忆系统分化方案.md`（附录 A 决策定稿）+ 第二轮编码任务拆解（Commit 0~5）。

## 一、本轮目标

把记忆系统从"单 User 级"升级为 **User / Passenger 分 Scope**：本人固定 passenger_id=0、role 只分 self/others、
下单前确认"给谁买"、补上 User L2 行为事件层、决策上下文显式分层、L3 按乘客蒸馏。

## 二、Commit 记录（git log）

```text
7b7f24c feat: L3 蒸馏按乘客扩展
d9bb3e6 feat: 决策上下文分层与优先级
17fcfe3 feat: User L2 行为事件层
e62df58 feat: 下单前乘客选择
d71721a feat: 乘客身份定稿 id0 与 role 收敛
（+ 收尾提交：出行后评分入口 / README / 本留档）
```

## 三、关键实现与证据

### 1. 身份定稿（A1/A2）
- 本人= `passenger_id="0"` + `role=self`；其余 `role=others`（companion 并入 others，读方兼容）；
- 多乘客无标记不猜本人（去掉列表位置依赖）；单人无标记默认本人（本人购票兜底）；
- 真实迁移：user1 乘客 P_ 哈希 → "0"；6 条订单 Episode.passengers 统一为 ["0"]；
- 回归测试：重复支付回写不再追加（旧 bug 在 A1 语义下免疫）。

### 2. 乘客选择（P0）
- SessionState 持久化 currentPassengerId / passengerSelectionPending / passengerSelectionDone；
- 多乘客首次下单先问"给谁买"，确认后本会话不再问；下单只带所选乘客；
- 探针：本人+妈妈画像 → 订单只含"妈妈"，Episode.passengers=["P_妈妈"]。

### 3. User L2 行为事件层（P1）
- 新表 memory_user_event（迁移 0005）+ 事件类型集中登记；
- 写入：推荐接受/拒绝、改签确认、退票确认、监控开关；带 trace 关联；
- 读取：Monitor 拿价格事件统计、Change 拿近期处理历史；只提高倾向、绝不自动执行资金操作。

### 4. 决策上下文分层与优先级（P2）
- 优先级链集中登记：current_request > passenger_hard > user_hard > passenger_l3 > user_l3 > l2 > default；
- Resolver 输出 userConstraints / passengerPreferences 双层；按 current_passenger_id 读偏好（本人=0）；
- Planner：硬过滤只由当前需求/User 约束决定，乘客偏好只进软排序（40/30/20/10 不变），推荐理由注明"已结合所选乘客偏好"。

### 5. L3 按乘客蒸馏 + conditions 预留
- 按 episode.passengers 分组蒸馏 transport（样本≥3、占比≥60%）与 time_window（早班判定）；
- User L3 price_sensitivity 从价格事件蒸馏（≥60% high / ≤30% low）；
- update_preference 支持 conditions 透传（暂不匹配）；
- 真实 user1：本人（id=0）从 6 条订单形成 transport=train 的乘客级 L3。

### 6. 出行后评分入口
- POST /api/v1/travel/feedback/post-trip（1~5 星）→ 落到对应订单 Episode 的 outcome.rating/feedback。

## 四、验证汇总

- 单元测试：66 个全部通过（新增：乘客选择 5、User 事件 3、蒸馏 4、post-trip 2、决策分层 3 等）；
- e2e（tests_e2e_mock.py）：RESULT: PASS（QR/支付/三层检测/改签链路环境回归）；
- 多轮真实 DB 探针（乘客选择、事件写入、分层决策、蒸馏、出行后评分）均通过并清理；
- Alembic 迁移至 0005；数据备份位于 E:\tmp\diet-agent\.memory_cleanup_backup_20260906\。

## 五、可讲的面试叙事

"第一轮我把记忆做进决策链路；第二轮解决'记忆属于谁'——本人固定 passenger_id=0，
帮家人买票先确认乘客，Episode/偏好按乘客落库；补了 User 行为事件层支撑价格敏感度等 L3 蒸馏；
决策上下文显式分 user 硬约束与 passenger 软偏好，优先级链集中可调。全程规则层把关，记忆只补全和辅助。"

## 六、边界与后续

- price_drop_accepted/ignored、change_rejected、reminder_set 已登记，可靠写入点待补；
- conditions 仅透传，条件偏好匹配引擎未做；
- 多 User/乘客共享归属为未来扩展（当前单 User）。

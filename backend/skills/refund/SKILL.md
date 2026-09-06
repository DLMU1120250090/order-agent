# refund

## capability
退票/取消的规则材料：退票费分档、到账口径、行程取消风险。

## usage
用户发起 ORDER_CANCEL 时按需注入；执行与金额由确定性服务负责。

## rules
- 退票费与能否退由 RefundRuleService / ChangeDecisionService 判定；
- 不承诺"秒退""全额退"等绝对化表述。

## related tools
ChangeDecisionService / RefundRuleService / TaskService

## retriever (optional)
预留：供应商退改政策检索占位。

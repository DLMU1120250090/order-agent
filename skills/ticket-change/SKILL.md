# ticket-change

## capability
改签/换乘调整的业务材料：成本构成（改签费、价差）、确认流程、风险提示。

## usage
用户发起 ORDER_CHANGE 时按需注入；决策本身不在此文件内。

## rules
- 「能不能改、推荐哪种」必须由 ChangeDecisionService 成本模型决定；
- 本技能只提供解释口径与材料，不替代业务规则。

## related tools
ChangeDecisionService / RefundRuleService / DataCollectorService

## retriever (optional)
预留：接入供应商退改政策时挂 retriever，召回结果仅供规则服务判断前参考。

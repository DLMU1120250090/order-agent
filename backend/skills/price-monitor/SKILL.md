# price-monitor

## capability
价格监控/降价提醒的材料：触发比例、净节省阈值、推送话术边界。

## usage
PriceMonitorService 扫描前读取用户偏好决定阈值；本技能仅沉淀口径与规则边界。

## rules
- 触发与是否推送由 Monitor 的确定性阈值判断；
- 不替用户下单、不承诺最低价保证。

## related tools
PriceMonitorService / PushService / ChangeDecisionService

## retriever (optional)
预留：供应商票价/退改政策检索占位。

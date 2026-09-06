# travel-checklist

## capability
基于行程段、目的地与天气生成实用出行清单（证件 / 行李 / 物品 / 当地注意）。

## usage
用户索取清单、或出发前提醒生成准备包时，把本文件文本注入 ChecklistAgent。

## rules
- 只基于输入行程/目的地/天气生成，不编造航司、班次、证件号或具体店铺；
- 中文 Markdown，控制在 300 字内。

## related tools
ChecklistAgent / DataCollectorService(weather) / ReminderService

## retriever (optional)
预留：未来接政策知识（航司行李额、证件要求等）时，在本节声明 retriever 查询接口；
召回结果只作为清单依据，最终展示仍由 ChecklistAgent 负责。

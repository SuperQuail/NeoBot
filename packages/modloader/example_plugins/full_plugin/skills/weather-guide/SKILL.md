---
name: weather-guide
description: 查询天气并给出出行建议
keywords: 天气 气温 下雨 出行 预报
---

当用户询问天气或出行建议时：

1. 先调用 `full_plugin__query` 查询目标城市天气。
2. 若预报有极端天气（暴雨、高温、台风），调用 `full_plugin__alert` 发送提醒。
3. 出行建议可委托给子 Agent `full_plugin.advice`。
4. 用户未指定城市时，先询问用户，不要自行假设。

---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

官方通道同一 msg_id 的 FULL→AT 升级重投时，消息队列按 message_id 原地替换旧条目（队列仍只有 1 条），并在升级路径跳过资料/头像/图片解析/档案总结等已执行过的重复副作用；同 msg_id 已触发过回复的不再第二次回复；未 @ 的命令文本不先当闲聊回复，AT 到达后命令只执行一次。

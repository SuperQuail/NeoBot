---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

补齐后台/定时/跨聊天回复的官方主动消息接线：start_reply/start_background_reply 支持并透传 proactive（后台合成事件默认 True），send_official_markdown 后台 handler 透传该标志；修复官方会话无可用被动回复目标时后台通知/定时任务直接发送失败（.changes/explicit-proactive-messages.md 声称的「显式走主动消息」此前未真正接线）。

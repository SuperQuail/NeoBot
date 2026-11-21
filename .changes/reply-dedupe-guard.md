---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

FULL→AT 升级在回复进行中的挂起路径不再二次回复：回复后队列/图片等待队列处理时按 message_id 跳过已触发过回复的消息；未注册的 / 命令文本不再被误判为已注册命令而抑制闲聊回复。

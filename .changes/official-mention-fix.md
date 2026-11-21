---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

修复官方适配器下群全量消息（GROUP_MESSAGE_CREATE）未 @ 机器人却被当成 @ 的问题：只有 @ 事件与显式 at 段才触发必回和群命令，普通群消息恢复按意愿概率处理。

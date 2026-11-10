---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
---

群全量消息 GROUP_MESSAGE_CREATE 的 content 仍带 @机器人 标记、mentions 不含机器人；现在把未知群标记补成 bot at 段，群命令（/linkqq 等）才能满足被 @bot 的触发条件。

---
type: fix
scope: adapter
packages:
  python@neobot-adapter: patch
---

修复官方群 AT 事件去掉 @机器人 前缀后，首个 `<@!目标用户>` 标记被误当作机器人前缀丢弃的问题：现在只有位于 content 开头的标记才跳过；正文中第一个 @ 目标也会保留为 at 段。另加保护：/linkqq 在 @ 未解析时不再静默映射发送者本人。

---
type: fix
scope: adapter
packages:
  python@neobot-adapter: patch
---

修复官方群 @ 事件里显式 @ 其他用户被忽略的问题：当 GROUP_AT_MESSAGE_CREATE 的 content 带 `<@!openid>` 标记但平台不返回 mentions 时，适配器此前丢弃该标记，导致 /linkqq @用户、/get openid @用户 退化为操作发送者本人（所有人拿到同一个 openid）。现在正文里的显式 @ 标记即使缺 mentions 也保留为 at 段；AT 事件开头的 @机器人 标记仍跳过，不产生假用户。补回归测试。

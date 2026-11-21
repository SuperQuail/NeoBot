---
type: feat
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方 GROUP_AT_MESSAGE_CREATE/C2C 事件的 mentions 转为 OneBot at 段，命令 at_qqs 与提示词能拿到被 @ 者；/linkqq 只给 QQ 号时映射发送者本人，@用户 + QQ号仍映射对方；/linkgroup 单参继续映射当前群。

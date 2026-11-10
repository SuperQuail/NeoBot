---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方 mentions 切分时保留正文空格，避免 /linkqq @用户 123 被拼成无空格命令；映射后的用户档案同时显示真实 QQ 号与官方合成 QQ ID。

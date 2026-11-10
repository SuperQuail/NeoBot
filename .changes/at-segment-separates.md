---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

命令文本提取时把 at/mention 段当空格分隔符，避免「/linkqq@用户 123」这类无显式空格的输入被拼成「/linkqq123」而无法触发命令。

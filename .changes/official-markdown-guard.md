---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

收紧官方 Markdown 卡片的两处不一致：提示词改为 @全体用 at_everyone=true（正文手写标签会被转义，避免模型误以为已 @全体）；链接校验覆盖空白/尖括号/引用式写法并对危险 scheme 兜底拒绝。

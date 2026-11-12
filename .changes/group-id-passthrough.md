---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

群管理/好友管理工具对纯数字 ID 继续按 int 透传给 OneBot（openid 仍按字符串），修复统一转字符串后参数类型变化的问题。

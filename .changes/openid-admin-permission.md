---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

修复管理员列表里的官方 openid 被权限判定丢弃的问题：admin_accounts/sub_admin_accounts 统一按字符串本地 ID 比较，QQ 号与 openid 都可命中超级/次级管理员权限。

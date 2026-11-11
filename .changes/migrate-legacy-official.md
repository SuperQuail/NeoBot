---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

only-official 下旧定时任务/后台通知的真实 QQ 号/群号自动查映射：有映射迁移为官方合成 ID 并写回定时任务，缺映射打印 WARNING 并跳过；新增 legacy_bindings 解析与迁移测试。

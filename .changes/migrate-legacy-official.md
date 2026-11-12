---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

only-official 下旧定时任务/后台通知的真实 QQ 号/群号自动查映射：有映射迁移为官方合成 ID 并写回定时任务，缺映射逐条只记 DEBUG 并跳过，结束时汇总一条 INFO（N 个目标未迁移，保持原样）；新增 legacy_bindings 解析与迁移测试。

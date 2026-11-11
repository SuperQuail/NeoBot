---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

启动时按 `data/qqbot/identities.json`（只读）把本体数据库里的旧 13 位合成号本地 ID 改写成官方 openid：用户资料/好感度、群资料、消息、记忆、档案与压缩快照、自动总结计数器、跨聊天会话、用量统计。迁移在 alembic 之后、服务读数据之前执行，单个 SQLite 事务、可重复执行（幂等）、无 identities 文件时 no-op；沿用 db_backup 的迁移前快照。目标 openid 行已存在时保留新旧两份数据、记 WARNING 并跳过该条，不删除旧数据。

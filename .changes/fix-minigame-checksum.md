---
type: fix
scope: minigame
packages:
  python@neobot-app: patch
  python@neobot-modloader: patch
---

修复 minigame 插件库 v3 迁移在发布后修正过 SQL、已应用库记录的校验和与当前代码不一致，导致插件启动报 PluginMigrationConflictError、整个小游戏插件加载失败的问题：Migration 新增 legacy_checksums，命中历史校验和时自动把应用记录改写为当前校验和并继续执行后续迁移（不重放），minigame v3 登记旧校验和；启动即可正常加载并继续执行 v4。

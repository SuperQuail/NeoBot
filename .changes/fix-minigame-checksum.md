---
type: fix
scope: minigame
packages:
  python@neobot-app: patch
  python@neobot-modloader: patch
---

修复 minigame 插件库 v3 迁移校验和冲突导致插件启动报 PluginMigrationConflictError、整个小游戏插件加载失败的问题：Migration 新增 legacy_checksums，命中历史校验和时自动把应用记录改写为当前校验和并继续执行后续迁移（不重放）。旧 v3（SELECT * 按位置搬运）只出现在 #305 的开发快照里、未随任何发布版本发布，跑过它的开发库会记录旧校验和且 mg_profile 数据被整体错位；新增 v5 迁移检测错位行（wins 为文本）并按原映射反推修复 user_name/score/best_score/plays/wins/updated_at，正常库 no-op。

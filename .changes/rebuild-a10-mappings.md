---
type: fix
scope: identity
packages:
  python@neobot-app: patch
---

a10→a11 升级默认放弃 a10 写入的人工身份映射：检测到 identity_migration_backup 时先备份当前库，再从迁移前快照整体恢复 core/agent/插件库、清空 user_qq_map aliases（备份），随后由 a11 用 identities.json 重建；失败只 WARNING 不阻断启动。新增 scripts/rebuild_identity_migration.py 支持 dry-run/--apply。

---
type: feat
scope: commands
packages:
  python@neobot-app: patch
---

命令注册新增 @ 用户参数通配符 `Command.at_args`：框架按消息里非 bot 的 @ 目标自动填入 ctx.args 指定位置，插件/内置命令无需再手写 at_qqs 过滤。修复 /add_admin、/del_admin 在官方适配器下只认数字 QQ、@ 到 openid 时无法生效的问题（有 trusted 映射存 QQ，无映射直接存 openid）。新增 scripts/repair_identity_migration.py：a10→a11 自动修复错误身份迁移，默认只恢复个人档案/计数器，可选恢复历史 ID 与插件库。

---
type: feat
scope: commands
packages:
  python@neobot-app: patch
  python@neobot-adapter: patch
---

命令注册 `Command.at_args` 通配符自动处理官方 AT 事件缺失 @ 信息：未解析到目标时不再调用 handler，而是自动报错并提示使用 `self`；`self`/`自己`/`本人` 会自动替换为发送者本地 ID。适配器新增 `official_at_event` 元数据，仅在 `GROUP_AT_MESSAGE_CREATE` 时标记。

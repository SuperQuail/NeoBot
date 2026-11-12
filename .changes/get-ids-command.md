---
type: feat
scope: commands
packages:
  python@neobot-app: minor
---

新增只读命令 /get openid [@用户] 与 /get groupid：官方通道直接返回完整 openid（本人/被 @ 用户/本群），便于部署者复制官方 ID 配置管理员/映射/任务；OneBot 通道没有 openid，只提示不可用，不把 QQ号/群号发进聊天（遵循命令回复不出现 QQ 号的约定）。

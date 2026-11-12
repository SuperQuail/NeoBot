---
type: feat
scope: commands
packages:
  python@neobot-app: minor
---

新增只读命令 /get openid [@用户] 与 /get groupid：官方通道直接返回完整 openid（本人/被 @ 用户/本群），OneBot 通道明确返回 QQ号或群号并说明没有 openid，便于部署者复制官方 ID 配置管理员/映射/任务。

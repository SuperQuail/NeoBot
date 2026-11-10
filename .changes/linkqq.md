---
type: feat
scope: bot
packages:
  python@neobot-app: patch
---

新增 /linkqq 管理员命令（@用户 + 真实QQ号）与 user_identity agent 工具（link/get/unlink）；映射持久化到 data/user_qq_map.json，提示词/资料/历史按真实 QQ 展示，管理员权限、好友黑白名单、回复黑名单按真实 QQ 识别。官方通道不能 @ 其他用户，合成 ID 由 agent 工具映射；不做自动关联。

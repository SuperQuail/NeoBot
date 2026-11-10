---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

agent 工具写入的链接映射只用于展示；若目标用户已有管理员命令写入的 trusted 映射，agent 的 link/unlink 一律拒绝，避免模型自封或改绑管理员身份。

---
type: fix
scope: bot
packages:
  python@neobot-chat: patch
  python@neobot-app: patch
---

自修复 Agent 诊断预算从 5 分钟提升到 2 小时，工具轮次不再设上限（由总超时兜底）；上下文超过约 12 万字符时自动调用 runtime/compact 压缩较早消息，避免多轮工具调用与上下文膨胀导致诊断超时。Agent 运行时新增可选 message_compactor 钩子与 max_iterations=None 支持，其他 Agent 行为不变。

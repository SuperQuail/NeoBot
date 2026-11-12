---
type: feat
scope: bot
packages:
  python@neobot-app: patch
  python@neobot-contracts: patch
  python@neobot-storage: patch
---

消息表新增 tool_call_json 与迁移 0032；发送工具持久化完整 tool_call，非发送工具持久化完整参数/结果但聊天历史只 compact 显示工具名与成败；启动恢复支持 full/compact 两种工具条目；补 reply/message/database/storage 测试。

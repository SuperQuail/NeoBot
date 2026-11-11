---
type: feat
scope: bot
packages:
  python@neobot-app: patch
---

新增 official_group_manage（仅官方通道）：查询机器人群内状态、禁言/解除禁言、踢人、入群审批；只调用官方真实接口，失败返回工具错误，不降级。

---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

旧定时任务绑定迁移任务纳入 ScheduledTaskManager.shutdown 管理：关闭时取消并等待迁移任务退出，done callback 对非取消异常记 WARNING，避免迁移跑进关闭流程或任务级异常无人回收（Task exception was never retrieved）。

---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方通道「被 @」改为按官方 API 契约一次判定：适配器把权威结论写进消息模型 mentioned_self（True/False，非官方为 None）；GROUP_AT_MESSAGE_CREATE 事件本身即被 @，群全量消息只有 content 标记或 mentions/msg_elements 明确指向机器人 openid 才算。机器人 openid 取自 READY 的 d.user.id，缺失时全量消息按未 @ 处理并只告警一次；映射时输出固定字段的 @ 判定诊断日志。app 侧新增 is_addressed_to_bot 统一入口，命令触发、@ 必回、已映射群去重、睡眠唤醒与提示词 @ 判定共用；删除 official_at、官方通道无条件判 @、at 段 qq=0 等补丁式判定。

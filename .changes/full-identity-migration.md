---
type: feat
scope: bot
packages:
  python@neobot-app: patch
---

把 OneBot 数字 QQ号/群号到官方 openid 的迁移补全为完整无损迁移：启动时（official 单通道）与 /linkqq、/linkgroup 后自动迁移核心库（user_data/group_data 合并、档案/计数器/快照、messages/memories/model_usage 的会话与发送者 ID、cross_chat_sessions、定时任务绑定）、agent 工具持久状态（state 文档/events/receipts）与内置插件库（streaming_parser/minigame/starship，含 speaking_schedule 文件级 config/mutes）；两边都有内容时旧版本在前合并，version/updated_at/快照 version 同步；迁移前对核心/agent/插件库做 sqlite 快照（data/db_backup/identity_*），删除/覆盖前写 identity_migration_backup；只使用 trusted 映射，dual 模式跳过插件群绑定；未映射的活跃任务/跨聊天会话 WARNING 提示补 /linkqq、/linkgroup。

---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

官方通道同一 msg_id 的 GROUP_MESSAGE_CREATE（全量、未 @）先到、GROUP_AT_MESSAGE_CREATE（@ 事件）后到时，去重记录改为「message_id → 是否 @」并允许一次「未 @ → 被 @」升级，后到的 @ 事件不再被误丢，命令与 @ 必回正常触发；队列「最新消息为@你的内容」提示改用适配器 mentioned_self 权威结论，uin 未解析/无可用 at 段时也能标出。

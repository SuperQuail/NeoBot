---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
---

修复群全量消息 @ 官方机器人被判成「未 @」：群场景里 @bot 的 id 是 member_openid，与 READY 的 d.user.id 不同，导致 /help 等命令不触发、被@必回不生效。适配器在 openid 未命中时按「mentions 里 bot=true 的 id 出现在正文 @ 标记」兜底判为被 @（source=bot_mention）：昵称已知优先按昵称，若 mentions 里 bot=true 条目的 username 非空且都不是本机器人昵称则直接判未 @、不再做位置兜底（避免多机器人群里 @ 另一个机器人被误触发），用户名缺失时才要求标记在正文开头或为唯一候选。引用消息（message_type=103）的 msg_elements 不再作为 @ 来源。诊断日志补 bot_mention_names；INFO 仅保留权威被 @ 或 mentions 出现 bot=true 的情况，普通群友 @（只有 content_at_ids）降为 DEBUG；告警限流改为 EventMapper 实例级，RESUMED 缺 user 不再告警。

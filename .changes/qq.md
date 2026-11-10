---
type: refactor
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

新增 BotAccounts 提供者：单/双通道、官方/OneBot、self_id/通道/config 的取号细节统一收敛；业务侧只调 bot_account_for_message/event、is_bot_message、looks_like_real_qq 等函数。清理回复、命令、历史补齐、头像、作息插件里对 config.bot.account 的单值假设；官方合成 ID 不再请求 qlogo。经查官方文档 group_openid 无到 QQ 群号的映射，双通道会话不做自动关联。

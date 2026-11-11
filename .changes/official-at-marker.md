---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方通道原生 @ 事件在机器人 uin 未解析（没有可用 at 段）时，用消息级 official_at 标记兜底：@bot 群命令、被@必回与已映射群去重都按被 @ 处理，不再依赖 at 段 qq 是否等于已知账号。

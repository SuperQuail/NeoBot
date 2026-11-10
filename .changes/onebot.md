---
type: feat
scope: adapter
packages:
  python@neobot-adapter: minor
  python@neobot-app: minor
---

OneBot 与官方 bot 可同时运行（两个账号、都可交互）；按会话/按条选路（默认 OneBot，send_reply/send_long_reply 可指定 channel）；双待账号通过 API 获取，不读 config.bot.account；面板同时展示两条通道，模式支持 dual 并热重载。

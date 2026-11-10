---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

send_reply/send_long_reply 已通过 mention_qqs 发送真实 @ 时，移除正文开头重复的 @昵称/@ QQ号 文本，避免「@唐天 @ 唐天 喵」；工具说明改为不要在正文里再写 @。

---
type: feat
scope: bot
packages:
  python@neobot-app: patch
---

新增官方专用 send_official_markdown（官方 Markdown 卡片），支持内嵌 @用户/@全体与 qqbot-cmd-enter/input 指令标签；与 Markdown 图片（send_long_reply）明确区分；补充提示词 skill，普通文本不再耦合 Markdown。

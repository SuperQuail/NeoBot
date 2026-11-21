---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
---

官方 content 中的 @ 标记按出现位置切分为 text/at 段，保留「/linkqq ... @用户」的真实顺序；未出现在正文里的 mention 追加到末尾，@机器人自身标记丢弃。

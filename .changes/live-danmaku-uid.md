---
type: fix
packages:
  python@neobot-app: patch
---

Give the live-reply prompt the current danmaku's uid and only mark the current message as "@-mentioned", so the bot stops guessing (and mis-@-ing) a history line.

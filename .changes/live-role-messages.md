---
type: perf
packages:
  python@neobot-app: patch
---

Send live-room history as role messages (bot turns as send_reply tool calls) instead of one text blob, so the stable prefix can hit the model cache and the model sees how it talks.

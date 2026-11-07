---
type: refactor
packages:
  python@neobot-app: minor
---

Run the live reply's tool loop without the generic agent wrapper: the prompt is sent verbatim, each model call and the whole turn get their own timeouts, and the tool surface stays send_reply/cancel.

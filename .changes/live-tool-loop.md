---
type: refactor
packages:
  python@neobot-app: minor
---

Drive the B站 reply tool loop directly instead of through the generic agent wrapper: prompts are sent verbatim, each model call and the whole turn get their own timeouts, and tool errors go back to the model instead of aborting the turn. Applies to comments, private messages and live replies.

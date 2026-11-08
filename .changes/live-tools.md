---
type: feat
packages:
  python@neobot-app: minor
---

Give the live reply agent on-demand tools for its room: look at the current frame and transcribe the last few seconds of audio. Tool results carry only the conclusion and text (no paths or URLs), tool time is capped so it cannot eat the whole turn, and tool errors come back to the model.

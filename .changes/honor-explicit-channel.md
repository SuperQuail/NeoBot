---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

双通道群发送的 OneBot 偏好只作用于未显式指定 channel 的默认路径；显式 channel 不再被静默改投，仍按调用方要求发送。

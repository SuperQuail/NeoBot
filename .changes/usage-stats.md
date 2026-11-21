---
type: fix
scope: statistics
packages:
  python@neobot-app: patch
---

修正用量计费在「整段 prompt 命中缓存」时的重复计费：供应商返回的 prompt_tokens 已含缓存命中部分，
命中 token 不再同时按未命中价再计一遍；内建公式与内置峰谷脚本共用同一套命中/未命中拆分，
面板金额与报表合计回到与实际账单一致的口径。

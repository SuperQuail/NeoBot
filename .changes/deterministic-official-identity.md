---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
---

合成号改为按 (AppID, 场景, openid) 确定性派生并保留旧映射，identities.json 丢失/重启不再按消息顺序漂移；新增 openid_fingerprint 诊断日志；文档说明 openid 场景隔离与 union_openid 限制。

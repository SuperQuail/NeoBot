---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

移除 9000000000001 自动默认超管，配置 0.11.3 迁移清掉自动写入值；openid 为唯一身份源头，新增 encode/decode 反向表接口，说明 13 位合成号无法纯哈希可逆。

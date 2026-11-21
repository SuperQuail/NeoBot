---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方登录失败分类修正：只有明确鉴权失败（HTTP 401/403、token 接口的 appid/secret 业务错误码）才计入连续登录失败；5xx/429/网络异常归入网络错误不计数，网关 close code 4004（token 失效）只刷新 token、不再计入，避免瞬时抖动在数秒内累计 3 次误删扫码凭据。连续 3 次真鉴权失败转重新扫码与 READY/RESUMED 清零行为不变。

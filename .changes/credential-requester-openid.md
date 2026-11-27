---
type: fix
scope: credentials
packages:
  python@neobot-app: patch
---

凭据申请记录申请者身份时不再强制转成数字：官方 openid 用户无需先绑定 QQ 也能正常申请，`requester_id` 按字符串保存（仅用于审计，不参与授权判定）。

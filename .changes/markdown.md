---
type: feat
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

群聊 at 段按合成 ID 反查 member_openid，生成 <qqbot-at-user id=.../> 并强制 markdown 发送；真实 QQ 先经 user_identity 反查合成 ID；@全体成员 支持 qqbot-at-everyone；未知 openid 降级 @昵称文本。

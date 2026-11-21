---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

将开放平台默认开发者 9000000000001 改为 chat.admin_accounts 配置默认值并迁移 0.11.1；/linkqq 映射超管 QQ 仅允许超管；热重载保留 env 官方凭据；网关断开清 connected；文本发送捕获鉴权错误；mentions 用 bot openid 识别 @bot；官方凭据配置优先并新增解绑接口/按钮。

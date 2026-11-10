---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

提示词发送者/群/聊天环境、用户资料、历史、通知、档案与兜底名统一按 ID 规模展示：真实 QQ 号标 QQ:，官方 13 位合成 ID 标 ID:；分析头像工具对合成 ID 直接返回明确错误不再请求 get_qq_avatar/qlogo；图片发送与跨聊天工具说明补充官方合成 ID 语义。

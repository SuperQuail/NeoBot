---
type: feat
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

后台通知/定时任务显式走 official 主动消息（不再依赖被动回退）；请求助手 CoreProxy 跟随事件来源通道；补齐群/单聊消息开关、订阅授权事件；保留发送失败只写日志/返回工具错误的语义。

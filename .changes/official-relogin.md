---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方通道连续 3 次登录/鉴权失败后停止用旧凭据自动重连：记录明确错误，删除扫码落盘凭据（配置/环境变量来源只提示不删配置），并自动重新拉起扫码绑定——面板「机器人通道」页显示新二维码并提示重新扫码，控制台打印 ASCII 二维码与绑定链接；绑定成功后用新凭据重连，成功连接（READY/RESUMED）后失败计数清零。

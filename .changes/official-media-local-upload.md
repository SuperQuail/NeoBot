---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方通道图片/语音/文件改为优先读取 app 提供的本地路径走官方分片上传（媒体段新增 local_path，file 字段保留兼容 OneBot）；/help 卡片渲染或发图失败时回退等价纯文本并保留日志，不再静默跳过聊天输出。修复官方通道发图报「上传官方富媒体失败：上传URL错误」（QQ 拉不到 127.0.0.1 文件服务器 URL）。

---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

官方富媒体 file_info 缓存改为按内容哈希区分本地/内联来源（URL 保持按 URL 缓存），修复 app 用固定文件名覆写卡片图（/help、/reload 等）后在 ttl 内复用上一张图 file_info、发送旧卡片的问题。

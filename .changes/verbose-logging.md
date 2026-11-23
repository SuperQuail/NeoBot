---
type: feat
scope: logging
packages:
  python@neobot-app: patch
---

新增 `[debug].verbose_logging`（auto/on/off，默认 auto）：默认不再把数据库 SQL、WebSocket 帧、图片解码等第三方库 DEBUG 写入日志文件，排障时可在面板或配置里打开；on/off 支持热重载，auto 跟随 Debug 模式并在软重启时重新解析。

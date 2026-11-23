---
type: fix
scope: logging
packages:
  python@neobot-app: patch
---

修复 `[debug].verbose_logging` 的布尔取值与 httpx 降级顺序：`verbose_logging = true`/`false`（含配置加载后的 `"True"`/`"False"`）现在分别等同 `on`/`off`，不再落入 auto；`off` 时 `httpx`/`aiohttp.access` 的逐请求 INFO 不再写入日志文件，与「从不记录」文案一致。

---
type: feat
scope: logging
packages:
  python@neobot-app: minor
---

新增 `[debug].log_max_total_mb`（默认 500 MB）日志目录体积预算：`data/logs` 总量超限后按最旧优先删除轮转文件，当前 `neobot.log` 永不删除；启动时立即检查一次，之后在文件 sink 的写入路径上按小时节流检查。原有的 10 MB 轮转与 7 天保留不变。
---
type: perf
scope: emoji
packages:
  python@neobot-app: patch
---

表情包定时扫描改为先比对目录指纹（文件名 + 大小 + mtime_ns，图片与 `.txt` 都算）：没有变化就跳过扫描，检查间隔从 5 分钟放宽到 15 分钟，并每 8 小时强制完整扫描一次兜底；扫描成功才盖章，失败下一轮重试。

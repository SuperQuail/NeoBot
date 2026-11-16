---
type: feat
scope: dashboard
packages:
  python@neobot-app: patch
---

面板配置表单新增 `datetime` / `date` / `time` 三种字段类型：本体（dataclass）与插件（Pydantic）配置都渲染对应的日期时间、日期、时间选择器，取值统一为 ISO 8601 字符串（`YYYY-MM-DDTHH:MM:SS` / `YYYY-MM-DD` / `HH:MM:SS`）。可选字段清空表示不设置；带时区偏移或毫秒的存量值先规范化再展示。

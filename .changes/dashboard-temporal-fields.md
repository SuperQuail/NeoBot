---
type: feat
scope: dashboard
packages:
  python@neobot-app: patch
---

面板配置表单新增 `datetime` / `date` / `time` 三种字段类型：本体（dataclass）与插件（Pydantic）配置都渲染对应的日期时间、日期、时间选择器，取值统一为 ISO 8601 字符串（`YYYY-MM-DDTHH:MM:SS` / `YYYY-MM-DD` / `HH:MM:SS`）。可选字段清空即从配置里删除该键（= 不设置）。面板按本地面钟编辑：编辑过的值按本地 naive 回写，时区偏移与亚秒会被丢弃；未编辑的字段保持原样。

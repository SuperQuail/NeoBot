---
type: fix
scope: modloader
packages:
  python@neobot-modloader: patch
  python@neobot-app: patch
---

无终端环境下插件 PyPI 依赖确认读到 EOF（Windows 把 stdin 接到 NUL 时 isatty() 仍返回 True）时按「没有可交互终端」跳过安装并记 warning，不再抛 EOFError；启动装配期确认失败只记日志、继续装配，面板安装改为返回可读的「缺少 PyPI 依赖」错误而不是 500。

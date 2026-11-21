---
type: feat
scope: dashboard
packages:
  python@neobot-app: patch
---

新增 React 页面 /channels 用同源 iframe 嵌入 /qqbot/?embed=1，保留左侧工具栏；扩展页不再注册侧栏入口、隐藏自身页头，面板安全头对 /qqbot 放开同源嵌套；模式切换继续写 config.toml 并热重载。

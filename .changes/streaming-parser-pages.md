---
type: fix
scope: dashboard
packages:
  python@neobot-app: patch
---

修复局域网 http 等非安全上下文打开面板时「使用说明」与「插件页面」整页渲染报错的问题：`crypto.randomUUID` 只在安全上下文提供，宿主页与插件页面桥接脚本改为在它缺失时退回随机串生成会话标识，不再抛出 `crypto.randomUUID is not a function`。

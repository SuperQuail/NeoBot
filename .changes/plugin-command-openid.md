---
type: fix
scope: bot
packages:
  python@neobot-modloader: patch
---

插件声明式命令在官方群不再因 int(openid) 崩溃：CommandContext.conv_id 直接作为事件 group_id 兜底，不再 int() 化；官方群 openid 命令可正常执行，OneBot 数值群号事件行为不变。

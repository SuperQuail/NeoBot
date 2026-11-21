---
type: fix
scope: bot
packages:
  python@neobot-app: patch
---

已映射群且 OneBot 在线时，只把未 @ 官方机器人的普通群消息去重交给 OneBot；显式 @ 官方机器人的官方群消息（@ 事件/正文 @bot 由适配器补 at 段）仍按官方通道正常处理，避免命令与提问整条丢失。同时修正解析后 message_type 为枚举导致的早期判断，去重不再整段失效。

---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

识别 err_code；发送失败只记录 info 并返回工具错误，不进入聊天流；移除 markdown/被动/媒体/通道自动降级回退；普通文本固定纯文本；引用 ref_idx、delete_msg、member_role、群信息/成员、语音 wav、被动额度/msg_seq 修复；ACL 只认 trusted；提示词/技能/插件/后台按官方能力过滤；双通道路由按来源通道。

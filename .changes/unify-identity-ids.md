---
type: refactor
scope: bot
packages:
  python@neobot-app: patch
---

统一 QQ号/官方合成号判断 API（is_synthetic_id/looks_like_real_group_number/infer_channel/group_label/profile_identity），调用方不再写位数分支；self-sent 队列条目携带 tool_call，role_messages 可重建真实工具调用与回执；修复发图/长回复/语音/官方 Markdown 历史缺失与失败误写；自身发言不再渲染负 msg_id。

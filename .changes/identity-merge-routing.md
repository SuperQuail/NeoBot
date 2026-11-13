---
type: feat
scope: bot
packages:
  python@neobot-app: patch
  python@neobot-memory: patch
  python@neobot-storage: patch
---

`/linkqq`、`/linkgroup` 成功后以 openid 为主键合并历史档案：QQ号/群号一侧的 user_profile/user_summary/group_profile/group_summary 与 user_data/group_data 并入 openid（文本按「QQ号版本在前、openid 版本在后」拼接，资料字段优先 openid、好感度取较大值），合并后删除源行；之后的资料/档案读写统一归一到 openid，避免同一人/同一个群长期记忆分裂。双通道出站调整：被 @ 触发的一轮固定用来源通道回复（哪个 bot 被 @ 就哪个回），普通/随机回复仍优先 OneBot、不可用回落官方。

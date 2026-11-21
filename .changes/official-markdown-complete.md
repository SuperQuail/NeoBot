---
type: feat
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: minor
---

补全官方 Markdown 卡片工具 send_official_markdown：新增 at_everyone（仅群聊、按群+本地自然日节流、适配器校验管理员）与 commands 指令按钮（text/show ≤100、urlencode、群聊禁 enter）；content 只放行内嵌 @用户，其余官方标签全角化并在回执返回 neutralized 计数，@全体/按钮只能来自结构化参数；单聊内嵌 @ 文本化；普通文本路径也清理官方标签；链接只允许 http(s) 并拒绝回环/内网地址；保持发送失败不降级、明确返回错误。

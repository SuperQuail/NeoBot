---
type: fix
scope: bot
packages:
  python@neobot-adapter: patch
  python@neobot-app: patch
---

新增官方 SUPPORTED_ACTIONS 能力表与 supports_action 查询（供插件/宿主判断官方真实能力）；命令图片发送检查 SendMsgResponse.status，失败只写日志不误报成功。

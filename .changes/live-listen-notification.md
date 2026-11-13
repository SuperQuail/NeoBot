---
type: feat
scope: streaming_parser
packages:
  python@neobot-app: patch
  python@neobot-adapter: patch
  python@neobot-modloader: patch
  python@neobot-contracts: patch
---

直播监听插件命令统一改为「直播监听」前缀：/监听 → /直播监听、/取消监听 → /取消直播监听、/监听列表 → /直播监听列表、/监听向导 → /直播监听向导，旧命令名保留为别名。开播/下播通知改为两条消息：先发插件渲染的卡片图片，官方通道再发一条原生图文卡片（msg_type=8，封面用 B 站直播间原始封面，标题/描述带主播与直播信息，卡片可点进直播间；发送失败补纯链接），OneBot 通道第二条为只含直播间链接的文本。放弃 Markdown 卡片与 qqbot-media 内嵌图：实测客户端会把素材图平铺渲染，真实登录态校验上传字节一致，属客户端渲染问题。新增 /直播状态 <房间号>：按同样两条消息格式预览，不写订阅、不触发通知。插件 SDK 发送接口新增 proactive 主动消息透传；卡片截图显式固定仿真视口；B站 /直播互动列表 改为 HTML 卡片；删除官方通道无意义的 member_openid warning。

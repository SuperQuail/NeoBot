"""live_interact 的拆分实现。

常量（constants）、无状态小工具（helpers）与六组 mixin：房间/状态（rooms）、
媒体（media）、WebSocket（ws）、自动回复（reply）、内容生成（generation）、
定时弹幕（schedules）。门面 neobot_app.bilibili.live_interact 只保留类定义、
生命周期与心跳，公开导入不变。"""

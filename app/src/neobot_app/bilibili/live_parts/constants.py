"""直播交互的时间间隔与容量上限（门面按同名 re-export）。"""


_WS_OP_HEARTBEAT = 2
_WS_OP_MESSAGE = 5
_WS_OP_AUTH = 7
_WS_OP_AUTH_REPLY = 8
_WS_HEARTBEAT_SECONDS = 30.0
#: 收包超时 = 2×心跳：这么久收不到任何包就认为连接僵死，主动断开重连。
_WS_RECEIVE_TIMEOUT_SECONDS = _WS_HEARTBEAT_SECONDS * 2
_WS_RECONNECT_MAX_SECONDS = 60.0
_WS_HEALTHY_SECONDS = 60.0
#: 认证连续失败这么多次后停止监听该房间（多半是登录态失效，重连也没用）。
_WS_AUTH_MAX_FAILURES = 3
#: 每房间同时排队处理的弹幕上限：刷屏时超出直接丢弃，任务不再无限堆积。
_DANMU_MAX_PENDING = 8
#: 超过这个秒数才轮到处理的弹幕不再触发自动回复（历史照记，避免回旧话）。
_DANMU_STALE_SECONDS = 15.0
#: 弹幕发送失败后的短冷却，避免同一条弹幕反复生成再失败。
_SEND_FAIL_COOLDOWN_SECONDS = 30.0
#: 观众档案任务的并发上限；与弹幕回复解耦，慢档案写入不占回复通道。
_ARCHIVE_CONCURRENCY = 4
#: 房间开播状态缓存时长；避免每条弹幕都打一次直播间信息接口。
_LIVE_STATUS_TTL_SECONDS = 60.0
#: 每房间保留的最近弹幕条数。
_MAX_HISTORY = 500
#: 每房间保留的最近非弹幕事件条数。
_MAX_RECENT_EVENTS = 100
#: 直播间复用 QQ 档案表；加前缀避免与 QQ 群号/QQ 号撞键。
_LIVE_ROOM_ARCHIVE_PREFIX = "bilibili_live:room:"
_LIVE_USER_ARCHIVE_PREFIX = "bilibili_live:uid:"
#: 跨房间事件去重键容量。
_MAX_EVENT_KEYS = 2000
#: 定时弹幕检查间隔。
_SCHEDULE_CHECK_SECONDS = 30.0
_RECURRENCES = frozenset({"once", "daily", "weekly"})

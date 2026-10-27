"""小游戏服务层的常量：每日上限、计分、池状态与清理间隔。"""

from __future__ import annotations


#: mg_daily 里的计数键
DAILY_BOTTLE_SEND = "bottle:send"

DAILY_BOTTLE_PICK = "bottle:pick"

#: 每日上限（§4.5：发瓶 5 + 捞瓶 5，分别计；捞取无冷却）
BOTTLE_SEND_DAILY_LIMIT = 5

BOTTLE_PICK_DAILY_LIMIT = 5

#: 每瓶 / 每次捞取的积分
BOTTLE_SEND_SCORE = 1

BOTTLE_PICK_SCORE = 1

#: 排除「自己最近 N 次捞取过的发送者」
RECENT_PICK_EXCLUSION = 3

#: mg_record 清理的最小触发间隔（秒）：进程内首次调用不清理，避免把
#: 「捞瓶流程」变成带 DELETE 的流程（A25 的 SQL 审计口径）。
CLEANUP_INTERVAL_SECONDS = 3600.0

#: 池状态
STATUS_POOLED = "pooled"

STATUS_PICKED = "picked"

STATUS_EXPIRED = "expired"

"""小游戏数据访问层（spec(5) §4.4 / R12）。

**程序负责**：随机、幂等、每日上限、计分、落库、池上限与归档、排行榜；
**不负责**玩法判定（是否算成语、接不接得上等一律交 AI，见 D14）。

设计要点：

- 时间一律以 **ISO 字符串**写进 DATETIME 列：SQLite 是动态类型，字符串比较即
  时间比较（同一时钟源的偏移格式一致），因此「伪时间」测试不需要额外机制；
- **漂流瓶只做软删除**（status=picked/expired + 时间戳），全程不 DELETE；
  唯一会 DELETE 的是 mg_record 的到期清理（record_keep_days），且只在
  显式调用 cleanup_records() 时发生（进程内最小间隔 1 小时，见下）；
- 池满转档用 **ORDER BY RANDOM() LIMIT 1**（随机，不按 created_at）；
- 所有随机都走注入的 rng（测试可种子化）。
"""

from __future__ import annotations

import random
from typing import Any
from neobot_app.time_context import now_local

from .parts.service_constants import (
    DAILY_BOTTLE_SEND,
    DAILY_BOTTLE_PICK,
    BOTTLE_SEND_DAILY_LIMIT,
    BOTTLE_PICK_DAILY_LIMIT,
    BOTTLE_SEND_SCORE,
    BOTTLE_PICK_SCORE,
    RECENT_PICK_EXCLUSION,
    CLEANUP_INTERVAL_SECONDS,
    STATUS_POOLED,
    STATUS_PICKED,
    STATUS_EXPIRED,
)
from .parts.service_profile import _ServiceProfileMixin
from .parts.service_bottle import _ServiceBottleMixin
from .parts.service_checkin import _ServiceCheckinMixin
from .parts.service_records import _ServiceRecordsMixin


class MinigameService(
    _ServiceProfileMixin,
    _ServiceBottleMixin,
    _ServiceCheckinMixin,
    _ServiceRecordsMixin,
):
    """小游戏的数据访问：池 / 积分 / 签到 / 抽签 / 流水 / 排行榜。"""

    def __init__(
        self,
        *,
        database: Any,
        config: Any,
        clock: Any = None,
        rng: random.Random | None = None,
        logger: Any = None,
        monotonic: Any = None,
    ) -> None:
        self._database = database
        self._config = config
        self._clock = clock or now_local
        self._rng = rng or random.Random()
        self._logger = logger
        self._monotonic = monotonic
        self._last_cleanup_at: float | None = None
        self._cleanup_armed = False


__all__ = [
    "BOTTLE_PICK_DAILY_LIMIT",
    "BOTTLE_PICK_SCORE",
    "BOTTLE_SEND_DAILY_LIMIT",
    "BOTTLE_SEND_SCORE",
    "CLEANUP_INTERVAL_SECONDS",
    "DAILY_BOTTLE_PICK",
    "DAILY_BOTTLE_SEND",
    "MinigameService",
    "RECENT_PICK_EXCLUSION",
    "STATUS_EXPIRED",
    "STATUS_PICKED",
    "STATUS_POOLED",
]

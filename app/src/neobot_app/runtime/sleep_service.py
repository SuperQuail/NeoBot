"""睡眠服务:全局睡眠状态管理(群聊不自动回复,私聊不受影响)。

睡眠期间:
- 群聊消息继续接收并组装 message queue,但不触发回复事件;
- 群聊中被@时会被唤醒,并注入"唤醒提示词"(可通过
  data/prompts/custom/prompts.toml 的 [wake_up] 分区自定义)后回复;
- 私聊保持不变,不睡觉,始终正常回复(私聊回复不走意愿管线);
- 时间到 / /awake 命令 / 被@ 均可结束睡眠;
- 睡眠时长上限 12 小时,无冷却限制。
"""

from __future__ import annotations

import re
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.time_context import epoch_seconds, from_epoch_seconds

# 睡眠时长上限:12 小时
MAX_SLEEP_SECONDS = 12 * 3600

# 唤醒提示词默认值(可由自定义提示词系统的 [wake_up] 分区覆盖)
DEFAULT_WAKE_PROMPT = "你刚刚正在睡觉,现在被叫醒了,还有点困."

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$", re.IGNORECASE)
_UNIT_SECONDS = {"": 60, "s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_sleep_duration(text: str) -> tuple[float | None, str | None]:
    """解析睡眠时长文本,返回 (秒数, 错误消息)。

    支持 30s / 10m / 2h / 1d,裸数字按分钟计;时长上限 12 小时。
    """
    if text is None or not str(text).strip():
        return None, (
            "缺少睡眠时长参数(支持 30s / 10m / 2h / 1d,"
            "裸数字按分钟,最多 12 小时)"
        )
    match = _DURATION_RE.match(str(text).strip())
    if match is None:
        return None, (
            f"无法解析时长 {text!r}(支持 30s / 10m / 2h / 1d,"
            "裸数字按分钟,最多 12 小时)"
        )
    value = float(match.group(1))
    unit = match.group(2).lower()
    seconds = value * _UNIT_SECONDS[unit]
    if seconds <= 0:
        return None, "睡眠时长必须大于 0"
    if seconds > MAX_SLEEP_SECONDS:
        return None, f"睡眠时长最多 {MAX_SLEEP_SECONDS // 3600} 小时"
    return seconds, None


def format_sleep_duration(seconds: float) -> str:
    """把秒数格式化为人类可读的中文时长。"""
    minutes = int(round(seconds / 60))
    if minutes < 60:
        return f"{minutes} 分钟"
    if minutes % 60 == 0:
        return f"{minutes // 60} 小时"
    return f"{minutes // 60} 小时 {minutes % 60} 分钟"


class SleepService:
    """Bot 睡眠状态管理(内存态,重启后自动醒来)。

    - 睡眠期间:群聊消息继续入队但不触发回复;被@时唤醒并带提示词回复;
    - 私聊不受影响(私聊回复不走意愿管线);
    - 时间到 / /awake / 被@ 均可结束睡眠。
    """

    def __init__(
        self,
        *,
        prompt_store: Any = None,
        logger: Logger | None = None,
        max_seconds: float = MAX_SLEEP_SECONDS,
    ) -> None:
        self._prompt_store = prompt_store
        self._logger = logger or NullLogger()
        self._max_seconds = max_seconds
        self._wake_up_at: float | None = None
        self._sleep_started_at: float | None = None

    # ── 状态查询 ──

    def is_sleeping(self) -> bool:
        """是否处于睡眠中(时间已到自动视为醒来)。"""
        if self._wake_up_at is None:
            return False
        if epoch_seconds() >= self._wake_up_at:
            self._wake_up_at = None
            self._logger.info(
                "Bot 睡眠到期,自动醒来(控制台日志:睡眠完毕)",
                elapsed_text=self._sleep_elapsed_text(),
                ended_at=epoch_seconds(),
            )
            self._sleep_started_at = None
            return False
        return True

    def remaining_seconds(self) -> int:
        """剩余睡眠秒数(未在睡眠时返回 0)。"""
        if not self.is_sleeping():
            return 0
        return max(0, int(self._wake_up_at - epoch_seconds()))

    def wake_up_at(self) -> float | None:
        """预计醒来的 epoch 秒;未在睡眠时返回 None。"""
        return self._wake_up_at if self.is_sleeping() else None

    def wake_up_time_text(self) -> str:
        """预计醒来时间的本地文本(如 '14:30');未在睡眠时返回空串。"""
        at = self.wake_up_at()
        if at is None:
            return ""
        return from_epoch_seconds(at).strftime("%H:%M")

    # ── 操作 ──

    def sleep(self, seconds: float) -> tuple[bool, str]:
        """开始睡眠。返回 (是否成功, 提示文本)。"""
        seconds = float(seconds)
        if seconds <= 0:
            return False, "睡眠时长必须大于 0"
        if seconds > self._max_seconds:
            return False, f"睡眠时长最多 {int(self._max_seconds // 3600)} 小时"
        self._wake_up_at = epoch_seconds() + seconds
        self._sleep_started_at = epoch_seconds()
        self._logger.info(
            "Bot 开始睡眠(控制台日志)",
            duration_seconds=int(seconds),
            duration_text=format_sleep_duration(seconds),
            sleep_started_at=self._sleep_started_at,
            wake_up_at=self._wake_up_at,
            wake_up_at_text=self.wake_up_time_text(),
        )
        return True, (
            f"好的,我去睡觉了(睡眠 {format_sleep_duration(seconds)},"
            f"预计 {self.wake_up_time_text()} 醒来)。"
            "睡眠期间群聊消息只接收不回复,被@会叫醒我;私聊不受影响。"
        )

    def wake(self, reason: str | None = None) -> bool:
        """结束睡眠。返回之前是否在睡眠中。reason 用于日志定位唤醒来源。"""
        was_sleeping = self.is_sleeping()
        if was_sleeping:
            self._logger.info(
                "Bot 被唤醒(控制台日志:睡眠完毕)",
                reason=reason or "unknown",
                elapsed_text=self._sleep_elapsed_text(),
                ended_at=epoch_seconds(),
            )
        self._wake_up_at = None
        self._sleep_started_at = None
        return was_sleeping

    def _sleep_elapsed_text(self) -> str:
        """睡眠已持续时长的可读文本(用于结束日志;睡眠未开始/已清除时返回 '?')。"""
        if self._sleep_started_at is None:
            return "?"
        elapsed = max(0.0, epoch_seconds() - self._sleep_started_at)
        return format_sleep_duration(elapsed)

    # ── 唤醒提示词(参考自定义提示词系统,可被 data/prompts/custom 覆盖) ──

    def wake_prompt(self) -> str:
        """读取唤醒提示词:[wake_up].template,支持自定义提示词文件覆盖。"""
        if self._prompt_store is not None:
            value = self._prompt_store.template("wake_up", default=DEFAULT_WAKE_PROMPT)
            if value and value.strip():
                return value
        from neobot_app.prompt.store import fallback_template

        return fallback_template("wake_up", default=DEFAULT_WAKE_PROMPT)

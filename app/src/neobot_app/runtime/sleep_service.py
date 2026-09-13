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

import asyncio
import re
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.time_context import epoch_seconds, from_epoch_seconds, monotonic_seconds

# 睡眠剩余时间播报间隔(秒)
SLEEP_TICKER_INTERVAL_SECONDS = 60

# 睡眠时长上限:12 小时
MAX_SLEEP_SECONDS = 12 * 3600

# 唤醒提示词默认值(可由自定义提示词系统的 [wake_up] 分区覆盖)
DEFAULT_WAKE_PROMPT = "你刚刚正在睡觉,现在被叫醒了,还有点困."

# /sleep 命令的提示词默认值(提示词分区 [sleep_cmd]，spec(5) §4.1 / R2)
DEFAULT_SLEEP_CMD_PROMPT = (
    "你刚刚答应去睡觉（睡眠 {duration}，预计 {wake_at} 醒来）。"
    "请用你自己的语气自然回应一句，不要复述本条状态说明。"
)

# /awake 命令的提示词默认值(提示词分区 [awake_cmd])。
# 与 [wake_up] 分工不同：wake_up 是「群聊被@叫醒」的状态注入，
# awake_cmd 是「用户执行 /awake」的回复提示，两者不合并。
DEFAULT_AWAKE_CMD_PROMPT = (
    "你刚被叫醒了（睡了 {elapsed}）。"
    "请用你自己的语气自然回应一句，不要复述本条状态说明。"
)

_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([smhd]?)\s*$", re.IGNORECASE)
# 占位符只认「标识符形态」的花括号：未知占位符原样保留，畸形花括号不报错
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: 双花括号（提示词系统的字面量转义约定）的临时哨兵。
#: 哨兵本身不含花括号，因此不会被第二轮占位符替换命中。
_NUL = chr(0)
_ESCAPED_OPEN = _NUL + "O" + _NUL
_ESCAPED_CLOSE = _NUL + "C" + _NUL


def safe_format(template: str, **values: Any) -> str:
    """安全地把模板里的占位符替换为给定值。

    与提示词系统的约定一致：
    - 未知占位符**原样保留**（便于发现拼错的占位符）；
    - 模板里缺少某个占位符**不报错**；
    - 畸形花括号（嵌套、落单）不报错，只替换能识别的部分；
    - 双层花括号渲染成字面量单层花括号；
    - 值里的花括号不会被二次替换。
    """
    text = "" if template is None else str(template)
    text = (
        text.replace(chr(123) * 2, _ESCAPED_OPEN)
        .replace(chr(125) * 2, _ESCAPED_CLOSE)
    )

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        value = values[key]
        return "" if value is None else str(value)

    text = _PLACEHOLDER_RE.sub(_replace, text)
    return text.replace(_ESCAPED_OPEN, chr(123)).replace(_ESCAPED_CLOSE, chr(125))


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
        # 墙钟只用于展示；实际时长使用单调时钟，避免系统校时提前结束睡眠。
        self._sleep_deadline: float | None = None
        self._sleep_started_monotonic: float | None = None

    # ── 状态查询 ──

    def is_sleeping(self) -> bool:
        """是否处于睡眠中(时间已到自动视为醒来)。"""
        if self._sleep_deadline is None:
            return False
        if monotonic_seconds() >= self._sleep_deadline:
            self._wake_up_at = None
            self._logger.info(
                "Bot 睡眠到期,自动醒来(控制台日志:睡眠完毕)",
                elapsed_text=self._sleep_elapsed_text(),
                ended_at=epoch_seconds(),
            )
            self._sleep_started_at = None
            self._sleep_deadline = None
            self._sleep_started_monotonic = None
            return False
        return True

    def remaining_seconds(self) -> int:
        """剩余睡眠秒数(未在睡眠时返回 0)。"""
        if not self.is_sleeping():
            return 0
        return max(0, int(self._sleep_deadline - monotonic_seconds()))

    def wake_up_at(self) -> float | None:
        """预计醒来的 epoch 秒;未在睡眠时返回 None。"""
        return self._wake_up_at if self.is_sleeping() else None

    def wake_up_time_text(self) -> str:
        """预计醒来时间的本地文本(如 '14:30');未在睡眠时返回空串。"""
        at = self.wake_up_at()
        if at is None:
            return ""
        return from_epoch_seconds(at).strftime("%H:%M")

    # ── 睡眠剩余时间播报(每分钟,接入应用 background_coros) ──

    def ticker(self) -> Any:
        """返回睡眠状态播报协程:睡眠期间每分钟打印剩余时间。

        接入 NeoBotApplication.background_coros,由应用生命周期统一启停。
        """
        return self._ticker_loop()

    async def _ticker_loop(
        self, interval_seconds: float = SLEEP_TICKER_INTERVAL_SECONDS
    ) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            self._log_remaining()

    def _log_remaining(self) -> None:
        """睡眠中打印一条剩余时间日志(每分钟由 ticker 调用)。"""
        if not self.is_sleeping():
            return
        remaining = self.remaining_seconds()
        self._logger.info(
            f"睡眠中,剩余睡眠时间{format_sleep_duration(remaining)}",
            remaining_seconds=remaining,
        )

    # ── 操作 ──

    def sleep(self, seconds: float) -> tuple[bool, str]:
        """开始睡眠。返回 (是否成功, 提示文本)。"""
        seconds = float(seconds)
        if seconds <= 0:
            return False, "睡眠时长必须大于 0"
        if seconds > self._max_seconds:
            return False, f"睡眠时长最多 {int(self._max_seconds // 3600)} 小时"
        self._sleep_started_at = epoch_seconds()
        self._wake_up_at = self._sleep_started_at + seconds
        self._sleep_started_monotonic = monotonic_seconds()
        self._sleep_deadline = self._sleep_started_monotonic + seconds
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
        self._sleep_deadline = None
        self._sleep_started_monotonic = None
        return was_sleeping

    def _sleep_elapsed_text(self) -> str:
        """睡眠已持续时长的可读文本(用于结束日志;睡眠未开始/已清除时返回 '?')。"""
        if self._sleep_started_monotonic is None:
            return "?"
        elapsed = max(0.0, monotonic_seconds() - self._sleep_started_monotonic)
        return format_sleep_duration(elapsed)

    # ── 唤醒提示词(参考自定义提示词系统,可被 data/prompts/custom 覆盖) ──

    def wake_prompt(self) -> str:
        """读取唤醒提示词:[wake_up].template,支持自定义提示词文件覆盖。"""
        return self._template("wake_up", DEFAULT_WAKE_PROMPT)

    def sleep_prompt(self, seconds: float | None = None) -> str:
        """读取 /sleep 命令的提示词:[sleep_cmd].template。

        占位符 {duration} / {wake_at} 用安全替换填充：未知占位符原样保留，
        模板里缺少占位符也不报错（spec(5) §4.1 / R2 / A4）。
        """
        duration = format_sleep_duration(seconds) if seconds else ""
        wake_at = self.wake_up_time_text() if seconds is not None else ""
        return safe_format(
            self._template("sleep_cmd", DEFAULT_SLEEP_CMD_PROMPT),
            duration=duration,
            wake_at=wake_at,
        )

    def awake_prompt(self, elapsed_seconds: float | None = None) -> str:
        """读取 /awake 命令的提示词:[awake_cmd].template。

        占位符 {elapsed} 用安全替换填充。**不**复用 [wake_up]：被@叫醒与
        命令叫醒是两种语义（spec(5) §4.1）。
        """
        if elapsed_seconds is None:
            elapsed = self._sleep_elapsed_text()
        else:
            elapsed = format_sleep_duration(max(0.0, float(elapsed_seconds)))
        return safe_format(
            self._template("awake_cmd", DEFAULT_AWAKE_CMD_PROMPT),
            elapsed=elapsed,
        )

    def elapsed_seconds(self) -> float | None:
        """本次睡眠已持续的秒数；未在睡眠时返回 None（供 /awake 取占位符值）。"""
        if not self.is_sleeping() or self._sleep_started_monotonic is None:
            return None
        return max(0.0, monotonic_seconds() - self._sleep_started_monotonic)

    def _template(self, key: str, default: str) -> str:
        """读取提示词分区:自定义文件覆盖默认,缺失时回退内置兜底。"""
        if self._prompt_store is not None:
            value = self._prompt_store.template(key, default=default)
            if value and value.strip():
                return value
        from neobot_app.prompt.store import fallback_template

        return fallback_template(key, default=default)

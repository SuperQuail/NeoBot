"""全局冻结服务:一键停下 Bot 的一切自动行为,进程继续运行。

用于 token 风暴、异常刷屏等失控场景:

- 冻结后,收到的消息不再触发回复、不再触发档案自动总结;
- 已经在跑的回复管线会在下一轮模型调用前让位;
- 命令系统与网页面板不受影响,`/unfreeze`(或面板按钮)随时恢复。

与 /sleep 的区别:睡眠只影响群聊回复且会被 @ 唤醒;冻结是运维熔断,
群聊与私聊一律停,只能显式解冻(带时长时到期自动解冻)。
"""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.time_context import (
    epoch_seconds,
    from_epoch_seconds,
    monotonic_seconds,
)


class FreezeService:
    """Bot 冻结状态管理(内存态,重启后自动恢复)。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        max_seconds: float | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._max_seconds = max_seconds
        self._frozen_at: float | None = None
        self._frozen_at_monotonic: float | None = None
        self._deadline: float | None = None
        self._reason = ""
        self._operator = ""

    # ── 状态查询 ──

    def is_frozen(self) -> bool:
        """是否处于冻结中(带时长时到期自动解冻)。"""
        if self._frozen_at is None:
            return False
        if self._deadline is not None and monotonic_seconds() >= self._deadline:
            elapsed = self.frozen_for_seconds()
            self._clear()
            self._logger.info(
                "Bot 冻结到期,已自动解冻",
                frozen_seconds=elapsed,
                ended_at=epoch_seconds(),
            )
            return False
        return True

    def frozen_for_seconds(self) -> int:
        """已冻结秒数(未冻结时为 0)。"""
        if self._frozen_at_monotonic is None:
            return 0
        return max(0, int(monotonic_seconds() - self._frozen_at_monotonic))

    def remaining_seconds(self) -> int | None:
        """剩余自动解冻秒数;无限期冻结时返回 None。"""
        if not self.is_frozen() or self._deadline is None:
            return None
        return max(0, int(self._deadline - monotonic_seconds()))

    def status(self) -> dict[str, Any]:
        """供命令/网页面板展示的状态快照。"""
        frozen = self.is_frozen()
        return {
            "frozen": frozen,
            "reason": self._reason if frozen else "",
            "operator": self._operator if frozen else "",
            "frozen_at": self._frozen_at if frozen else None,
            "frozen_at_text": (
                from_epoch_seconds(self._frozen_at).strftime("%Y-%m-%d %H:%M:%S")
                if frozen and self._frozen_at is not None
                else ""
            ),
            "frozen_for_seconds": self.frozen_for_seconds() if frozen else 0,
            "remaining_seconds": self.remaining_seconds() if frozen else None,
        }

    # ── 操作 ──

    def freeze(
        self,
        *,
        reason: str = "",
        operator: str = "",
        seconds: float | None = None,
    ) -> tuple[bool, str]:
        """冻结 Bot。返回 (是否本次生效, 提示文本)。

        重复冻结视为生效(刷新原因/时长),便于在事故中反复确认状态。
        """
        if seconds is not None:
            seconds = float(seconds)
            if seconds <= 0:
                return False, "冻结时长必须大于 0"
            if self._max_seconds is not None and seconds > self._max_seconds:
                return False, f"冻结时长最多 {int(self._max_seconds // 3600)} 小时"

        already = self.is_frozen()
        now = epoch_seconds()
        if not already:
            self._frozen_at = now
        self._frozen_at_monotonic = monotonic_seconds()
        self._deadline = (
            None if seconds is None else self._frozen_at_monotonic + seconds
        )
        if reason:
            self._reason = reason
        if operator:
            self._operator = operator
        self._logger.warning(
            "Bot 已冻结(控制台日志:冻结中)",
            operator=self._operator or "unknown",
            reason=self._reason or "未说明",
            duration_seconds=None if seconds is None else int(seconds),
            frozen_at=now,
        )
        if seconds is None:
            tail = "冻结时长未设置,需要手动 /unfreeze 或面板解冻。"
        else:
            from neobot_app.runtime.sleep_service import format_sleep_duration

            tail = f"将在 {format_sleep_duration(seconds)}后自动解冻。"
        heading = "已再次确认冻结状态。" if already else "Bot 已冻结。"
        return True, (
            f"{heading}冻结期间群聊与私聊都不回复、不再执行档案自动总结,"
            f"命令系统仍然可用。{tail}"
        )

    def unfreeze(self, *, reason: str = "", operator: str = "") -> tuple[bool, str]:
        """解冻 Bot。返回 (之前是否处于冻结, 提示文本)。"""
        was_frozen = self.is_frozen()
        elapsed = self.frozen_for_seconds()
        self._clear()
        if was_frozen:
            self._logger.info(
                "Bot 已解冻(控制台日志:冻结结束)",
                operator=operator or "unknown",
                reason=reason or "未说明",
                frozen_seconds=elapsed,
                ended_at=epoch_seconds(),
            )
            return True, "Bot 已解冻,恢复正常回复与记忆处理。"
        return False, "Bot 当前没有处于冻结状态。"

    def _clear(self) -> None:
        self._frozen_at = None
        self._frozen_at_monotonic = None
        self._deadline = None
        self._reason = ""
        self._operator = ""


_freeze_service: FreezeService | None = None


def get_freeze_service() -> FreezeService:
    """获取进程内单例;未初始化时惰性创建一个未冻结的实例。"""
    global _freeze_service
    if _freeze_service is None:
        _freeze_service = FreezeService()
    return _freeze_service


def initialize_freeze_service(service: FreezeService) -> None:
    global _freeze_service
    _freeze_service = service

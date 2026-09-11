"""待机状态：只保留最基本的服务，把「不回复」升级为「不运行」。

与旧的运维冻结（已移除）的区别：

- 冻结是「服务全量照跑，只是丢弃消息」——面板、模型、后台任务都还在消耗资源；
- 待机是「停掉 bot 运行时，只留面板/配置/命令等核心服务」——事故中可以真正停火，
  并且因为运行时整体重建，任何配置项都能在待机期生效（软重启运行）。

状态与动作分离：本模块只负责**状态、持久化与通知**，真正的「停运行时 / 重建启动」
由装配层通过回调注入（on_enter / on_resume / on_onebot_change），因此这里不 import
bootstrap，不会形成循环依赖。

重启语义：进程重启后**不会自动恢复待机**（避免「以为在正常跑，其实一直哑火」），
需要开箱即待机请配置 [standby].start_in_standby = true；用户的「待机时是否保持
OneBot 连接」选择会持久化到数据目录的 standby.json。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.time_context import epoch_seconds, from_epoch_seconds

#: 状态取值
RUNNING = "running"
STANDBY = "standby"

#: 生命周期动作：由装配层注入，返回 (是否成功, 提示文案)
StandbyAction = Callable[[], Awaitable[tuple[bool, str]]]
OneBotAction = Callable[[bool], Awaitable[tuple[bool, str]]]


class StandbyService:
    """待机状态机（单事件循环内使用，动作在锁内串行）。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        state_path: Path | None = None,
        connect_onebot: bool = True,
        start_in_standby: bool = False,
        on_enter: StandbyAction | None = None,
        on_resume: StandbyAction | None = None,
        on_onebot_change: OneBotAction | None = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._state_path = Path(state_path) if state_path is not None else None
        self._state = STANDBY if start_in_standby else RUNNING
        self._reason = "启动即待机" if start_in_standby else ""
        self._operator = "config" if start_in_standby else ""
        self._since = epoch_seconds()
        self._connect_onebot = bool(connect_onebot)
        self._on_enter = on_enter
        self._on_resume = on_resume
        self._on_onebot_change = on_onebot_change
        self._lock = asyncio.Lock()
        self._restore()

    # ── 状态查询 ────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    def is_standby(self) -> bool:
        """Bot 是否处于待机状态（待机期不进入回复与记忆管线）。"""
        return self._state == STANDBY

    @property
    def connect_onebot(self) -> bool:
        """待机时是否保持与 OneBot 的连接。"""
        return self._connect_onebot

    def standby_for_seconds(self) -> int:
        if self._state != STANDBY:
            return 0
        return max(0, int(epoch_seconds() - self._since))

    def status(self) -> dict[str, Any]:
        """面板/命令共用的状态快照。"""
        since_text = ""
        if self._since:
            try:
                since_text = from_epoch_seconds(self._since).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                since_text = ""
        return {
            "state": self._state,
            "standby": self._state == STANDBY,
            "reason": self._reason,
            "operator": self._operator,
            "since": self._since,
            "since_text": since_text,
            "standby_seconds": self.standby_for_seconds(),
            "connect_onebot": self._connect_onebot,
        }

    # ── 状态迁移 ────────────────────────────────────────────

    async def enter(self, *, reason: str = "", operator: str = "") -> tuple[bool, str]:
        """进入待机：停掉 bot 运行时，只保留最基本的核心服务。"""
        async with self._lock:
            if self._state == STANDBY:
                if not reason:
                    return True, "Bot 已处于待机状态。"
                self._reason = reason
                self._operator = operator or self._operator
                self._persist()
                return True, f"已更新待机原因：{reason}"
            if self._on_enter is not None:
                ok, detail = await self._on_enter()
                if not ok:
                    self._logger.error(f"进入待机失败: {detail}")
                    return False, detail
            self._state = STANDBY
            self._reason = reason or "未记录原因"
            self._operator = operator
            self._since = epoch_seconds()
            self._persist()
            self._logger.warning(
                "Bot 已进入待机：仅保留面板与核心服务",
                reason=self._reason,
                operator=self._operator,
            )
            return True, (
                f"Bot 已进入待机（{self._reason}，操作者 {self._operator or '未记录'}）："
                "回复与记忆管线已停止，面板与命令仍可用，/reboot 可软重启运行。"
            )

    async def resume(self, *, reason: str = "", operator: str = "") -> tuple[bool, str]:
        """退出待机（软重启运行）：按当前配置重建并启动 bot 运行时。"""
        async with self._lock:
            if self._on_resume is not None:
                ok, detail = await self._on_resume()
                if not ok:
                    self._logger.error(f"软重启运行失败: {detail}")
                    return False, detail
                message = detail
            else:
                message = "Bot 已恢复运行。"
            self._state = RUNNING
            self._reason = ""
            self._operator = operator or ""
            self._since = epoch_seconds()
            self._persist()
            self._logger.warning(
                "Bot 已按新配置软重启运行"
                + (f"（原因：{reason}）" if reason else ""),
                operator=operator or "未记录",
            )
            return True, message

    async def reboot(self, *, reason: str = "", operator: str = "") -> tuple[bool, str]:
        """软重启 bot 运行时：不重启进程、不重建线程，只重建运行时对象。"""
        return await self.resume(reason=reason or "软重启", operator=operator)

    async def set_connect_onebot(
        self, enabled: bool, *, operator: str = ""
    ) -> tuple[bool, str]:
        """设置待机期是否保持 OneBot 连接（立即生效）。"""
        enabled = bool(enabled)
        async with self._lock:
            if enabled == self._connect_onebot:
                return True, "待机期连接设置未变化。"
            if self._on_onebot_change is not None:
                ok, detail = await self._on_onebot_change(enabled)
                if not ok:
                    return False, detail
            self._connect_onebot = enabled
            self._persist()
            if enabled:
                return True, "待机期将保持与 OneBot 的连接（QQ 命令仍可用）。"
            return True, "待机期已断开与 OneBot 的连接（仅面板可用）。"

    # ── 持久化 ──────────────────────────────────────────────

    def _restore(self) -> None:
        """只恢复用户选择（连接开关）；待机状态本身不跨进程恢复。"""
        path = self._state_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            self._logger.warning(f"待机状态文件读取失败: {exc}")
            return
        if isinstance(payload, dict) and "connect_onebot" in payload:
            self._connect_onebot = bool(payload["connect_onebot"])

    def _persist(self) -> None:
        path = self._state_path
        if path is None:
            return
        payload = {
            "state": self._state,
            "reason": self._reason,
            "operator": self._operator,
            "since": self._since,
            "connect_onebot": self._connect_onebot,
        }
        try:
            from neobot_app.utils.atomic import atomic_write_text

            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
        except Exception as exc:
            self._logger.warning(f"待机状态文件写入失败: {exc}")

"""适配器连接就绪探针。

职责只有一个：**观察**适配器当前是否已有框架连入，并把结论作为运行状态交出去。

它刻意不做三件事：
- 不抛异常 —— 「框架还没连上」不是启动失败，而是可恢复的运行状态；
- 不中断启动 —— 反向 WebSocket 服务启动后框架随时可以连入，事件管线会在
  连上的那一刻自然开始工作，不需要任何人重启；
- 不编排启动 —— 启动顺序仍由 NeoBotApplication.start 负责。

超时语义被限制在本模块内：等待窗口只影响「首次观察时愿意等多久」，
不会向上传播成致命错误。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Mapping

from neobot_contracts.ports.logging import Logger, NullLogger


@dataclass(frozen=True, slots=True)
class ConnectionState:
    """一次连接观察的结论。"""

    connected: bool
    waited_seconds: float
    wait_timed_out: bool
    address: str

    def status_text(self) -> str:
        """给运行状态展示用的一句话描述。"""
        if self.connected:
            return f"框架已连接（{self.address}）"
        if self.wait_timed_out:
            return f"等待框架连接 {self.address} 超时，已在后台继续等待"
        return f"等待框架连接 {self.address}"

    def startup_log(self) -> str:
        """启动日志用的一句话描述（不含「超时」这类可能被误读为失败的措辞）。"""
        if self.connected:
            return f"OneBot 框架已连接（{self.address}），事件管线就绪"
        return (
            f"暂未连接 OneBot 框架，反向 WebSocket 服务已在 {self.address} 监听："
            "框架连上后自动开始工作，无需重启"
        )


class ConnectionReadinessProbe:
    """按需等待一次适配器连接建立，返回状态而不是抛错。"""

    def __init__(
        self,
        adapter: Any,
        *,
        logger: Logger | None = None,
        wait_seconds: float = 30.0,
    ) -> None:
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._wait_seconds = max(0.0, float(wait_seconds))

    @property
    def wait_seconds(self) -> float:
        return self._wait_seconds

    def address(self) -> str:
        """监听地址描述：优先反向 WS，其次本地适配器的 HTTP/WS 地址。"""
        getter = getattr(self._adapter, "settings", None)
        settings = getter() if callable(getter) else getter
        if settings is not None:
            return f"ws://{settings.host}:{settings.port}"
        for attr in ("http_url", "ws_url"):
            value = str(getattr(self._adapter, attr, "") or "")
            if value:
                return value
        return "反向 WebSocket 服务"

    def snapshot(self) -> ConnectionState:
        """不等待，直接读当前状态。"""
        return ConnectionState(
            connected=bool(getattr(self._adapter, "connected", False)),
            waited_seconds=0.0,
            wait_timed_out=False,
            address=self.address(),
        )

    async def observe(self) -> ConnectionState:
        """最多等待 ``wait_seconds``，返回观察结论（永不抛错）。"""
        current = self.snapshot()
        if current.connected:
            return current
        timeout = self._wait_seconds if self._wait_seconds > 0 else None
        started = time.monotonic()
        try:
            connected = await asyncio.to_thread(
                self._adapter.wait_for_connection, timeout
            )
        except Exception as exc:
            # 适配器实现异常不应升级为启动失败：记录后按「未连接」处理。
            self._logger.warning(
                "等待框架连接时适配器报错，按未连接继续运行",
                error_type=type(exc).__name__,
                error=str(exc),
            )
            connected = bool(getattr(self._adapter, "connected", False))
        return ConnectionState(
            connected=bool(connected),
            waited_seconds=time.monotonic() - started,
            wait_timed_out=not connected,
            address=self.address(),
        )

    def describe_requirements(self) -> Mapping[str, Any]:
        """诊断信息：把「探针认为需要什么」显式说清楚，便于日志与面板展示。"""
        return {
            "address": self.address(),
            "wait_seconds": self._wait_seconds,
        }

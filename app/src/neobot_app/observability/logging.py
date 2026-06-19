"""Loguru 适配层 — 将 loguru 包装为 contracts.Logger"""

from __future__ import annotations

import asyncio
import logging as stdlib_logging
import sys
from pathlib import Path
from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

_runtime_event_dispatcher: Any = None


def set_runtime_event_dispatcher(dispatcher: Any) -> None:
    global _runtime_event_dispatcher
    _runtime_event_dispatcher = dispatcher


def _loguru_runtime_sink(message: Any) -> None:
    """loguru sink: 将每条日志转成 RuntimeEnvelope 推入事件总线。"""
    dispatch = _runtime_event_dispatcher
    if dispatch is None:
        return
    record = message.record
    envelope = RuntimeEnvelope(
        kind="log",
        stage=record["level"].name.lower(),
        source=str(record["extra"].get("module_name", "")),
        payload={
            "message": record["message"],
            "level": record["level"].name,
            "time": str(record["time"]),
            "module": str(record["extra"].get("module_name", "")),
            "file": record["file"].name,
            "line": record["line"],
            "function": record["function"],
        },
    )
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(lambda: asyncio.ensure_future(dispatch(envelope)))
    except RuntimeError:
        pass


class _InterceptHandler(stdlib_logging.Handler):
    """将 stdlib logging 调用转发到 loguru。"""

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        try:
            level = loguru.logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame = stdlib_logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == stdlib_logging.__file__:
            frame = frame.f_back
            depth += 1
        loguru.logger.bind(module_name=record.name).opt(
            depth=depth, exception=record.exc_info
        ).log(level, record.getMessage())


def configure_loguru(log_dir: Path | None = None, *, runtime_events: bool = False) -> None:
    """配置 Loguru 输出格式。

    移除默认 handler，注册 stderr 和可选的文件 handler。
    同时拦截 stdlib logging 调用，统一路由到 loguru。
    """
    loguru.logger.remove()
    loguru.logger.configure(extra={"module_name": "root"})

    # 拦截所有 stdlib logging，转发到 loguru
    stdlib_logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module_name]: <24}</cyan> | "
        "<level>{message}</level>"
    )
    file_format = console_format + " ({elapsed})"

    loguru.logger.add(
        sys.stderr,
        format=console_format,
        level="DEBUG",
        colorize=True,
    )

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        loguru.logger.add(
            log_dir / "neobot.log",
            format=file_format,
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )

    if runtime_events:
        loguru.logger.add(
            _loguru_runtime_sink,
            level="DEBUG",
        )


class LoguruLoggerAdapter:
    """将 loguru.Logger 适配为 neobot_contracts.Logger 接口"""

    def __init__(self, inner: loguru.Logger) -> None:  # type: ignore[type-arg]
        self._inner = inner

    def bind(self, **ctx: Any) -> LoguruLoggerAdapter:
        return LoguruLoggerAdapter(self._inner.bind(**ctx))

    @staticmethod
    def _format(msg: str, **kw: Any) -> str:
        if not kw:
            return msg
        parts = ", ".join(f"{k}={v}" for k, v in kw.items())
        return f"{msg} | {parts}"

    def debug(self, msg: str, **kw: Any) -> None:
        self._inner.debug(self._format(msg, **kw))

    def info(self, msg: str, **kw: Any) -> None:
        self._inner.info(self._format(msg, **kw))

    def warning(self, msg: str, **kw: Any) -> None:
        self._inner.warning(self._format(msg, **kw))

    def error(self, msg: str, **kw: Any) -> None:
        self._inner.error(self._format(msg, **kw))

    def exception(self, msg: str, **kw: Any) -> None:
        self._inner.exception(self._format(msg, **kw))


class LoguruLoggerFactory:
    """Logger 工厂，按模块名创建绑定了上下文的 Logger"""

    def get_logger(self, module: str) -> Logger:
        return LoguruLoggerAdapter(loguru.logger.bind(module_name=module))

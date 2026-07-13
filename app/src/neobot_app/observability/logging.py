"""Loguru 适配层 — 将 loguru 包装为 contracts.Logger"""

from __future__ import annotations

import asyncio
import logging as stdlib_logging
import sys
import traceback as _traceback
from pathlib import Path
from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

_runtime_event_dispatcher: Any = None
_self_heal_manager: Any = None

# These module-name prefixes produce ERROR-level logs that are transient /
# external-dependency hiccups, not Bot bugs. Filter them out of self-heal
# error accumulation so a flaky OneBot HTTP / vision provider / image fetch
# path does NOT wake the self-heal agent. They still get logged normally.
_SELF_HEAL_EXCLUDE_MODULES = (
    "adapter_receiver",   # API 调用超时 / 没有活跃连接 / 迟到 echo 回填
    "app.image_parse",    # 视觉模型超时 / ReadError / 下载失败
    "app.self_heal",      # 自身日志，避免自激
)


def set_runtime_event_dispatcher(dispatcher: Any) -> None:
    global _runtime_event_dispatcher
    _runtime_event_dispatcher = dispatcher


def register_self_heal_manager(manager: Any) -> None:
    """Register the SelfHealManager so the loguru ERROR sink can feed it.

    The sink hands off each record via call_soon_threadsafe (from loguru's
    logging thread) to the running event loop.  Until a manager is registered
    the sink is a no-op.
    """
    global _self_heal_manager
    _self_heal_manager = manager


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


def _loguru_self_heal_sink(message: Any) -> None:
    """loguru sink: 捕获 ERROR 及以上日志并推入 SelfHealManager。

    在 loguru 的 logging 线程中执行（同步），通过 call_soon_threadsafe
    安全转交主事件循环。自修复 agent 自身日志（module_name 前缀
    'app.self_heal'）会被跳过，避免自激循环。
    """
    mgr = _self_heal_manager
    if mgr is None:
        return
    record = message.record
    module = str(record["extra"].get("module_name", ""))
    if module.startswith("app.self_heal"):
        return
    # 偶发性/外部依赖抖动的错误不应累积进自修复判定。
    # adapter_receiver：API 调用超时 / 没有活跃连接 / 迟到 echo 回填
    #   均为 OneBot 上游瞬时问题，本身已有降级/重连兜底。
    # app.image_parse：视觉模型超时/ReadError/下载失败属于上游抖动或
    #   大图误码，不构成可自愈的 Bug。
    excluded = _SELF_HEAL_EXCLUDE_MODULES
    for prefix in excluded:
        if module.startswith(prefix):
            return
    exc = record.get("exception")
    from neobot_app.time_context import monotonic_seconds as _monotonic
    payload = {
        "time": str(record["time"]),
        "level": record["level"].name,
        "module": module,
        "file": record["file"].name,
        "line": record["line"],
        "function": record["function"],
        "message": record["message"],
        "traceback": (
            "".join(_traceback.format_exception(exc.type, exc.value, exc.tb))
            if exc and exc.type and exc.tb
            else None
        ),
        "_monotonic": _monotonic(),
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop in this thread — loguru calls us from its own
        # worker thread. Try to obtain the main event loop via the asyncio
        # policy fallback.
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
    if loop is None:
        return
    try:
        loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(mgr.record(payload))
        )
    except RuntimeError:
        return


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

    # Self-heal error ingestion sink: feeds the SelfHealManager with ERROR
    # level logs (and above). No-op when no manager has been registered.
    loguru.logger.add(
        _loguru_self_heal_sink,
        level="ERROR",
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

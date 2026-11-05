"""单 Bot 日志装配：Loguru 记录、共享脱敏快照、独立输出。"""

from __future__ import annotations

import asyncio
import logging as stdlib_logging
import sys
from functools import partial
from pathlib import Path
from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

from .log_console import RichConsoleSink
from .log_console import set_console_show_module as set_console_show_module
from .log_delivery import AsyncLogDelivery
from .log_records import normalize_record, plain_record, record_payload
from .log_records import redact_sensitive as redact_sensitive

# 保留原导入入口；脱敏不再依赖控制台/文件 sink 的注册顺序。
_redacting_filter = normalize_record
_runtime_delivery = AsyncLogDelivery()
_self_heal_delivery = AsyncLogDelivery()
_SELF_HEAL_EXCLUDE_MODULES = ("adapter_receiver", "app.image_parse", "app.self_heal")
_STDLIB_FIELDS = set(stdlib_logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def set_runtime_event_dispatcher(dispatcher: Any) -> None:
    _runtime_delivery.set_target(dispatcher)


def register_self_heal_manager(manager: Any) -> None:
    _self_heal_delivery.set_target(manager.record if manager is not None else None)


def bind_logging_loop() -> None:
    """在应用异步启动时绑定主循环，允许适配器线程投递日志。"""
    _runtime_delivery.bind_loop()
    _self_heal_delivery.bind_loop()


async def flush_log_sinks(timeout: float = 2.0) -> bool:
    """有界等待异步出口；超时不取消已在处理的错误/运行时事件。"""
    try:
        async with asyncio.timeout(timeout):
            await asyncio.gather(_runtime_delivery.flush(), _self_heal_delivery.flush())
    except TimeoutError:
        return False
    return True


def log_delivery_stats() -> dict[str, dict[str, int]]:
    return {"runtime": _runtime_delivery.stats(), "self_heal": _self_heal_delivery.stats()}


def _loguru_runtime_sink(message: Any, *, minimum_level: int = 0) -> None:
    payload = record_payload(message.record)
    if payload["fields"].get("event") == "onebot.api.sent":
        _runtime_delivery.submit(
            RuntimeEnvelope(
                kind="metric",
                stage="onebot.api.sent",
                source=payload["module"],
                payload={"action": payload["fields"].get("action", "")},
            )
        )
    if minimum_level and message.record["level"].no < minimum_level:
        return
    _runtime_delivery.submit(
        RuntimeEnvelope(kind="log", stage=payload["level"].lower(), source=payload["module"], payload=payload)
    )


def _loguru_self_heal_sink(message: Any) -> None:
    payload = record_payload(message.record)
    if payload["module"].startswith(_SELF_HEAL_EXCLUDE_MODULES):
        return
    # 严重程度和自修复资格是两个维度，可由明确分类排除用户配置/外部故障。
    if payload["fields"].get("self_heal") is False:
        return
    from neobot_app.time_context import monotonic_seconds

    exception = payload["exception"]
    payload["traceback"] = exception["traceback"] if exception else None
    payload["_monotonic"] = monotonic_seconds()
    _self_heal_delivery.submit(payload)


class _InterceptHandler(stdlib_logging.Handler):
    """接入第三方 stdlib 日志，同时保留 extra、原始调用位置与异常。"""

    def emit(self, record: stdlib_logging.LogRecord) -> None:
        try:
            level = loguru.logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        # Alembic 的逐步迁移/插件枚举保留到 DEBUG 文件，宿主给出一次结果摘要。
        if (
            record.name in {"alembic.runtime.plugins", "alembic.runtime.migration"}
            and record.levelno == stdlib_logging.INFO
        ):
            level = "DEBUG"
        if (
            record.name == "websockets.server"
            and record.levelno == stdlib_logging.INFO
            and record.getMessage().startswith("server listening on")
        ):
            level = "DEBUG"
        fields = {key: value for key, value in record.__dict__.items() if key not in _STDLIB_FIELDS}
        fields.pop("module_name", None)
        fields["_neobot_source"] = {"file": record.pathname, "line": record.lineno, "function": record.funcName}
        loguru.logger.bind(**fields, module_name=record.name).opt(exception=record.exc_info).log(
            level, record.getMessage()
        )


def _file_sink_format(record: dict[str, Any]) -> str:
    record["extra"]["_neobot_text"] = plain_record(record_payload(record))
    # 函数 format 避免 Loguru 自动追加 {exception}，各出口只渲染安全异常一次。
    return "{extra[_neobot_text]}\n"


def configure_loguru(
    log_dir: Path | None = None,
    *,
    runtime_events: bool = False,
    console_level: str = "INFO",
    runtime_level: str = "INFO",
    console_show_module: bool = False,
) -> None:
    """集中注册四个出口：Rich stdout、DEBUG 文件、运行时事件与 ERROR 自修复。"""
    loguru.logger.remove()
    set_console_show_module(console_show_module)
    loguru.logger.configure(extra={}, patcher=normalize_record)
    stdlib_logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    loguru.logger.add(
        RichConsoleSink(sys.stdout),
        format="{message}",
        level=console_level,
        backtrace=False,
        diagnose=False,
        filter=normalize_record,
    )
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        loguru.logger.add(
            log_dir / "neobot.log",
            format=_file_sink_format,
            level="DEBUG",
            rotation="10 MB",
            retention="7 days",
            encoding="utf-8",
            colorize=False,
            backtrace=False,
            diagnose=False,
            filter=normalize_record,
        )
    if runtime_events:
        loguru.logger.add(
            partial(_loguru_runtime_sink, minimum_level=loguru.logger.level(runtime_level).no),
            level="DEBUG",
            format="{message}",
            backtrace=False,
            diagnose=False,
            filter=normalize_record,
        )
    loguru.logger.add(
        _loguru_self_heal_sink,
        level="ERROR",
        format="{message}",
        backtrace=False,
        diagnose=False,
        filter=normalize_record,
    )
    bind_logging_loop()


class LoguruLoggerAdapter:
    """保持 contracts.Logger API；调用字段与 bind 上下文合并，逐次字段优先。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def bind(self, **ctx: Any) -> LoguruLoggerAdapter:
        return LoguruLoggerAdapter(self._inner.bind(**ctx))

    def _log(self, level: str, msg: str, fields: dict[str, Any], *, exception: bool = False) -> None:
        exc_info = fields.pop("exc_info", exception)
        self._inner.bind(**fields).opt(depth=2, exception=exc_info).log(level, msg)

    def debug(self, msg: str, **kw: Any) -> None:
        self._log("DEBUG", msg, kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._log("INFO", msg, kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._log("WARNING", msg, kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._log("ERROR", msg, kw)

    def exception(self, msg: str, **kw: Any) -> None:
        self._log("ERROR", msg, kw, exception=True)


class LoguruLoggerFactory:
    def get_logger(self, module: str) -> Logger:
        return LoguruLoggerAdapter(loguru.logger.bind(module_name=module))

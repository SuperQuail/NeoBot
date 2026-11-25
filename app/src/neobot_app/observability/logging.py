"""单 Bot 日志装配：Loguru 记录、共享脱敏快照、独立输出。"""

from __future__ import annotations

import asyncio
import logging as stdlib_logging
import sys
import time
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
# 逐请求/逐连接的第三方 INFO 只对排障有用：控制台与面板不显示，开启详细日志后才进 DEBUG 文件。
_PER_REQUEST_INFO_LOGGERS = frozenset({"aiohttp.access", "httpx"})
#: 默认不把 DEBUG 写进日志文件的第三方 logger 根名。WebSocket 帧、SQL 回显、
#: 图片解码与 HTTP 头在排障时有用，但平时会以数量级放大日志；需要时用
#: ``[debug].verbose_logging`` 打开（见 ``resolve_verbose_logging``）。
_NOISY_LOGGER_ROOTS = frozenset({"aiosqlite", "websockets", "PIL", "httpcore", "httpx", "urllib3"})
_verbose_logging = False

#: [debug].log_max_total_mb 的默认值：日志目录体积预算 500 MB。
LOG_MAX_TOTAL_MB_DEFAULT = 500
#: 体积预算在写入路径上节流检查：每写一条日志只多一次时钟比较。
_BUDGET_CHECK_INTERVAL_SECONDS = 3600.0
_LOG_CURRENT_NAME = "neobot.log"
_LOG_FILE_PREFIX = "neobot"
_log_budget_dir: Path | None = None
_log_budget_bytes = 0
_log_budget_checked_at = 0.0


def enforce_log_size_budget(log_dir: Path, max_total_bytes: int) -> int:
    """按最旧优先删除轮转日志，直到目录总量回到预算内，返回删除数。

    当前写入中的 neobot.log 永不删除；max_total_bytes <= 0 表示不限制。
    只统计文件名以 neobot 开头的条目，目录里的其它文件不碰。
    """
    if max_total_bytes <= 0:
        return 0
    try:
        entries = list(log_dir.iterdir())
    except OSError:
        return 0
    files: list[tuple[float, int, Path]] = []
    total = 0
    for path in entries:
        try:
            if not path.is_file() or not path.name.startswith(_LOG_FILE_PREFIX):
                continue
            info = path.stat()
        except OSError:
            continue
        files.append((info.st_mtime, info.st_size, path))
        total += info.st_size
    if total <= max_total_bytes:
        return 0
    removed = 0
    for _, size, path in sorted(files):
        if path.name == _LOG_CURRENT_NAME:
            continue
        try:
            path.unlink()
        except OSError:
            continue
        total -= size
        removed += 1
        if total <= max_total_bytes:
            break
    return removed


def set_log_size_budget(max_total_mb: int | None) -> None:
    """登记日志目录体积预算（MB）；0/None/负数表示不限制。

    设置时立刻清一次（启动就能把历史堆积压回预算），之后由文件 sink 每小时检查。
    """
    global _log_budget_bytes, _log_budget_checked_at
    try:
        megabytes = int(max_total_mb or 0)
    except (TypeError, ValueError):
        megabytes = 0
    _log_budget_bytes = max(megabytes, 0) * 1024 * 1024
    _log_budget_checked_at = 0.0
    if _log_budget_bytes and _log_budget_dir is not None:
        _log_budget_checked_at = time.monotonic()
        enforce_log_size_budget(_log_budget_dir, _log_budget_bytes)


def _maybe_enforce_log_budget() -> None:
    """文件 sink 每条记录调用一次：至多每小时扫一次目录执行预算。"""
    global _log_budget_checked_at
    if _log_budget_bytes <= 0 or _log_budget_dir is None:
        return
    now = time.monotonic()
    if _log_budget_checked_at and now - _log_budget_checked_at < _BUDGET_CHECK_INTERVAL_SECONDS:
        return
    _log_budget_checked_at = now
    enforce_log_size_budget(_log_budget_dir, _log_budget_bytes)


def resolve_verbose_logging(debug_cfg: Any, *, recorder_active: bool | None = None) -> bool:
    """把 ``[debug].verbose_logging`` 的 auto/on/off（或布尔值）解析成布尔值。

    auto 跟随**实际生效的** DebugRecorder（``recorder_active``），而不是只读配置：
    recorder 是进程启动时构建的核心对象，软重启不会重建它；只看 ``enabled`` 会让
    「日志说在跟随 Debug 模式、调试包却还是旧状态」。调用方拿不到实际状态时才回退到
    配置值。布尔值与 on/off 等价；配置加载器会把 TOML 布尔转成 ``"True"``/``"False"``，
    所以 true/false 文本也按显式开关处理。未知取值按 auto 处理（配置校验只查类型，不查枚举）。
    """
    raw = getattr(debug_cfg, "verbose_logging", "auto")
    if isinstance(raw, bool):
        return raw
    mode = str(raw or "auto").strip().lower()
    if mode in {"on", "true"}:
        return True
    if mode in {"off", "false"}:
        return False
    if mode != "auto":
        loguru.logger.warning(f"未知的 debug.verbose_logging 取值 {mode!r}，按 auto 处理")
    if recorder_active is None:
        return bool(getattr(debug_cfg, "enabled", False))
    return bool(recorder_active)


def set_verbose_logging(enabled: bool) -> None:
    """切换详细日志：第三方库 DEBUG 是否写进日志文件。运行期可安全调用。"""
    global _verbose_logging
    enabled = bool(enabled)
    if enabled == _verbose_logging:
        return
    _verbose_logging = enabled
    # 留一条分界标记：文件体积突然变化时能直接看出是哪次切换造成的。
    loguru.logger.warning(
        f"详细日志已{'开启' if enabled else '关闭'}：第三方库 DEBUG {'将' if enabled else '不再'}写入日志文件"
    )


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
        # 逐请求 INFO 按等效 DEBUG 归类：先过滤后降级会让 off 时它们绕过开关落盘。
        per_request_info = record.name in _PER_REQUEST_INFO_LOGGERS and record.levelno == stdlib_logging.INFO
        # 过滤放在 stdlib -> loguru 的入口，先于任何 sink 的格式化/脱敏。
        # 当前控制台/面板/自修复的最低级别都 >= INFO，所以等价于「只影响日志文件」；
        # 若以后把这些出口降到 DEBUG，本开关会一并影响它们（见「日志与诊断」文档）。
        if not _verbose_logging and (
            per_request_info
            or (record.levelno < stdlib_logging.INFO and record.name.partition(".")[0] in _NOISY_LOGGER_ROOTS)
        ):
            return
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
        if per_request_info:
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
    # 轮转只负责切文件，总量由体积预算兜底；检查按小时节流，不逐条扫目录。
    _maybe_enforce_log_budget()
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
    global _log_budget_dir
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
        _log_budget_dir = log_dir
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


class VerboseLoggingConsumer:
    """``debug.verbose_logging`` 的热重载消费者。

    只声明自己这个字段：``on``/``off`` 改完重载即生效；``auto`` 跟随的是
    **实际生效的 DebugRecorder**（进程启动时构建，软重启复用），不是配置里的
    ``enabled`` —— 否则会出现「过滤已切换、调试包还是旧状态」的半生效。
    """

    name = "verbose_logging"
    config_paths = ("debug.verbose_logging",)

    def __init__(self, *, recorder_active: bool) -> None:
        self._recorder_active = bool(recorder_active)

    @property
    def hot_reload_policies(self) -> tuple[Any, ...]:
        from neobot_app.config.hot_reload import HotReloadRule

        return (
            HotReloadRule(
                "debug.verbose_logging",
                True,
                "日志过滤是模块级开关，重载后立即生效；auto 跟随实际生效的 DebugRecorder",
            ),
        )

    async def apply_config(self, config: Any) -> None:
        set_verbose_logging(
            resolve_verbose_logging(
                getattr(config, "debug", None),
                recorder_active=self._recorder_active,
            )
        )

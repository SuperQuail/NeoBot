"""Loguru 适配层 — 将 loguru 包装为 contracts.Logger"""

from __future__ import annotations

import asyncio
import logging as stdlib_logging
import re
import sys
import traceback as _traceback
from pathlib import Path
from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

_runtime_event_dispatcher: Any = None
_self_heal_manager: Any = None

_REDACTED = "***REDACTED***"

# 敏感信息脱敏模式：sk- 前缀的 OpenAI 风格 Key，以及常见键值形式的
# key/token/password/secret/authorization/bearer。值边界限定为空白/逗号/分号，
# 避免吞掉相邻内容；纯单词 "token" 等不会被误伤。
#
# 键名允许带前缀（``DEEPSEEK_APIKEY=``、``client_secret=``、``csrf_token=``）：
# 旧写法用 ``\b`` 卡词边界，而下划线是词字符，导致这些形态整类漏脱敏。
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)(?<![A-Za-z0-9])[A-Za-z0-9_]*"
        r"(?:api[_-]?key|apikey|access[_-]?token|auth[_-]?token|token|password|"
        r"passwd|pwd|secret|credential|authorization)"
        r"\s*[=:]\s*(?:(?:bearer|token)\s+)?[^\s,;\"']+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
    # 无分隔符的裸形态：「密码是 hunter2」。值必须含数字且不短于 6 位，
    # 否则会把 "password strength is weak" 这类正常句子一起脱敏。
    re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:password|passwd|pwd|secret|token|api[_-]?key)"
        r"(?:\s+is)?\s*[=:]?\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{6,}"
    ),
    # URL 内嵌凭据：https://user:password@host/...
    re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"),
)

_URL_USERINFO_RE = _REDACTION_PATTERNS[-1]


def redact_sensitive(text: str) -> str:
    """将文本中的常见敏感信息（API Key / token / password 等）替换为 ***REDACTED***。"""
    for pattern in _REDACTION_PATTERNS:
        if pattern is _URL_USERINFO_RE:
            text = pattern.sub(rf"\1{_REDACTED}@", text)
            continue
        text = pattern.sub(_REDACTED, text)
    return text


def _redacting_filter(record: dict[str, Any]) -> bool:
    """loguru filter：在格式化前改写记录，使日志文件输出经过脱敏。

    record 是 loguru 每条日志的共享记录字典；此处替换 message 并接管异常渲染
    （用 stdlib 格式化 traceback 后脱敏，避免 loguru 在诊断模式输出含密钥的
    源码行），后续所有读取该记录的 sink（文件/运行时事件/自修复）都会得到
    脱敏文本。

    不要把 record["exception"] 置 None：文件 sink 之后的自修复 sink 需要
    结构化 traceback（payload["traceback"]）。这里重建一个值已脱敏的异常
    （保留原 traceback 对象）挂回 record；文件 sink 使用 _file_sink_format
    （函数式 format，不含 {exception}）避免 loguru 渲染原始 traceback 的
    未脱敏源码行，密钥不再泄露。

    控制台与文件 sink 都挂这个 filter，且 record 在各 sink 间共享，因此用标记
    保证只执行一次（否则 traceback 会被追加两遍）。
    """
    extra = record.setdefault("extra", {})
    if extra.get("_redaction_applied"):
        return True
    extra["_redaction_applied"] = True
    record["message"] = redact_sensitive(record["message"])
    exc = record.get("exception")
    if not exc:
        return True
    exc_type, exc_value, exc_tb = exc
    if exc_type and exc_tb:
        tb_text = "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
        record["message"] += "\n" + redact_sensitive(tb_text)
    try:
        redacted_value = exc_type(redact_sensitive(str(exc_value)))
    except Exception:
        redacted_value = RuntimeError(redact_sensitive(str(exc_value)))
    record["exception"] = (exc_type, redacted_value, exc_tb)
    return True

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
    """注册 SelfHealManager，使 loguru 的 ERROR sink 能够向它投递记录。

    sink 通过 call_soon_threadsafe（在 loguru 的日志线程中）把每条记录
    交给运行中的事件循环；在注册管理器之前，sink 为空操作。
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
            "message": redact_sensitive(record["message"]),
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
    traceback_text: str | None = None
    if exc:
        exc_type, exc_value, exc_tb = exc
        if exc_type and exc_tb:
            traceback_text = redact_sensitive(
                "".join(_traceback.format_exception(exc_type, exc_value, exc_tb))
            )
    payload = {
        "time": str(record["time"]),
        "level": record["level"].name,
        "module": module,
        "file": record["file"].name,
        "line": record["line"],
        "function": record["function"],
        "message": redact_sensitive(record["message"]),
        "traceback": traceback_text,
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


def _file_sink_format(record: dict[str, Any]) -> str:
    """文件 sink 的格式：以函数形式返回，避免 loguru 对字符串 format 自动追加
    "{exception}"（loguru 渲染原始 traceback 会带未脱敏的源码行）。

    异常信息已由 _redacting_filter 脱敏后追加到 message；record["exception"]
    保持非 None，供文件 sink 之后的自修复 sink 消费结构化 traceback。
    """
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[module_name]: <24}</cyan> | "
        "<level>{message}</level>"
        " ({elapsed})\n"
    )


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

    loguru.logger.add(
        sys.stderr,
        format=console_format,
        level="DEBUG",
        colorize=True,
        # 控制台此前没有挂脱敏 filter：密钥会以明文进 stderr（容器/重定向日志
        # 同样会落盘）。挂上后 record 被改写，后续 sink 也拿到脱敏文本。
        filter=_redacting_filter,
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
            backtrace=True,
            diagnose=False,
            filter=_redacting_filter,
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

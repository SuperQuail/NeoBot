"""Loguru 适配层 — 将 loguru 包装为 contracts.Logger"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger


def configure_loguru(log_dir: Path | None = None) -> None:
    """配置 Loguru 输出格式。

    移除默认 handler，注册 stderr 和可选的文件 handler。
    """
    loguru.logger.remove()
    loguru.logger.configure(extra={"module_name": "root"})

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

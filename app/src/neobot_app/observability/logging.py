"""Loguru 适配层 — 将 loguru 包装为 contracts.Logger"""

from __future__ import annotations

from typing import Any

import loguru

from neobot_contracts.ports.logging import Logger


class LoguruLoggerAdapter:
    """将 loguru.Logger 适配为 neobot_contracts.Logger 协议"""

    def __init__(self, inner: loguru.Logger) -> None:  # type: ignore[type-arg]
        self._inner = inner

    def bind(self, **ctx: Any) -> LoguruLoggerAdapter:
        return LoguruLoggerAdapter(self._inner.bind(**ctx))

    def debug(self, msg: str, **kw: Any) -> None:
        self._inner.debug(msg, **kw)

    def info(self, msg: str, **kw: Any) -> None:
        self._inner.info(msg, **kw)

    def warning(self, msg: str, **kw: Any) -> None:
        self._inner.warning(msg, **kw)

    def error(self, msg: str, **kw: Any) -> None:
        self._inner.error(msg, **kw)

    def exception(self, msg: str, **kw: Any) -> None:
        self._inner.exception(msg, **kw)


class LoguruLoggerFactory:
    """Logger 工厂，按模块名创建绑定了上下文的 Logger"""

    def get_logger(self, module: str) -> Logger:
        return LoguruLoggerAdapter(loguru.logger.bind(module_name=module))

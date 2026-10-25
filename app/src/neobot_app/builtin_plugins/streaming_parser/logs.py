"""日志小工具。

为什么需要它：poller / notify / assets 三处各写过一份「按级别取 logger 方法」的
包装，重复且容易改漏。统一到这里，顺便固定一条纪律——消息一律用 f-string 拼好
再交给宿主 logger，禁止 `logger.info("中文", key=value)`：本体用 loguru，sink 只
渲染 message，kwargs 会被直接丢掉。
"""

from __future__ import annotations

from typing import Any


def log_at(logger: Any, level: str, message: str) -> None:
    """按级别调用宿主 logger；级别不存在或 logger 缺失时静默跳过。"""
    handler = getattr(logger, level, None) if logger is not None else None
    if callable(handler):
        handler(message)

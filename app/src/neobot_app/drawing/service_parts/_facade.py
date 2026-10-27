"""运行时读取门面模块上的可替换依赖（测试 monkeypatch 的挂载点）。

实现拆到 service_parts/* 后，模块级 `from ... import x` 会拿到导入时的旧引用，
绕过测试对 neobot_app.drawing.service 的 monkeypatch；统一经这里在调用时读取。
"""

from __future__ import annotations

import importlib
from typing import Any


def facade() -> Any:
    """返回 neobot_app.drawing.service 门面模块。"""
    return importlib.import_module("neobot_app.drawing.service")

"""内部提示词标签的读取与渲染（数据文件：templates/labels.toml）。

只用于组装提示词时的标签/分隔符/动态附录说明；用户可自定义的提示词分区仍在
``prompts.toml``（见 ``store.py``）。按文件 mtime 缓存解析结果。
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from neobot_app.prompt.render import render_template

LABELS_FILE = Path(__file__).resolve().parent / "templates" / "labels.toml"

_CACHE: tuple[tuple[int, int] | None, dict[str, dict[str, str]]] = (None, {})


def _load() -> dict[str, dict[str, str]]:
    global _CACHE
    try:
        stat = LABELS_FILE.stat()
        signature: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return {}
    cached_signature, cached = _CACHE
    if cached_signature == signature:
        return cached
    try:
        document = tomllib.loads(LABELS_FILE.read_text("utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    sections = {
        str(group): {str(key): str(value) for key, value in body.items()}
        for group, body in document.items()
        if isinstance(body, dict)
    }
    _CACHE = (signature, sections)
    return sections


def label(group: str, key: str, default: str = "") -> str:
    """读取原始标签文本（未渲染）。"""
    return _load().get(group, {}).get(key, default)


def render_label(group: str, key: str, default: str = "", **values: Any) -> str:
    """读取并渲染标签文本；缺失时返回 default。"""
    template = label(group, key, "")
    if not template:
        return default
    return render_template(template, values)

"""四个玩法共用的样式包装。"""

from __future__ import annotations


def _style(css: str) -> str:
    return "<style>" + css + "</style>" if css else ""

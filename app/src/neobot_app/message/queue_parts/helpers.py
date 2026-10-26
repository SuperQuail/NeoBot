"""队列渲染用的小工具。"""

from __future__ import annotations

from typing import Optional


def _safe_int(value: object) -> Optional[int]:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None

def _poke_sub_type_text(sub_type: str) -> str:
    """将 poke 子类型代码转为中文描述，未知时返回'戳一戳'。"""
    mapping = {
        "poke": "戳一戳",
        "show": "比心",
        "heartbeat": "心跳",
        "like": "点赞",
        "fangdajing": "放大镜",
        "break_out": "敲一敲",
        "sixsixsix": "666",
        "rose": "玫瑰",
        "heart": "比心",
    }
    return mapping.get(str(sub_type).lower(), "戳一戳")

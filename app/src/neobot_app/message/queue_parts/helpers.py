"""队列渲染用的小工具。"""

from __future__ import annotations

from typing import Optional


def _identity_str(value: object) -> str:
    """本地身份 ID 归一化（openid 字符串 / QQ 数字）；空值返回空串。

    user/group/session 主键一律按字符串比较：官方 openid 是字母数字串，OneBot
    QQ 号是数字，不能混用 int()/位数判断，否则 openid 会被截成 0 或抛异常。
    """
    if value is None:
        return ""
    return str(value).strip()


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

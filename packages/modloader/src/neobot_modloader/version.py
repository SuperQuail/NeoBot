"""插件声明的最低 NeoBot 版本比较。

``plugin.toml`` / ``Plugin(min_neobot_version=...)`` 声明的是「需要 NeoBot
不低于某版本」。这里只做数字段比较，不引入额外依赖：``1.2.3``、``v1.2``、
``1.2.3-beta.1`` 都能解析（预发布后缀忽略，按 ``1.2.3`` 处理）。
"""

from __future__ import annotations

import re

_VERSION_RE = re.compile(r"^[vV]?(\d+(?:\.\d+)*)")


def parse_version(value: str | None) -> tuple[int, ...] | None:
    """解析版本号为数字元组；无法解析时返回 None。"""
    text = str(value or "").strip()
    match = _VERSION_RE.match(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def version_at_least(host: str | None, minimum: str | None) -> bool | None:
    """判断 ``host`` 是否不低于 ``minimum``。

    Returns:
        True/False 表示可比较的结果；任一版本无法解析时返回 None（调用方
        应跳过检查并记录告警，而不是拒绝加载）。
    """
    host_parts = parse_version(host)
    minimum_parts = parse_version(minimum)
    if host_parts is None or minimum_parts is None:
        return None
    if not any(host_parts):
        # 源码方式运行时 importlib.metadata 取不到发行版本，回落成 0.0.0；
        # 把它当「未知版本」，跳过检查而不是把插件全判成过旧。
        return None
    size = max(len(host_parts), len(minimum_parts))
    padded_host = host_parts + (0,) * (size - len(host_parts))
    padded_minimum = minimum_parts + (0,) * (size - len(minimum_parts))
    return padded_host >= padded_minimum


def incompatible_version_error(
    *,
    name: str,
    host: str | None,
    minimum: str | None,
) -> str | None:
    """返回不满足最低版本时的错误文本；满足或无法比较时返回 None。"""
    if not minimum:
        return None
    satisfied = version_at_least(host, minimum)
    if satisfied is None:
        return None
    if satisfied:
        return None
    return f"插件 {name} 要求 NeoBot >= {minimum}，当前为 {host or '未知'}"

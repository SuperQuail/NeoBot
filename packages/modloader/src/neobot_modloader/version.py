"""版本号解析与比较。

min_neobot_version 与插件依赖声明都只需要「数字段比较」：1.2.3、v1.2、
1.2.3-beta.1 都能解析（预发布后缀忽略，按 1.2.3 处理），不引入
packaging 之类的额外依赖。
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


def _trimmed(parts: tuple[int, ...] | None) -> tuple[int, ...] | None:
    """去掉末尾的 0，让 1.0 与 1.0.0 相等。"""
    if parts is None:
        return None
    trimmed = list(parts)
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed.pop()
    return tuple(trimmed)


def compare_plugin_versions(left: str | None, right: str | None) -> int | None:
    """比较两个插件版本号，返回 -1 / 0 / 1。

    任一版本无法解析、或形如 0.0.0（源码方式运行时拿不到发行版本）时返回
    None，表示「无法比较」——调用方应跳过检查而不是判定为不满足。
    """
    left_parts = _trimmed(parse_version(left))
    right_parts = _trimmed(parse_version(right))
    if left_parts is None or right_parts is None:
        return None
    if not any(left_parts) or not any(right_parts):
        return None
    size = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (size - len(left_parts))
    padded_right = right_parts + (0,) * (size - len(right_parts))
    if padded_left == padded_right:
        return 0
    return 1 if padded_left > padded_right else -1


def version_at_least(host: str | None, minimum: str | None) -> bool | None:
    """判断 host 是否不低于 minimum。

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

"""官方内置插件目录。

随本体分发的插件放在本目录下，运行时作为 official 来源扫描，
与数据目录中的第三方插件区分：官方插件可启停、可重载，但不能安装/更新/卸载。
"""

from __future__ import annotations

from pathlib import Path


def builtin_plugin_dirs() -> tuple[Path, ...]:
    """返回官方插件扫描目录（本目录下的每个子包都是一个官方插件）。"""
    return (Path(__file__).resolve().parent,)


__all__ = ["builtin_plugin_dirs"]

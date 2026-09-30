"""依赖体检：一眼看出「装的是哪个版本、哪个符号缺了、文件在哪」。

背景：新环境部署连续踩到两个坑 —— DrissionPage 5.0.0b1 没有 ChromiumPage、
某个 httpx 没有 AsyncClient。两者都不是代码写错，而是**环境里装的东西和项目假设
不一致**，而报错信息（cannot import name / has no attribute）看不出装的是哪一版。

这个模块给出一条可复制的诊断命令：`neobot doctor`。
"""

from __future__ import annotations

import importlib
import importlib.metadata as metadata
import sys
from typing import Any

#: 每个待检依赖：包名 -> 必须存在的符号（缺任何一个都说明装错了版本）
#: 值里的点号表示属性链（aiohttp 的 web 是子模块，必须 import 之后才挂在包上）
REQUIRED_SYMBOLS: dict[str, tuple[str, ...]] = {
    "DrissionPage": ("ChromiumPage", "ChromiumOptions"),
    "httpx": ("AsyncClient", "Client"),
    "sqlalchemy": ("create_engine",),
    "aiohttp": ("web.Application", "ClientSession"),
    "loguru": ("logger",),
}


def _describe(module_name: str, symbols: tuple[str, ...]) -> dict[str, Any]:
    """导入模块并逐个检查符号；返回一行诊断结果。"""

    row: dict[str, Any] = {
        "module": module_name,
        "distribution": None,
        "version": None,
        "path": None,
        "ok": False,
        "detail": "",
    }
    try:
        row["distribution"] = metadata.distribution(module_name).metadata["Name"]
    except Exception:  # noqa: BLE001 - 有些包名与导入名不同（Pillow vs PIL）
        row["distribution"] = None
    try:
        module = importlib.import_module(module_name)
        # aiohttp.web 这类子模块：只 import 父包时它并不挂在包上，必须先显式导入
        # （项目里真正用的是 aiohttp.web.Application，不能因为探测方式漏报成「缺符号」）。
        for name in symbols:
            if "." in name:
                importlib.import_module(f"{module_name}.{name.split('.', 1)[0]}")
    except Exception as exc:  # noqa: BLE001 - 导入失败本身就是诊断结果
        row["detail"] = f"导入失败：{type(exc).__name__}: {exc}"
        return row
    row["path"] = getattr(module, "__file__", None) or getattr(module, "__path__", None)
    row["version"] = getattr(module, "__version__", None)
    if row["version"] is None and row["distribution"]:
        try:
            row["version"] = metadata.version(row["distribution"])
        except Exception:  # noqa: BLE001
            pass
    missing = [name for name in symbols if _resolve_attr(module, name) is None]
    row["ok"] = not missing
    row["detail"] = "OK" if not missing else ("缺少符号：" + "、".join(missing))
    return row


def _resolve_attr(module: Any, dotted: str) -> Any:
    """按点号链取属性；任一段缺失返回 None（aiohttp.web 这类子模块也适用）。"""

    current = module
    for part in dotted.split("."):
        if not hasattr(current, part):
            return None
        current = getattr(current, part)
    return current


def collect_dependency_report() -> dict[str, Any]:
    """收集第三方依赖与关键运行时信息（不导入本项目任何可选子系统）。"""

    rows = [_describe(name, symbols) for name, symbols in REQUIRED_SYMBOLS.items()]
    return {
        "python": sys.version.replace("\n", " "),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "dependencies": rows,
    }


def format_report(report: dict[str, Any]) -> str:
    """渲染成人类可读的表格（纯文本，便于贴进 issue）。"""

    lines = [
        "NeoBot 依赖体检",
        "=" * 60,
        f"Python      : {report['python']}",
        f"解释器      : {report['executable']}",
        f"环境前缀    : {report['prefix']}",
        "",
        f"{'模块':<16}{'发行包':<18}{'版本':<12}状态",
        "-" * 60,
    ]
    for row in report["dependencies"]:
        lines.append(
            f"{row['module']:<16}{str(row['distribution'] or '-'):<18}"
            f"{str(row['version'] or '-'):<12}{row['detail']}"
        )
        if not row["ok"] and row["path"]:
            lines.append(f"{' ' * 16}路径: {row['path']}")
    bad = [row for row in report["dependencies"] if not row["ok"]]
    lines.append("")
    if bad:
        lines.append(f"结论：{len(bad)} 个依赖不可用 —— 请按上面「缺少符号」的提示处理：")
        for row in bad:
            lines.append(f"  - {row['module']} {row['version'] or '?'}：{row['detail']}")
        lines.append("")
        lines.append("常见修复：uv pip install \"drissionpage>=4.1,<4.2\"（5.x 移除了 ChromiumPage）")
    else:
        lines.append("结论：全部依赖可用 ✔")
    return "\n".join(lines)

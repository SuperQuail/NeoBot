"""CLI 的启动标识与初始化结果；终端使用卡片，重定向输出保持纯文本。"""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .log_console import get_console
from .log_records import redact_sensitive

NEOBOT_BANNER = """
███╗   ██╗███████╗ ██████╗ ██████╗  ██████╗ ████████╗
████╗  ██║██╔════╝██╔═══██╗██╔══██╗██╔═══██╗╚══██╔══╝
██╔██╗ ██║█████╗  ██║   ██║██████╔╝██║   ██║   ██║
██║╚██╗██║██╔══╝  ██║   ██║██╔══██╗██║   ██║   ██║
██║ ╚████║███████╗╚██████╔╝██████╔╝╚██████╔╝   ██║
╚═╝  ╚═══╝╚══════╝ ╚═════╝ ╚═════╝  ╚═════╝    ╚═╝
"""


def display_banner(version: str, *, console: Console | None = None) -> None:
    """只在真实 run 命令进入初始化前调用一次。"""
    output = console or get_console()
    banner = NEOBOT_BANNER.strip("\n")
    if output.is_terminal and output.width < max(map(len, banner.splitlines())):
        banner = "[ NeoBot ]"
    output.print(
        Group(Text(banner, style="bold cyan", no_wrap=True, overflow="ignore"), Text(f"NeoBot {version}", style="dim")),
    )
    output.print()


def display_startup_result(
    *,
    ready: bool,
    version: str,
    duration_seconds: float,
    standby: bool = False,
    dashboard: dict[str, Any] | None = None,
    detail: str = "",
    initializing: bool = False,
    console: Console | None = None,
) -> None:
    """展示已确认的结果；不从配置猜测面板地址或把启动失败称为就绪。"""
    output = console or get_console()
    title = "核心服务就绪 · 待机" if standby else "NeoBot 已就绪"
    status = "Bot 待机；核心服务可用" if standby else "Bot 运行时已启动"
    if initializing:
        title = "WebUI 已就绪"
        status = "基础模块可用；Bot 正在初始化"
    if not ready:
        title = "NeoBot 启动未完成"
        status = "初始化失败；请检查日志"
    dashboard = dashboard or {}
    url = dashboard.get("local_url") if dashboard.get("available") else None
    rows = [
        ("程序版本", version),
        ("启动耗时", f"{duration_seconds:.2f} 秒"),
        ("运行状态", status),
    ]
    if url:
        rows.append(("面板地址", str(url)))
    else:
        reason = str(dashboard.get("reason") or "面板未启用或启动失败")
        rows.append(("面板地址", f"无可用面板（{reason}）"))
    if detail:
        rows.append(("补充说明", str(redact_sensitive(detail))))

    output.print()
    if not output.is_terminal:
        output.print(Text(f"[{title}]"), soft_wrap=True)
        for name, value in rows:
            output.print(Text(f"{name}：{value}"), soft_wrap=True)
        output.print()
        return

    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column(style="dim", width=8, min_width=8, max_width=8, justify="left", no_wrap=True)
    table.add_column(justify="left")
    for name, value in rows:
        style = f"bold cyan link {url}" if name == "面板地址" and url else ""
        table.add_row(Text(name), Text(value, style=style))
    output.print(
        Panel(
            table,
            title=Text(title, style="bold"),
            border_style="green" if ready else "yellow",
            padding=(1, 1),
            expand=True,
        )
    )
    output.print()

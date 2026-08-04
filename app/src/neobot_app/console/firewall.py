"""Windows 防火墙控制台端口放行工具。

背景: Windows 防火墙按"可执行文件完整路径"匹配入站规则。
uv 创建的 venv 里 python.exe 是独立拷贝 (如 .venv\\Scripts\\python.exe),
系统里已有的 python 规则不会覆盖它 → 从外网经路由器转发的入站连接被默认拦截,
表现为"内网可访问、外网不可用"。

本模块提供:
    - 检测指定程序是否有入站允许规则 (读防火墙规则注册表, 只读)
    - 用 netsh 添加入站放行规则 (需管理员权限)
    - 控制台启动时自动检测并输出明确指引
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_FIREWALL_RULES_KEY = (
    r"SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\FirewallRules"
)


def is_windows() -> bool:
    return sys.platform == "win32"


def _parse_rule_value(value: str) -> dict[str, str]:
    """解析防火墙规则注册表值 (V2.28|Action=Allow|App=...|Dir=In|...)。"""
    fields: dict[str, str] = {}
    for part in value.split("|"):
        if "=" in part:
            key, _, field_value = part.partition("=")
            fields[key.strip()] = field_value
    return fields


def has_inbound_allow_rule(program: str | Path) -> bool:
    """检查指定程序是否有"入站 + 允许 + 启用"的防火墙规则 (Windows)。"""
    if not is_windows():
        return True  # 非 Windows 平台无此问题
    program = str(Path(program).resolve()).casefold()
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, _FIREWALL_RULES_KEY
        ) as key:
            count = winreg.QueryInfoKey(key)[1]  # [0]=子键数, [1]=值数 (防火墙规则存于值)
            for index in range(count):
                _name, value, _type = winreg.EnumValue(key, index)
                fields = _parse_rule_value(value)
                if fields.get("Dir", "").casefold() != "in":
                    continue
                if fields.get("Action", "").casefold() != "allow":
                    continue
                if fields.get("Active", "").casefold() != "true":
                    continue
                app = fields.get("App", "")
                if app and str(Path(app).resolve()).casefold() == program:
                    return True
    except OSError:
        return True  # 读不到注册表时保守放行, 不误报
    return False


def add_inbound_allow_rule(program: str | Path, port: int, *, name: str | None = None) -> bool:
    """用 netsh 添加指定程序的 TCP 入站放行规则 (需管理员权限)。

    返回是否添加成功 (命令执行成功即 True)。
    """
    if not is_windows():
        return True
    program = str(Path(program).resolve())
    rule_name = name or f"NeoBot Console {port}"
    command = (
        f'netsh advfirewall firewall add rule name="{rule_name}" '
        f'dir=in action=allow program="{program}" protocol=TCP localport={port}'
    )
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=15, encoding="utf-8", errors="replace",
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def firewall_warning_message(port: int) -> str:
    """生成外网无法访问时的排查提示 (启动日志用)。"""
    program = Path(sys.executable).resolve()
    return (
        f"调试控制台已监听 0.0.0.0:{port}, 但 Windows 防火墙对该程序 "
        f"({program}) 没有入站放行规则, 从外网经路由器转发的连接可能被拦截。\n"
        f"  如外网无法访问, 请以管理员身份执行:\n"
        f"    python -m neobot_app.cli firewall-open --port {port}"
    )


def check_console_firewall(port: int) -> bool:
    """控制台启动后调用: 无放行规则时返回 False (调用方负责记录警告)。"""
    if not is_windows():
        return True
    if has_inbound_allow_rule(sys.executable):
        return True
    # 按端口精确匹配的规则也可能存在 (规则未指定程序, 而是按端口放行)
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _FIREWALL_RULES_KEY) as key:
            count = winreg.QueryInfoKey(key)[1]  # [0]=子键数, [1]=值数 (防火墙规则存于值)
            for index in range(count):
                _name, value, _type = winreg.EnumValue(key, index)
                fields = _parse_rule_value(value)
                if fields.get("Dir", "").casefold() != "in":
                    continue
                if fields.get("Action", "").casefold() != "allow":
                    continue
                if fields.get("Active", "").casefold() != "true":
                    continue
                if str(fields.get("LPort", "")).split(",").__contains__(str(port)):
                    return True
    except OSError:
        return True
    return False

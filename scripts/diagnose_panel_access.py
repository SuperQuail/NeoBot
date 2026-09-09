#!/usr/bin/env python3
"""NeoBot 网页面板连通性排查脚本（单文件、零依赖，只用标准库）。

用途：定位「本机可以访问、远程访问不了」的原因。默认在**服务器本机**运行，
也可以带着 --remote 在**远程机器**上运行，判断卡在哪一层。

用法：
    python diagnose_panel_access.py                    # 本机诊断（自动读 config.toml 的端口）
    python diagnose_panel_access.py --port 9981        # 指定端口
    python diagnose_panel_access.py --host 0.0.0.0     # 指定期望的监听地址
    python diagnose_panel_access.py --remote 1.2.3.4   # 在远程机器上测试连通性
    python diagnose_panel_access.py --remote example.com --port 9981

退出码：0 = 全部检查通过；1 = 存在需要处理的问题。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

TIMEOUT = 5.0
OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"

# 控制台编码兜底：即使终端编码无法表示某个符号也不要让脚本崩掉
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

CONFIG_CANDIDATES = (
    "config.toml",
    "data/config.toml",
    "app/data/config.toml",
    "../config.toml",
    "../data/config.toml",
)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def say(tag: str, message: str) -> None:
    print(f"{tag} {message}")


def section(title: str) -> None:
    print()
    print(f"== {title} " + "=" * max(0, 60 - len(title)))


def run_command(args: list[str], timeout: float = 15.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def is_windows() -> bool:
    return os.name == "nt"


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------


def read_dashboard_config() -> tuple[str | None, int | None, str | None]:
    """从可能的 config.toml 里读 [dashboard] 的 host / port。"""
    data_dir = os.environ.get("NEOBOT_DATA_DIR")
    candidates: list[Path] = []
    if data_dir:
        candidates.append(Path(data_dir) / "config.toml")
    here = Path(__file__).resolve().parent
    for base in (here, here.parent):
        for rel in CONFIG_CANDIDATES:
            candidates.append((base / rel).resolve())

    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        match = re.search(
            r"^\[dashboard\]\s*$([\s\S]*?)(?=^\[|\Z)", text, re.MULTILINE
        )
        if match is None:
            continue
        body = match.group(1)
        host_match = re.search(r'^\s*host\s*=\s*"([^"]*)"', body, re.MULTILINE)
        port_match = re.search(r"^\s*port\s*=\s*(\d+)", body, re.MULTILINE)
        host = host_match.group(1) if host_match else None
        port = int(port_match.group(1)) if port_match else None
        say(INFO, f"已读取配置: {path} -> host={host or '未设置'} port={port or '未设置'}")
        return host, port, str(path)
    say(WARN, "未找到含 [dashboard] 的 config.toml，将使用默认端口 9981（可用 --port 指定）")
    return None, None, None


# ---------------------------------------------------------------------------
# 本机监听检查
# ---------------------------------------------------------------------------


def listening_entries(port: int) -> list[tuple[str, str]]:
    """返回 [(本地地址, 进程信息)]。"""
    entries: list[tuple[str, str]] = []
    if is_windows():
        code, output = run_command(["netstat", "-ano", "-p", "TCP"])
        if code != 0:
            return entries
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local, state, pid = parts[1], parts[3], parts[4] if len(parts) > 4 else ""
            if not local.endswith(f":{port}"):
                continue
            if state.upper() != "LISTENING":
                continue
            entries.append((local.rsplit(":", 1)[0], f"PID {pid}"))
    else:
        code, output = run_command(["ss", "-ltnp"])
        if code != 0:
            code, output = run_command(["netstat", "-ltnp"])
        if code != 0:
            return entries
        for line in output.splitlines():
            if f":{port}" not in line:
                continue
            columns = line.split()
            if len(columns) < 4:
                continue
            local = columns[3] if columns[0].upper() == "LISTEN" else columns[3]
            entries.append((local.rsplit(":", 1)[0], columns[-1] if len(columns) > 5 else ""))
    return entries


def process_path(pid_text: str) -> str:
    """取监听进程的可执行文件路径（用于按程序匹配防火墙规则）。"""
    match = re.search(r"(\d+)", pid_text or "")
    if match is None or not is_windows():
        return ""
    pid = match.group(1)
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    code, output = run_command(
        ps + [f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Path"]
    )
    return output.strip() if code == 0 else ""


def process_name(pid_text: str) -> str:
    match = re.search(r"(\d+)", pid_text or "")
    if match is None:
        return ""
    pid = match.group(1)
    if is_windows():
        code, output = run_command(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"]
        )
        if code == 0 and output.strip():
            return output.strip().split(",")[0].strip('"')
        return ""
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    # UDP 连接法：拿到默认路由使用的本机地址（无需真的发包）
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.5)
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if address not in addresses and not address.startswith("127."):
                addresses.insert(0, address)
    except OSError:
        pass
    return addresses


# ---------------------------------------------------------------------------
# HTTP 探测
# ---------------------------------------------------------------------------


def http_probe(host: str, port: int, path: str = "/healthz") -> tuple[bool, str]:
    """返回 (是否收到 HTTP 响应, 描述)。"""
    import http.client

    try:
        connection = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(200).decode("utf-8", "replace").strip()
        connection.close()
        return True, f"HTTP {response.status} {body[:120]}"
    except Exception as exc:  # noqa: BLE001 - 诊断脚本需要兜住所有异常
        return False, f"{type(exc).__name__}: {exc}"


def tcp_probe(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True, "TCP 连接成功"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# 防火墙检查
# ---------------------------------------------------------------------------


def windows_program_rules(program: str) -> bool:
    """按程序路径查入站允许规则（很多用户只给程序加了规则）。返回是否存在。"""
    if not program:
        return False
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    escaped = program.replace("'", "''")
    script = (
        f"$p='{escaped}'; Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | "
        "ForEach-Object { $r=$_; $a=$r | Get-NetFirewallApplicationFilter; "
        "[pscustomobject]@{Name=$r.DisplayName;Program=$a.Program} } | "
        "Where-Object { $_.Program -eq $p } | ConvertTo-Json -Compress"
    )
    code, output = run_command(ps + [script], timeout=30.0)
    if code != 0 or not output.strip():
        return False
    try:
        parsed = json.loads(output.strip())
        rules = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return False
    if rules:
        say(OK, f"程序 {program} 已有 {len(rules)} 条入站放行规则（与端口规则二选一即可）")
        return True
    return False


def windows_firewall_report(port: int, program: str | None = None) -> bool:
    """返回 True 表示疑似被防火墙拦截。"""
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    script = (
        "Get-NetFirewallProfile | Select-Object Name,Enabled,DefaultInboundAction | "
        "ConvertTo-Json -Compress"
    )
    code, output = run_command(ps + [script])
    profiles: list[dict] = []
    if code == 0 and output.strip():
        try:
            parsed = json.loads(output.strip())
            profiles = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            profiles = []
    if profiles:
        for profile in profiles:
            enabled = bool(profile.get("Enabled"))
            action = str(profile.get("DefaultInboundAction") or "")
            tag = WARN if enabled and action in {"2", "Block", "0"} else INFO
            say(
                tag,
                f"防火墙配置文件 {profile.get('Name')}: 启用={enabled} 默认入站动作={action}"
                "（2/Block 表示未匹配规则一律拒绝）",
            )
    else:
        say(WARN, "无法读取 Windows 防火墙配置（可能未安装 PowerShell 或权限不足）")

    script = (
        "$p=%d; Get-NetFirewallRule -Direction Inbound -Enabled True -Action Allow | "
        "ForEach-Object { $r=$_; $f=$r | Get-NetFirewallPortFilter; $a=$r | Get-NetFirewallApplicationFilter; "
        "[pscustomobject]@{Name=$r.DisplayName;Protocol=$f.Protocol;LocalPort=$f.LocalPort;Program=$a.Program} } | "
        "Where-Object { $_.LocalPort -eq $p -or $_.LocalPort -eq 'Any' } | ConvertTo-Json -Compress"
    ) % port
    code, output = run_command(ps + [script], timeout=30.0)
    rules: list[dict] = []
    if code == 0 and output.strip():
        try:
            parsed = json.loads(output.strip())
            rules = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            rules = []
    if rules:
        for rule in rules[:8]:
            say(
                OK,
                f"入站放行规则: {rule.get('Name')} "
                f"(协议={rule.get('Protocol')} 端口={rule.get('LocalPort')} 程序={rule.get('Program')})",
            )
        say(INFO, f"共找到 {len(rules)} 条允许入站到 TCP {port} 的规则")
        return False
    if windows_program_rules(program or ""):
        return False
    say(
        FAIL,
        f"没有找到允许入站 TCP {port} 的 Windows 防火墙规则 —— 这通常就是远程无法访问的原因",
    )
    say(
        INFO,
        f'修复（管理员 CMD/PowerShell）：netsh advfirewall firewall add rule '
        f'name="NeoBot Dashboard {port}" dir=in action=allow protocol=TCP localport={port}',
    )
    say(INFO, f"或使用自带命令：neobot firewall-open --port {port}")
    return True


def linux_firewall_report(port: int) -> bool:
    """返回 True 表示疑似被防火墙拦截。"""
    suspect = False
    code, output = run_command(["ufw", "status"])
    if code == 0:
        say(INFO, f"ufw 状态: {output.strip().splitlines()[0] if output.strip() else '未知'}")
        if "inactive" not in output and f"{port}" not in output:
            say(WARN, f"ufw 规则里没有看到端口 {port}（如 ufw 已启用，请执行: sudo ufw allow {port}/tcp）")
            suspect = True
    code, output = run_command(["firewall-cmd", "--state"])
    if code == 0 and "running" in output:
        code, ports = run_command(["firewall-cmd", "--list-ports"])
        if code == 0 and f"{port}/tcp" not in ports:
            say(WARN, f"firewalld 未放行 {port}/tcp（执行: sudo firewall-cmd --permanent --add-port={port}/tcp && sudo firewall-cmd --reload）")
            suspect = True
    code, output = run_command(["iptables", "-S"])
    if code == 0 and output:
        say(INFO, "已读取 iptables 规则（如使用云主机，还需检查云平台安全组）")
    return suspect


# ---------------------------------------------------------------------------
# 本机诊断
# ---------------------------------------------------------------------------


def diagnose_local(port: int, expected_host: str | None) -> int:
    problems = 0

    section("1. 本机监听状态")
    entries = listening_entries(port)
    if not entries:
        say(FAIL, f"没有进程在监听 TCP {port} —— 面板没起来或端口被改过")
        say(INFO, "检查启动日志里「网页面板已启动」这一行给出的实际端口；端口冲突时会向后顺延")
        problems += 1
    else:
        for local, pid_text in entries:
            name = process_name(pid_text)
            label = local or "?"
            if label in {"0.0.0.0", "::", "[::]"}:
                say(OK, f"监听 {label}:{port}（全部网卡）{('进程: ' + name) if name else pid_text}")
            elif label.startswith("127.") or label == "::1":
                say(FAIL, f"监听 {label}:{port}（仅本机回环，远程必然连不上）")
                say(INFO, '把 config.toml 的 [dashboard].host 改成 "0.0.0.0" 后重启 NeoBot')
                problems += 1
            else:
                say(WARN, f"监听 {label}:{port}（只绑定了单个地址）{('进程: ' + name) if name else pid_text}")
                say(INFO, '如果远程用的是别的网卡地址，请把 host 改为 "0.0.0.0"')
                problems += 1
    if expected_host and expected_host not in {"0.0.0.0", "::", "127.0.0.1", "localhost"}:
        say(INFO, f"配置里的 host = {expected_host}（注意：这不是 0.0.0.0，只监听该地址）")

    section("2. 本机回环访问")
    ok, detail = http_probe("127.0.0.1", port)
    say(OK if ok else FAIL, f"GET http://127.0.0.1:{port}/healthz -> {detail}")
    if not ok:
        problems += 1

    section("3. 通过本机局域网地址访问（验证是否真的绑定到网卡）")
    addresses = local_ipv4_addresses()
    if not addresses:
        say(WARN, "没有探测到非回环 IPv4 地址")
    any_failed = False
    for address in addresses:
        ok, detail = http_probe(address, port)
        say(OK if ok else WARN, f"GET http://{address}:{port}/healthz -> {detail}")
        any_failed = any_failed or not ok
    if any_failed:
        say(INFO, "有地址不通通常说明服务只监听了 127.0.0.1（虚拟网卡地址不通可忽略）")
        say(INFO, "注意：本机访问自己的局域网 IP 不经过防火墙，因此这里通了也不代表外网能通")

    section("4. 防火墙 / 安全组")
    program = ""
    for _local, pid_text in entries:
        program = process_path(pid_text)
        if program:
            break
    if is_windows():
        firewall_suspect = windows_firewall_report(port, program or None)
    else:
        firewall_suspect = linux_firewall_report(port)
    say(INFO, "云服务器（阿里云/腾讯云/AWS 等）还需在控制台安全组放行 TCP 端口，脚本无法检测这一层")
    if firewall_suspect:
        problems += 1

    section("结论")
    if problems == 0:
        say(OK, "本机侧检查通过：端口已监听、回环与局域网地址均能访问、防火墙未见拦截")
        say(INFO, "若远程仍无法访问，请优先检查：")
        say(INFO, "  1) 云平台安全组 / 路由器端口转发是否放行")
        say(INFO, f"  2) 远程是否使用了正确的地址与端口（本机地址：{', '.join(addresses) or '未知'}）")
        say(INFO, f"  3) 在远程机器上执行：python diagnose_panel_access.py --remote <服务器IP> --port {port}")
    elif firewall_suspect and problems == 1:
        say(FAIL, "端口已监听且本机可访问，但缺少防火墙放行规则 —— 这就是「本地能访问、远程访问不了」的最常见原因")
        say(INFO, f'在服务器上以管理员身份执行：netsh advfirewall firewall add rule '
                   f'name="NeoBot Dashboard {port}" dir=in action=allow protocol=TCP localport={port}')
        say(INFO, "云服务器还需在控制台安全组放行该端口")
    else:
        say(FAIL, f"发现 {problems} 个问题，请按上面的提示处理后再试")
    return 0 if problems == 0 else 1


# ---------------------------------------------------------------------------
# 远程诊断
# ---------------------------------------------------------------------------


def diagnose_remote(host: str, port: int) -> int:
    problems = 0

    section("1. 解析目标地址")
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = sorted({info[4][0] for info in infos})
        say(OK, f"{host} -> {', '.join(addresses)}")
    except Exception as exc:  # noqa: BLE001
        say(FAIL, f"无法解析 {host}: {exc}")
        return 1

    section("2. TCP 连通性")
    ok, detail = tcp_probe(host, port)
    say(OK if ok else FAIL, f"TCP {host}:{port} -> {detail}")
    if not ok:
        problems += 1
        say(INFO, "TCP 连不上说明包没到达服务，常见原因：")
        say(INFO, "  · 服务器防火墙未放行该端口（Windows: netsh advfirewall firewall add rule ...）")
        say(INFO, "  · 云平台安全组 / 路由器未放行")
        say(INFO, '  · 面板只监听了 127.0.0.1（在服务器上运行本脚本不带 --remote 即可确认）')
        say(INFO, "  · 端口写错（面板端口冲突时会向后顺延，以启动日志为准）")
        say(INFO, "  · 服务器不在同一网络 / 需要 VPN")

    section("3. HTTP 响应")
    for path in ("/healthz", "/"):
        ok, detail = http_probe(host, port, path)
        say(OK if ok else FAIL, f"GET http://{host}:{port}{path} -> {detail}")
        if not ok:
            problems += 1

    section("结论")
    if problems == 0:
        say(OK, "远程可达：TCP 与 HTTP 均正常")
        say(INFO, "若浏览器仍打不开，请检查浏览器代理、HTTPS 强制跳转与访问的 URL 是否带 base_path")
    else:
        say(FAIL, f"发现 {problems} 个问题，按上面提示在服务器侧排查")
    return 0 if problems == 0 else 1


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="NeoBot 网页面板连通性排查")
    parser.add_argument("--port", type=int, default=None, help="面板端口（默认读 config.toml，读不到用 9981）")
    parser.add_argument("--host", default=None, help="期望的监听地址（可选，仅用于提示）")
    parser.add_argument("--remote", default=None, help="远程机器上运行时填服务器 IP/域名")
    args = parser.parse_args()

    config_host, config_port, config_path = read_dashboard_config()
    port = args.port or config_port or 9981
    host = args.host or config_host

    print("NeoBot 网页面板连通性排查")
    print(f"时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"模式: {'远程连通性测试' if args.remote else '本机诊断'}")
    print(f"端口: {port}" + (f"（来自 {config_path}）" if config_port == port and config_path else ""))
    if args.remote:
        print(f"目标: {args.remote}:{port}")

    if args.remote:
        return diagnose_remote(args.remote, port)
    return diagnose_local(port, host)


if __name__ == "__main__":
    sys.exit(main())

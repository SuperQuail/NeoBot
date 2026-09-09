#!/usr/bin/env python3
"""NeoBot 网页面板连通性排查脚本（单文件、零依赖，只用标准库）。

定位「本机可以访问、远程访问不了」的原因。默认在**服务器本机**运行，
也可以带 --remote 在**远程机器**上运行，判断卡在哪一层。

性能约束：整轮检查有硬性总预算（默认 60 秒，--timeout 可调），
每一步都单独限时；任何一步卡住或超时都会被跳过并继续，不会浪费时间。

用法：
    python diagnose_panel_access.py                       # 本机诊断（自动读 config.toml 端口）
    python diagnose_panel_access.py --port 9981           # 指定端口
    python diagnose_panel_access.py --timeout 30          # 收紧总预算到 30 秒
    python diagnose_panel_access.py --remote 1.2.3.4      # 在远程机器上测连通性
    python diagnose_panel_access.py --public-ip 1.2.3.4   # 跳过联网探测，直接给出公网出口 IP

退出码：0 = 未发现阻塞问题；1 = 发现问题或检查未完成。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

OK, FAIL, WARN, INFO = "[OK]  ", "[FAIL]", "[WARN]", "[INFO]"
DEFAULT_BUDGET = 60.0
MAX_LAN_PROBES = 4

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass


class Budget:
    """全局时间预算：保证整轮检查不会超时浪费。"""

    def __init__(self, total: float) -> None:
        self.total = max(5.0, float(total))
        self.started = time.monotonic()
        self.deadline = self.started + self.total

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def step(self, want: float) -> float:
        """本步可用超时；返回 0 表示预算已耗尽。"""
        return min(float(want), self.remaining())

    def expired(self) -> bool:
        return self.remaining() <= 0.05

    def elapsed(self) -> float:
        return time.monotonic() - self.started


BUDGET = Budget(DEFAULT_BUDGET)


def say(tag: str, message: str) -> None:
    print(f"{tag} {message}")


def section(title: str) -> None:
    print()
    print(f"== {title} " + "=" * max(0, 60 - len(title)))


def run_command(args: list[str], timeout: float) -> tuple[int, str]:
    """执行外部命令；超时/失败返回 (127, 错误信息)，绝不抛出。"""
    if timeout <= 0:
        return 127, "timeout budget exhausted"
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return 124, f"命令超时（{timeout:.0f}s）: {args[0]}"
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"
    return completed.returncode, (completed.stdout or "") + (completed.stderr or "")


def is_windows() -> bool:
    return os.name == "nt"


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------

CONFIG_CANDIDATES = (
    "config.toml",
    "data/config.toml",
    "app/data/config.toml",
    "../config.toml",
    "../data/config.toml",
    "../app/data/config.toml",
)


def read_dashboard_config() -> tuple[str | None, int | None, str | None]:
    """从可能的 config.toml 里读 [dashboard] 的 host / port。"""
    candidates: list[Path] = []
    data_dir = os.environ.get("NEOBOT_DATA_DIR")
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
    say(WARN, "未找到含 [dashboard] 的 config.toml，使用默认端口 9981（可用 --port 指定）")
    return None, None, None


# ---------------------------------------------------------------------------
# 监听 / 地址
# ---------------------------------------------------------------------------


def listening_entries(port: int) -> list[tuple[str, str]]:
    """返回 [(本地监听地址, 进程信息)]。"""
    entries: list[tuple[str, str]] = []
    timeout = BUDGET.step(8.0)
    if is_windows():
        code, output = run_command(["netstat", "-ano", "-p", "TCP"], timeout)
        if code != 0:
            say(WARN, f"读取监听状态失败: {output[:120]}")
            return entries
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 4 or parts[0].upper() != "TCP":
                continue
            local, state = parts[1], parts[3]
            if not local.endswith(f":{port}") or state.upper() != "LISTENING":
                continue
            pid = parts[4] if len(parts) > 4 else ""
            entries.append((local.rsplit(":", 1)[0], f"PID {pid}"))
    else:
        code, output = run_command(["ss", "-ltnp"], timeout)
        if code != 0:
            code, output = run_command(["netstat", "-ltnp"], timeout)
        if code != 0:
            say(WARN, f"读取监听状态失败: {output[:120]}")
            return entries
        for line in output.splitlines():
            if f":{port}" not in line:
                continue
            columns = line.split()
            if len(columns) < 4:
                continue
            entries.append((columns[3].rsplit(":", 1)[0], columns[-1] if len(columns) > 5 else ""))
    return entries


def process_name(pid_text: str) -> str:
    match = re.search(r"(\d+)", pid_text or "")
    if match is None:
        return ""
    pid = match.group(1)
    if is_windows():
        code, output = run_command(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], BUDGET.step(6.0)
        )
        if code == 0 and output.strip():
            return output.strip().split(",")[0].strip('"')
        return ""
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def process_path(pid_text: str) -> str:
    """取监听进程的可执行路径（用于按程序匹配防火墙规则）。"""
    match = re.search(r"(\d+)", pid_text or "")
    if match is None or not is_windows():
        return ""
    pid = match.group(1)
    ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
    code, output = run_command(
        ps + [f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Path"],
        BUDGET.step(8.0),
    )
    return output.strip() if code == 0 else ""


def local_ipv4_addresses() -> list[str]:
    addresses: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address not in addresses and not address.startswith("127."):
                addresses.append(address)
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.3)
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if address not in addresses and not address.startswith("127."):
                addresses.insert(0, address)
    except OSError:
        pass
    return addresses[:MAX_LAN_PROBES]


# ---------------------------------------------------------------------------
# 网络探测
# ---------------------------------------------------------------------------


def http_probe(host: str, port: int, path: str = "/healthz") -> tuple[bool, str]:
    import http.client

    timeout = BUDGET.step(4.0)
    if timeout <= 0:
        return False, "跳过（时间预算已用完）"
    try:
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read(200).decode("utf-8", "replace").strip()
        connection.close()
        return True, f"HTTP {response.status} {body[:120]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def tcp_probe(host: str, port: int, timeout: float | None = None) -> tuple[bool, str]:
    timeout = BUDGET.step(6.0) if timeout is None else timeout
    if timeout <= 0:
        return False, "跳过（时间预算已用完）"
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"{(time.perf_counter() - started) * 1000:.0f} ms"
    except socket.timeout:
        return False, "超时（丢包，多为防火墙/安全组丢弃）"
    except ConnectionRefusedError:
        return False, "拒绝（RST，主机可达但端口无服务）"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Windows 防火墙（COM 一次枚举，约 0.1-1 秒；不用 CIM 的 N+1 查询）
# ---------------------------------------------------------------------------

_WINDOWS_FIREWALL_PS = """
$p = __PORT__
function Test-PortMatch([string]$spec, [string]$port) {
    if (-not $spec) { return $false }
    foreach ($part in ($spec -split ',')) {
        $part = $part.Trim()
        if ($part -eq $port) { return $true }
        if ($part -match '^(\\d+)-(\\d+)$') {
            $low = [int]$Matches[1]; $high = [int]$Matches[2]; $target = [int]$port
            if ($target -ge $low -and $target -le $high) { return $true }
        }
    }
    return $false
}
$fw = New-Object -ComObject HNetCfg.FwPolicy2
$profiles = @()
foreach ($t in @(1, 2, 4)) {
    $name = switch ($t) { 1 { 'Domain' } 2 { 'Private' } 4 { 'Public' } }
    $profiles += [pscustomobject]@{
        Name = $name
        Enabled = [bool]$fw.FirewallEnabled($t)
        DefaultInbound = [int]$fw.DefaultInboundAction($t)
    }
}
$active = @(Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Select-Object Name, NetworkCategory)
$exact = @(); $broad = @()
foreach ($r in $fw.Rules) {
    if (-not $r.Enabled) { continue }
    if ($r.Direction -ne 1) { continue }
    if ($r.Action -ne 1) { continue }
    $proto = [int]$r.Protocol
    if ($proto -ne 6 -and $proto -ne 256) { continue }
    $lp = [string]$r.LocalPorts
    if (Test-PortMatch $lp ([string]$p)) {
        $exact += [pscustomobject]@{ Name = $r.Name; Profiles = [int]$r.Profiles; Program = [string]$r.ApplicationName; Ports = $lp }
    } elseif ($lp -eq 'Any' -or $lp -eq '*') {
        $broad += [pscustomobject]@{ Name = $r.Name; Profiles = [int]$r.Profiles; Program = [string]$r.ApplicationName }
    }
}
$json = [pscustomobject]@{ Profiles = @($profiles); Active = @($active); Exact = @($exact); Broad = @($broad) } |
    ConvertTo-Json -Depth 4 -Compress
"""


def _profile_covers(mask: int, active_profiles: set[str]) -> bool:
    """Windows 防火墙 Profiles 位掩码：1=Domain 2=Private 4=Public，0x7FFFFFFF=全部。"""
    if mask in {0, 0x7FFFFFFF, -1}:
        return True
    bits = {"Domain": 1, "Private": 2, "Public": 4}
    if not active_profiles:
        return True
    return any(mask & bits.get(name, 0) for name in active_profiles)


def windows_firewall_report(port: int, program: str | None = None) -> bool:
    """返回 True 表示疑似被防火墙拦截。任何异常都只提示、不阻塞。"""
    timeout = BUDGET.step(15.0)
    if timeout <= 0:
        say(WARN, "时间预算不足，跳过防火墙检查")
        return False
    # 结果写 UTF-8 临时文件再读回：避免 PowerShell stdout 代码页把中文规则名弄坏
    import tempfile

    with tempfile.TemporaryDirectory(prefix="neobot-fw-") as tmp:
        out_path = Path(tmp) / "rules.json"
        ps = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]
        script = (
            _WINDOWS_FIREWALL_PS.replace("__PORT__", str(port))
            + f"\n$json | Set-Content -LiteralPath '{out_path}' -Encoding UTF8\n"
        )
        code, output = run_command(ps + [script], timeout)
        if not out_path.is_file():
            say(WARN, f"防火墙检查跳过: {(output or 'PowerShell 不可用').strip()[:120]}")
            return False
        raw = out_path.read_text(encoding="utf-8-sig", errors="replace").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        say(WARN, f"防火墙信息解析失败，跳过（{exc}）")
        return False

    profiles = data.get("Profiles") or []
    if isinstance(profiles, dict):
        profiles = [profiles]
    active_entries = data.get("Active") or []
    if isinstance(active_entries, dict):
        active_entries = [active_entries]
    # Get-NetConnectionProfile 的 NetworkCategory：0=Public 1=Private 2=DomainAuthenticated
    alias = {
        "0": "Public",
        "1": "Private",
        "2": "Domain",
        "Public": "Public",
        "Private": "Private",
        "DomainAuthenticated": "Domain",
    }
    active_profiles = {
        alias.get(str(item.get("NetworkCategory")), "Public") for item in active_entries
    }
    active_profiles = {name for name in active_profiles if name}
    if active_profiles:
        say(INFO, f"当前活动网络配置文件: {', '.join(sorted(active_profiles))}")

    enabled_for_active = False
    for profile in profiles:
        name = str(profile.get("Name") or "")
        enabled = bool(profile.get("Enabled"))
        action = int(profile.get("DefaultInbound") or 0)
        is_active = name in active_profiles
        blocking = enabled and action == 2
        if is_active and enabled:
            enabled_for_active = True
        say(
            WARN if (blocking and is_active) else INFO,
            f"防火墙 {name}: 启用={enabled} 默认入站={'阻止' if action == 2 else '允许'}"
            + ("  <- 当前生效" if is_active else ""),
        )

    exact = [r for r in (data.get("Exact") or []) if _profile_covers(int(r.get("Profiles") or 0), active_profiles)]
    broad = [r for r in (data.get("Broad") or []) if _profile_covers(int(r.get("Profiles") or 0), active_profiles)]

    if program:
        program_rules = [
            r for r in broad + exact if str(r.get("Program") or "").lower() == program.lower()
        ]
        if program_rules:
            say(OK, f"程序 {program} 已有入站放行规则（{program_rules[0].get('Name')}）")
            return False

    if exact:
        for rule in exact[:5]:
            say(OK, f"已放行 TCP {port}: {rule.get('Name')} 程序={rule.get('Program') or 'Any'}")
        say(INFO, f"共 {len(exact)} 条针对 TCP {port} 的入站放行规则")
        return False

    if not enabled_for_active:
        say(INFO, "当前活动网络配置文件的防火墙未启用：拦截更可能来自云安全组或上游设备")
        return True

    if broad:
        say(WARN, f"存在 {len(broad)} 条「端口=Any」的宽泛入站规则，通常不覆盖公网入站，不能据此判断已放行")
    say(FAIL, f"没有找到允许入站 TCP {port} 的 Windows 防火墙规则")
    say(
        INFO,
        f'修复（管理员 CMD/PowerShell）：netsh advfirewall firewall add rule '
        f'name="NeoBot Dashboard {port}" dir=in action=allow protocol=TCP localport={port}',
    )
    say(INFO, f"或使用自带命令：neobot firewall-open --port {port}")
    return True


def linux_firewall_report(port: int) -> bool:
    suspect = False
    code, output = run_command(["ufw", "status"], BUDGET.step(6.0))
    if code == 0:
        say(INFO, f"ufw 状态: {output.strip().splitlines()[0] if output.strip() else '未知'}")
        if "inactive" not in output and str(port) not in output:
            say(WARN, f"ufw 未放行 {port}（sudo ufw allow {port}/tcp）")
            suspect = True
    code, output = run_command(["firewall-cmd", "--state"], BUDGET.step(6.0))
    if code == 0 and "running" in output:
        code, ports = run_command(["firewall-cmd", "--list-ports"], BUDGET.step(6.0))
        if code == 0 and f"{port}/tcp" not in ports:
            say(WARN, f"firewalld 未放行 {port}/tcp（sudo firewall-cmd --permanent --add-port={port}/tcp）")
            suspect = True
    return suspect


# ---------------------------------------------------------------------------
# 公网出口 / NAT
# ---------------------------------------------------------------------------


def public_ip_report(local_addresses: list[str], public_ip: str | None) -> str | None:
    if public_ip:
        say(INFO, f"公网出口 IP（命令行指定）: {public_ip}")
        return public_ip
    import http.client

    for host, path in (("api.ipify.org", "/?format=json"), ("ifconfig.me", "/ip")):
        timeout = BUDGET.step(6.0)
        if timeout <= 0:
            break
        try:
            connection = http.client.HTTPSConnection(host, timeout=timeout)
            connection.request("GET", path)
            response = connection.getresponse()
            body = response.read(200).decode("utf-8", "replace").strip()
            connection.close()
            if response.status != 200 or not body:
                continue
            detected = body
            if detected.startswith("{"):
                detected = str(json.loads(detected).get("ip") or "")
            detected = detected.strip()
            if detected:
                say(INFO, f"公网出口 IP: {detected}")
                return detected
        except Exception:  # noqa: BLE001
            continue
    say(INFO, "未能获取公网出口 IP（无外网/代理受限）；可用 --public-ip 手动指定")
    return None


def nat_warning(local_addresses: list[str], public_ip: str | None, port: int) -> bool:
    if not public_ip:
        return False
    if public_ip in local_addresses:
        say(INFO, "公网 IP 直接绑定在本机：远程访问只需放行防火墙/安全组")
        return False
    say(
        WARN,
        f"本机处于 NAT 之后：本机地址 {', '.join(local_addresses) or '未知'}，公网出口 {public_ip}",
    )
    say(INFO, f"远程访问 {public_ip}:{port} 需要上游做端口映射：")
    say(INFO, f"  · 云服务器（华为云/阿里云/腾讯云/AWS 等）：控制台【安全组】添加入方向规则，"
              f"协议 TCP、端口 {port}、源 0.0.0.0/0（或只放行你的出口 IP）")
    say(INFO, "  · 家用/公司路由器：端口转发（外部端口 -> 内网 IP:端口），并确认运营商未封禁该端口")
    return True


# ---------------------------------------------------------------------------
# 本机诊断
# ---------------------------------------------------------------------------


def diagnose_local(port: int, expected_host: str | None, public_ip_arg: str | None) -> int:
    problems = 0

    section("1. 本机监听状态")
    entries = listening_entries(port)
    if not entries:
        say(FAIL, f"没有进程在监听 TCP {port} —— 面板没起来或端口被改过")
        say(INFO, "以启动日志中「网页面板已启动」那行的端口为准（端口冲突会向后顺延）")
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
                say(WARN, f"监听 {label}:{port}（只绑定单个地址）{('进程: ' + name) if name else pid_text}")
                problems += 1
    if expected_host and expected_host not in {"0.0.0.0", "::", "127.0.0.1", "localhost"}:
        say(INFO, f"配置里 host = {expected_host}（不是 0.0.0.0，只监听该地址）")

    section("2. 本机回环访问")
    ok, detail = http_probe("127.0.0.1", port)
    say(OK if ok else FAIL, f"GET http://127.0.0.1:{port}/healthz -> {detail}")
    if not ok:
        problems += 1

    section("3. 通过本机局域网地址访问")
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
        say(INFO, "本机访问自己的局域网 IP 不经过防火墙，这里通了也不代表外网能通")

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
    say(INFO, "脚本只能检查本机侧；云平台安全组 / 路由器端口映射需自行确认")

    section("5. 公网出口 / NAT")
    public_ip = public_ip_report(addresses, public_ip_arg)
    nat_suspect = nat_warning(addresses, public_ip, port)

    if firewall_suspect:
        problems += 1
    if nat_suspect:
        problems += 1

    section("结论")
    if problems == 0:
        say(OK, "本机侧检查通过：端口已监听、回环与局域网地址均能访问、未见本机侧拦截")
        say(INFO, f"远程仍打不开时，在远程机器上执行："
                  f"python diagnose_panel_access.py --remote <服务器IP> --port {port}")
        say(INFO, "重点确认云平台安全组 / 路由器端口映射，以及远程使用的地址是否正确")
    elif nat_suspect:
        say(FAIL, f"面板本身正常，但本机在 NAT 之后：远程必须由上游把 {port} 端口映射进来")
        say(INFO, f"公网地址 {public_ip or '未知'} -> 内网 {', '.join(addresses) or '未知'}:{port}")
        say(INFO, f"云服务器：控制台【安全组】添加入方向规则（TCP / {port} / 0.0.0.0/0）")
        say(INFO, "家用路由器：做端口转发，并确认运营商未封禁该端口")
        if firewall_suspect:
            say(INFO, "另外本机防火墙也缺少该端口规则，建议一并添加")
    elif firewall_suspect:
        say(FAIL, "端口已监听且本机可访问，但缺少防火墙放行规则 —— 这是「本机能访问、远程访问不了」的常见原因")
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
        say(INFO, "  · 服务器防火墙未放行（Windows: netsh advfirewall firewall add rule ...）")
        say(INFO, "  · 云平台安全组 / 路由器端口转发未放行")
        say(INFO, "  · 面板只监听了 127.0.0.1（在服务器上不带 --remote 运行本脚本确认）")
        say(INFO, "  · 端口写错（端口冲突时会向后顺延，以启动日志为准）")
        if "超时" in detail:
            say(INFO, "  · 超时=丢包：多为安全组/防火墙丢弃；拒绝(RST)=主机可达但无服务")

    section("3. HTTP 响应")
    for path in ("/healthz", "/"):
        ok, detail = http_probe(host, port, path)
        say(OK if ok else FAIL, f"GET http://{host}:{port}{path} -> {detail}")
        if not ok:
            problems += 1

    section("结论")
    if problems == 0:
        say(OK, "远程可达：TCP 与 HTTP 均正常")
        say(INFO, "若浏览器仍打不开，检查浏览器代理、HTTPS 跳转与访问 URL 是否带 base_path")
    else:
        say(FAIL, f"发现 {problems} 个问题，请按上面提示在服务器侧排查")
    return 0 if problems == 0 else 1


# ---------------------------------------------------------------------------


def main() -> int:
    global BUDGET
    parser = argparse.ArgumentParser(description="NeoBot 网页面板连通性排查")
    parser.add_argument("--port", type=int, default=None, help="面板端口（默认读 config.toml，读不到用 9981）")
    parser.add_argument("--host", default=None, help="期望的监听地址（可选，仅用于提示）")
    parser.add_argument("--remote", default=None, help="远程机器上运行时填服务器 IP/域名")
    parser.add_argument("--public-ip", default=None, help="本机公网出口 IP（跳过联网探测）")
    parser.add_argument("--timeout", type=float, default=DEFAULT_BUDGET, help=f"整轮检查总预算秒数（默认 {DEFAULT_BUDGET:g}）")
    parser.add_argument("--no-pause", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    BUDGET = Budget(args.timeout)

    config_host, config_port, config_path = read_dashboard_config()
    port = args.port or config_port or 9981
    host = args.host or config_host

    print("NeoBot 网页面板连通性排查")
    print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}  总预算: {BUDGET.total:.0f}s")
    print(f"模式: {'远程连通性测试' if args.remote else '本机诊断'}")
    print(f"端口: {port}" + (f"（来自 {config_path}）" if config_port == port and config_path else ""))
    if args.remote:
        print(f"目标: {args.remote}:{port}")

    try:
        if args.remote:
            code = diagnose_remote(args.remote, port)
        else:
            code = diagnose_local(port, host, args.public_ip)
    except KeyboardInterrupt:
        print()
        say(WARN, "已中断")
        return 1
    print()
    print(f"耗时: {BUDGET.elapsed():.1f}s")
    return code


if __name__ == "__main__":
    sys.exit(main())

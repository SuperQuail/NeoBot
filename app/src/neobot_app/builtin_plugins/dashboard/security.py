"""面板安全：会话、限速与脱敏。

设计要点：
- 登录凭据是面板密码（app/src/neobot_app/panel_auth.py 负责存储与校验），
  未设置密码时不允许外网访问，只能从本机进入设置流程。
- 会话使用内存随机 token + HttpOnly Cookie，并绑定 CSRF token；写操作必须带 X-CSRF-Token。
- 会话记录创建时的密码 revision，密码被修改后旧会话立即失效。
- 登录按 IP 限速，超过阈值临时锁定，防公网暴力破解。
- 所有对外输出都经过脱敏，避免把 API Key 写进日志/接口响应。
"""

from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

SENSITIVE_KEY_RE = re.compile(r"(?i)(api[_-]?key|access[_-]?key|token|password|secret|credential|authorization|cookie)")
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret|authorization)"
        r"\b\s*[=:]\s*(?:(?:bearer|token)\s+)?[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
)


def redact(text: Any) -> str:
    """把文本中的密钥类内容替换为 ***。"""
    value = str(text if text is not None else "")
    for pattern in _REDACTION_PATTERNS:
        value = pattern.sub("***", value)
    return value


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key or "")))


def mask_secret(value: str, *, keep: int = 4) -> str:
    """保留首尾少量字符用于辨认，其余打码（仅用于日志，禁止用于接口响应）。"""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep * 2:
        return "*" * len(text)
    return f"{text[:keep]}{'*' * 8}{text[-keep:]}"


#: 密钥占位符：前端只能看到它，真实值永远不出网、也不落盘
SECRET_PLACEHOLDER = "••••••••"


def has_secret_value(data: Any) -> bool:
    """判断（嵌套）配置里是否存在非空的敏感字段。"""
    if isinstance(data, dict):
        for key, value in data.items():
            if is_sensitive_key(key) and isinstance(value, str) and value.strip():
                return True
            if has_secret_value(value):
                return True
        return False
    if isinstance(data, (list, tuple)):
        return any(has_secret_value(item) for item in data)
    return False


def mask_mapping(data: Any) -> Any:
    """递归打码：键名命中敏感规则的字符串值替换为占位符。"""
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            name = str(key)
            if is_sensitive_key(name) and isinstance(value, str) and value:
                masked[name] = SECRET_PLACEHOLDER
            else:
                masked[name] = mask_mapping(value)
        return masked
    if isinstance(data, (list, tuple)):
        return [mask_mapping(item) for item in data]
    return data


def restore_mapping(submitted: Any, original: Any) -> Any:
    """保存时把占位符/空值还原成原值（仅敏感键）。

    - 提交的敏感键等于占位符或空字符串：沿用原值（原值不存在则删除该键）；
    - 提交了新的非空值：以新值为准（只能更新，不能读取）。
    """
    if isinstance(submitted, dict):
        base = original if isinstance(original, dict) else {}
        restored: dict[str, Any] = {}
        for key, value in submitted.items():
            name = str(key)
            if is_sensitive_key(name) and isinstance(value, str):
                if value == SECRET_PLACEHOLDER or not value.strip():
                    previous = base.get(name)
                    if isinstance(previous, str) and previous:
                        restored[name] = previous
                    continue
                restored[name] = value
                continue
            restored[name] = restore_mapping(value, base.get(name))
        return restored
    if isinstance(submitted, list):
        base_list = original if isinstance(original, list) else []
        return [
            restore_mapping(item, base_list[index] if index < len(base_list) else None)
            for index, item in enumerate(submitted)
        ]
    return submitted


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(str(left or ""), str(right or ""))


def client_ip(request: Any, *, trust_proxy: bool = False) -> str:
    """解析客户端地址；仅在显式信任代理时使用转发头。

    XFF 取**最右**一项而不是最左：最左是客户端自己可以随意伪造的（浏览器/脚本
    发一个 ``X-Forwarded-For: 127.0.0.1`` 就变成了「本机访问」，从而绕过
    auth_setup 的「仅本机可设置密码」与 allow_remote_manage=false 的远程限制）。
    最右一项由我们信任的那一跳代理追加，客户端无法控制。
    """
    if trust_proxy:
        for header in ("X-Forwarded-For", "X-Real-IP"):
            raw = request.headers.get(header)
            if raw:
                candidate = raw.split(",")[-1].strip()
                if candidate:
                    return candidate
    peer = request.transport.get_extra_info("peername") if request.transport else None
    if isinstance(peer, (tuple, list)) and peer:
        return str(peer[0])
    return str(request.remote or "")


def is_loopback(ip: str) -> bool:
    normalized = str(ip or "").strip()
    if normalized in {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}:
        return True
    return normalized.startswith("127.")


def _strip_scope(text: str) -> str:
    """去掉 IPv6 的 zone id（``fe80::1%eth0``）：ipaddress 只接受纯地址。"""
    return str(text or "").strip().split("%", 1)[0]


def parse_client_address(ip: str) -> Any:
    """把客户端地址解析成 ip_address；无法解析返回 None。

    双栈套接字（``host = "::"``）上，IPv4 客户端会以 ``::ffff:a.b.c.d`` 出现。
    这里统一还原成 IPv4，否则白名单里写 ``192.168.1.5`` 永远匹配不上。
    """
    text = _strip_scope(ip)
    if not text:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def parse_ip_network(entry: str) -> Any:
    """把白名单条目解析成网络；裸 IP 等价于单主机前缀（/32 或 /128）。

    用 ``strict=False``：允许写 ``192.168.1.5/24`` 这类「主机位非零」的简写，
    按 ``192.168.1.0/24`` 处理 —— 用户写它的意图显然是「这个网段」。
    """
    text = _strip_scope(entry)
    if not text:
        return None
    try:
        return ipaddress.ip_network(text, strict=False)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class IpAllowList:
    """面板的客户端来源 IP 白名单。

    语义有三条，改动时别破任何一条：

    1. ``entries`` 为空 => **不限制**（默认行为，升级后老部署表现不变）；
    2. 回环地址**始终放行** —— 白名单是能把自己锁在门外的配置，而面板正是修复入口，
       所以本机永远是逃生通道；
    3. 解析不了的条目**不等于放行**：它只是永远匹配不上。于是「白名单写成乱码」
       的结果是除本机外全拒（fail-closed）。

    第 3 条与 ``validate_plugin_config`` 的「非法配置回落默认值」叠加时会翻转成
    fail-open（整个字段被丢弃 => 空列表 => 放行所有），所以配置模型的校验器
    **刻意不因条目不可解析而抛错**，只在 ``invalid`` 里记账、由启动日志告警。
    """

    entries: tuple[str, ...] = ()
    networks: tuple[Any, ...] = ()
    invalid: tuple[str, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.entries)

    def allows(self, ip: str) -> bool:
        if not self.enabled:
            return True
        if is_loopback(ip):
            return True
        address = parse_client_address(ip)
        if address is None:
            return False
        return any(address in network for network in self.networks)

    def describe(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "entries": list(self.entries),
            "invalid": list(self.invalid),
        }


def build_ip_allow_list(entries: Iterable[Any] | None) -> IpAllowList:
    """把配置条目编译成可匹配的网络列表：去空白、按出现顺序去重、分开记账非法项。"""
    kept: list[str] = []
    networks: list[Any] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for entry in entries or ():
        text = str(entry or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        kept.append(text)
        network = parse_ip_network(text)
        if network is None:
            invalid.append(text)
            continue
        networks.append(network)
    return IpAllowList(tuple(kept), tuple(networks), tuple(invalid))


@dataclass(slots=True)
class Session:
    token: str
    csrf_token: str
    created_at: float
    last_seen_at: float
    ip: str = ""
    user_agent: str = ""
    password_revision: int = 0

    def touch(self, *, timeout_seconds: float) -> bool:
        now = time.time()
        if now - self.last_seen_at > timeout_seconds:
            return False
        self.last_seen_at = now
        return True

    def to_payload(self, *, timeout_seconds: float) -> dict[str, Any]:
        return {
            "ip": self.ip,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
            "expires_in": max(0, int(timeout_seconds - (time.time() - self.last_seen_at))),
        }


class SessionStore:
    """内存会话表（重启即失效，令牌仍是唯一长期凭据）。"""

    def __init__(self, *, timeout_seconds: float, max_sessions: int = 64) -> None:
        self._timeout = float(timeout_seconds)
        self._max_sessions = int(max_sessions)
        self._sessions: dict[str, Session] = {}

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    def create(self, *, ip: str = "", user_agent: str = "", password_revision: int = 0) -> Session:
        self.prune()
        if len(self._sessions) >= self._max_sessions:
            oldest = min(self._sessions.values(), key=lambda item: item.last_seen_at)
            self._sessions.pop(oldest.token, None)
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(24),
            created_at=now,
            last_seen_at=now,
            ip=ip,
            user_agent=user_agent[:200],
            password_revision=int(password_revision),
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None, *, password_revision: int | None = None) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if password_revision is not None and session.password_revision != int(password_revision):
            # 密码已被修改：旧会话立即失效
            self._sessions.pop(token, None)
            return None
        if not session.touch(timeout_seconds=self._timeout):
            self._sessions.pop(token, None)
            return None
        return session

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        return self._sessions.pop(token, None) is not None

    def revoke_all(self) -> int:
        count = len(self._sessions)
        self._sessions.clear()
        return count

    def prune(self) -> None:
        now = time.time()
        for token in [token for token, session in self._sessions.items() if now - session.last_seen_at > self._timeout]:
            self._sessions.pop(token, None)

    def has_recent_activity(self, window_seconds: float) -> bool:
        """是否存在「最近 window_seconds 秒内活动过」的会话（面板延迟探针的门控条件）。

        必须是**只读**的：绝不能走 get()，否则 touch() 会把会话自我续期，
        于是只要探针在跑，会话就永远不会过期，门控形同虚设。
        """
        try:
            window = float(window_seconds)
        except (TypeError, ValueError):
            return False
        if window <= 0:
            return False
        now = time.time()
        return any(now - session.last_seen_at <= window for session in self._sessions.values())

    def describe(self) -> list[dict[str, Any]]:
        self.prune()
        return [
            {"token": session.token[:6] + "…", **session.to_payload(timeout_seconds=self._timeout)}
            for session in sorted(self._sessions.values(), key=lambda item: item.last_seen_at, reverse=True)
        ]


@dataclass(slots=True)
class LoginLimiter:
    """按 IP 统计登录失败次数，超限后临时锁定。"""

    max_failures: int = 5
    window_seconds: float = 600.0
    _failures: dict[str, list[float]] = field(default_factory=dict)

    def _recent(self, ip: str, now: float) -> list[float]:
        stamps = [item for item in self._failures.get(ip, []) if now - item < self.window_seconds]
        if stamps:
            self._failures[ip] = stamps
        else:
            self._failures.pop(ip, None)
        return stamps

    def is_locked(self, ip: str) -> tuple[bool, int]:
        now = time.time()
        stamps = self._recent(ip, now)
        if len(stamps) < self.max_failures:
            return False, 0
        remaining = int(self.window_seconds - (now - min(stamps))) + 1
        return True, max(1, remaining)

    def record_failure(self, ip: str) -> None:
        now = time.time()
        stamps = self._recent(ip, now)
        stamps.append(now)
        self._failures[ip] = stamps

    def reset(self, ip: str) -> None:
        self._failures.pop(ip, None)

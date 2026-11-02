"""DSH daemon 网关的线协议模型（v1）。

开发机 daemon 出站轮询时，一个同步周期是::

    POST /dsh/daemon/sync
    {
      "v": 1,
      "daemon_id": "devbox-01",
      "seq": 7,
      "cursor": 6,
      "reports": [
        {"id": "r-1", "kind": "task.event", "task_id": "t-1",
         "payload": {"status": "running"}, "created_at": 1760000000.0}
      ],
      "acks": ["c-0"],
      "health": {"sessions": 2}
    }

    {
      "v": 1,
      "daemon_id": "devbox-01",
      "cursor": 7,
      "commands": [
        {"id": "c-1", "kind": "task.dispatch", "task_id": "t-1", "payload": {...}}
      ]
    }

语义约定：

- 报告按 ``(daemon_id, seq)`` 幂等：daemon 重发同一个 seq 时不再重复投递。
- 响应里的 ``cursor`` 是「服务端已处理的最后 seq」；请求里的 ``cursor`` 只是
  daemon 带回来的观察值，服务端不依赖它去重。
- 命令是「先下发、后 ack」：网关把下发的命令记入待确认表，daemon 在下一次请求的
  ``acks`` 里带上命令 id 才算完成；未 ack 的命令每轮重发（按首次下发顺序），
  因此 daemon 崩溃/断线不会丢命令。未知或重复的 ack 一律忽略。
- daemon 重启后如果 seq 从 0 重新开始，必须换一个新的 daemon_id（例如带上 boot
  id），否则同一 daemon_id 的低 seq 会被当成重发忽略。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: 线协议版本；不兼容变更必须 +1，并在服务端显式拒绝旧版本。
PROTOCOL_VERSION = 1

#: 单次同步最多携带的报告条数：超过按非法请求拒绝，避免单请求撑爆内存。
MAX_REPORTS_PER_SYNC = 500

#: 单次同步最多携带的命令确认条数；超出的请求按非法输入拒绝。
MAX_ACKS_PER_SYNC = 256

#: daemon_id / report id / task_id 的最长字符数。
MAX_ID_LENGTH = 128

#: 报告种类名的最长字符数。
MAX_KIND_LENGTH = 64

_MISSING = object()


class GatewayProtocolError(ValueError):
    """请求不符合线协议；``code`` 是稳定、机器可读的错误码。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(slots=True)
class SyncReport:
    """daemon 上报的一条语义事件（不绑定具体工具/会话实现）。"""

    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = ""
    task_id: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "task_id": self.task_id,
            "payload": dict(self.payload),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class DaemonCommand:
    """服务端下发给 daemon 的一条命令。"""

    id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    task_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "task_id": self.task_id,
            "payload": dict(self.payload),
        }


@dataclass(slots=True)
class SyncRequest:
    """一次同步请求（已通过 :func:`parse_sync_request` 校验）。"""

    daemon_id: str
    seq: int
    cursor: int = 0
    #: 上一轮下发给 daemon 的命令 id；网关据此从 pending 中移除。
    acks: list[str] = field(default_factory=list)
    reports: list[SyncReport] = field(default_factory=list)
    health: dict[str, Any] = field(default_factory=dict)
    v: int = PROTOCOL_VERSION


@dataclass(slots=True)
class SyncResponse:
    """同步响应：``cursor`` 为该 daemon 已处理的最后 seq，``commands`` 为本轮下发。"""

    daemon_id: str
    cursor: int
    commands: list[DaemonCommand] = field(default_factory=list)
    v: int = PROTOCOL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "v": self.v,
            "daemon_id": self.daemon_id,
            "cursor": self.cursor,
            "commands": [command.to_dict() for command in self.commands],
        }


def _read_str(
    mapping: dict[str, Any],
    key: str,
    *,
    code: str,
    label: str,
    required: bool = False,
    max_length: int = MAX_ID_LENGTH,
) -> str:
    value = mapping.get(key, "")
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise GatewayProtocolError(code, f"{label} 必须是字符串")
    text = value.strip()
    if required and not text:
        raise GatewayProtocolError(code, f"{label} 不能为空")
    if len(text) > max_length:
        raise GatewayProtocolError(code, f"{label} 过长（最多 {max_length} 字符）")
    return text


def _read_int(
    mapping: dict[str, Any],
    key: str,
    *,
    code: str,
    label: str,
    minimum: int = 0,
    default: Any = _MISSING,
) -> int:
    value = mapping.get(key, _MISSING)
    if value is _MISSING:
        if default is _MISSING:
            raise GatewayProtocolError(code, f"缺少必需字段 {label}")
        return int(default)
    # bool 是 int 的子类，JSON 的 true/false 不能当成 seq/cursor。
    if isinstance(value, bool) or not isinstance(value, int):
        raise GatewayProtocolError(code, f"{label} 必须是整数")
    if value < minimum:
        raise GatewayProtocolError(code, f"{label} 不能小于 {minimum}")
    return value


def _read_number(
    mapping: dict[str, Any],
    key: str,
    *,
    code: str,
    label: str,
    default: float = 0.0,
) -> float:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GatewayProtocolError(code, f"{label} 必须是数字")
    return float(value)


def _parse_report(item: Any, index: int) -> SyncReport:
    code = "invalid_reports"
    prefix = f"reports[{index}]"
    if not isinstance(item, dict):
        raise GatewayProtocolError(code, f"{prefix} 必须是对象")
    kind = _read_str(
        item,
        "kind",
        code=code,
        label=f"{prefix}.kind",
        required=True,
        max_length=MAX_KIND_LENGTH,
    )
    report_id = _read_str(item, "id", code=code, label=f"{prefix}.id")
    task_id = _read_str(item, "task_id", code=code, label=f"{prefix}.task_id")
    payload = item.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise GatewayProtocolError(code, f"{prefix}.payload 必须是对象")
    created_at = _read_number(item, "created_at", code=code, label=f"{prefix}.created_at")
    return SyncReport(
        kind=kind,
        payload=dict(payload),
        id=report_id,
        task_id=task_id,
        created_at=created_at,
    )


def _parse_acks(payload: dict[str, Any]) -> list[str]:
    """解析已下发命令的确认列表；空/缺省表示没有要确认的命令。"""
    raw_acks = payload.get("acks", [])
    if raw_acks is None:
        raw_acks = []
    if not isinstance(raw_acks, list):
        raise GatewayProtocolError("invalid_acks", "acks 必须是数组")
    if len(raw_acks) > MAX_ACKS_PER_SYNC:
        raise GatewayProtocolError(
            "invalid_acks",
            f"acks 最多 {MAX_ACKS_PER_SYNC} 条",
        )
    acks: list[str] = []
    for index, item in enumerate(raw_acks):
        if not isinstance(item, str) or not item.strip():
            raise GatewayProtocolError("invalid_acks", f"acks[{index}] 必须是非空字符串")
        command_id = item.strip()
        if len(command_id) > MAX_ID_LENGTH:
            raise GatewayProtocolError(
                "invalid_acks",
                f"acks[{index}] 过长（最多 {MAX_ID_LENGTH} 字符）",
            )
        acks.append(command_id)
    return acks


def parse_sync_request(payload: Any) -> SyncRequest:
    """解析并校验同步请求；非法输入一律抛 :class:`GatewayProtocolError`。"""
    if not isinstance(payload, dict):
        raise GatewayProtocolError("invalid_body", "请求体必须是 JSON 对象")
    version = _read_int(
        payload,
        "v",
        code="unsupported_version",
        label="v",
        default=PROTOCOL_VERSION,
    )
    if version != PROTOCOL_VERSION:
        raise GatewayProtocolError(
            "unsupported_version",
            f"不支持的协议版本 v={version}，本机只支持 v={PROTOCOL_VERSION}",
        )
    daemon_id = _read_str(
        payload,
        "daemon_id",
        code="invalid_daemon_id",
        label="daemon_id",
        required=True,
    )
    seq = _read_int(payload, "seq", code="invalid_seq", label="seq")
    cursor = _read_int(payload, "cursor", code="invalid_cursor", label="cursor", default=0)
    acks = _parse_acks(payload)

    raw_reports = payload.get("reports", [])
    if raw_reports is None:
        raw_reports = []
    if not isinstance(raw_reports, list):
        raise GatewayProtocolError("invalid_reports", "reports 必须是数组")
    if len(raw_reports) > MAX_REPORTS_PER_SYNC:
        raise GatewayProtocolError(
            "too_many_reports",
            f"reports 最多 {MAX_REPORTS_PER_SYNC} 条",
        )
    reports = [_parse_report(item, index) for index, item in enumerate(raw_reports)]

    raw_health = payload.get("health", {})
    if raw_health is None:
        raw_health = {}
    if not isinstance(raw_health, dict):
        raise GatewayProtocolError("invalid_health", "health 必须是对象")

    return SyncRequest(
        daemon_id=daemon_id,
        seq=seq,
        cursor=cursor,
        acks=acks,
        reports=reports,
        health=dict(raw_health),
        v=version,
    )


__all__ = [
    "DaemonCommand",
    "GatewayProtocolError",
    "MAX_ACKS_PER_SYNC",
    "MAX_ID_LENGTH",
    "MAX_KIND_LENGTH",
    "MAX_REPORTS_PER_SYNC",
    "PROTOCOL_VERSION",
    "SyncReport",
    "SyncRequest",
    "SyncResponse",
    "parse_sync_request",
]

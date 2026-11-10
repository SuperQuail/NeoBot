"""官方模式的 OneBot action 分发。

只映射官方接口真实具备的能力：发送、登录信息、版本信息与状态；没有等价接口的
列表/资料查询返回 ok + 空数据/本地缓存，其余明确返回 failed + 中文原因，避免
调用方把「官方协议做不到」误当成「暂时失败」反复重试。
"""

from __future__ import annotations

from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME
from neobot_contracts.ports.speaking import SpeechBlocked

from neobot_adapter.model import response

_SEND_ACTIONS = frozenset({"send_group_msg", "send_private_msg", "send_msg"})
_LIST_ACTIONS = frozenset(
    {
        "get_group_list",
        "get_friend_list",
        "get_group_member_list",
        "get_group_member_info",
        "get_stranger_info",
        "get_robot_uin_range",
    }
)
_PROTOCOL_VERSION = "qq-official-v2"


async def dispatch(
    adapter: Any,
    action: str,
    params: dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """执行一个 OneBot action，返回 OneBot 形状的响应 dict。"""
    name = str(action or "").strip()
    values = params if isinstance(params, dict) else {}
    try:
        if name in _SEND_ACTIONS:
            return await _send(adapter, name, values, timeout)
        if name == "get_login_info":
            return await _get_login_info(adapter)
        if name == "get_version_info":
            return _ok(
                {
                    "app_name": OFFICIAL_ADAPTER_APP_NAME,
                    "app_version": _app_version(),
                    "protocol_version": _PROTOCOL_VERSION,
                }
            )
        if name == "get_status":
            return _ok(_status(adapter))
        if name == "get_msg":
            return _get_msg(adapter, values)
        if name == "delete_msg":
            # 官方 v2 没有撤回接口；明确失败比假装成功更安全。
            return _failed("QQ 官方机器人协议没有消息撤回接口，delete_msg 不可用")
        if name == "get_forward_msg":
            return _failed("QQ 官方机器人协议没有合并转发消息查询接口")
        if name in _LIST_ACTIONS:
            return _list_data(adapter, name, values)
    except SpeechBlocked:
        # 发言策略拒绝不是接口失败，必须原样抛给调用方（与 OneBot/Local 一致）。
        raise
    except Exception as exc:
        return _failed(f"官方协议处理 {name} 失败：{type(exc).__name__}: {exc}")
    return _failed(f"官方协议模式不支持该操作：{name}（QQ 官方机器人接口没有等价能力）")


# ── 发送 ────────────────────────────────────────────────────────────


async def _send(
    adapter: Any,
    action: str,
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    kind, target = _send_target(action, params)
    if kind is None or target in (None, ""):
        return _failed(f"{action} 缺少目标参数（group_id / user_id）")
    message = params.get("message", "")
    result: response.SendMsgResponse = await adapter.send(
        ConversationRef(kind=kind, id=str(target)),
        message,
        timeout=timeout,
    )
    return result.model_dump()


def _send_target(action: str, params: dict[str, Any]) -> tuple[str | None, Any]:
    if action == "send_group_msg":
        return "group", params.get("group_id")
    if action == "send_private_msg":
        return "private", params.get("user_id")
    message_type = str(params.get("message_type") or "").strip()
    if message_type == "group":
        return "group", params.get("group_id")
    if message_type == "private":
        return "private", params.get("user_id")
    if params.get("group_id") is not None:
        return "group", params.get("group_id")
    if params.get("user_id") is not None:
        return "private", params.get("user_id")
    return None, None


# ── 身份/状态 ───────────────────────────────────────────────────────


async def _get_login_info(adapter: Any) -> dict[str, Any]:
    await adapter.ensure_robot_identity()
    return _ok(
        {
            "user_id": int(getattr(adapter, "robot_uin", 0) or 0),
            "nickname": str(getattr(adapter, "robot_nickname", "") or ""),
        }
    )


def _status(adapter: Any) -> dict[str, Any]:
    connected = bool(getattr(adapter, "connected", False))
    return {
        "online": connected,
        "good": connected,
        "app_initialized": True,
        "app_enabled": connected,
        "stat": {"message_received": 0, "message_sent": 0},
    }


def _app_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("neobot-adapter")
    except PackageNotFoundError:
        return ""


# ── 只读列表/资料 ───────────────────────────────────────────────────


def _list_data(adapter: Any, action: str, params: dict[str, Any]) -> dict[str, Any]:
    if action == "get_group_list":
        return _ok(list(adapter.known_groups.values()))
    if action == "get_friend_list":
        return _ok([])
    if action == "get_group_member_list":
        return _ok([])
    if action == "get_group_member_info":
        return _group_member_info(adapter, params)
    if action == "get_stranger_info":
        return _stranger_info(adapter, params)
    # get_robot_uin_range：官方模式没有 UIN 段概念，空列表即可。
    return _ok([])


def _group_member_info(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id = _as_int(params.get("group_id"))
    user_id = _as_int(params.get("user_id"))
    user = adapter.known_users.get(user_id) if user_id else None
    if user is None:
        return _ok(None)
    return _ok(
        {
            "group_id": group_id,
            "user_id": user_id,
            "nickname": user.get("nickname", ""),
            "card": "",
            "role": "member",
        }
    )


def _stranger_info(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    user_id = _as_int(params.get("user_id"))
    user = adapter.known_users.get(user_id) if user_id else None
    if user is None:
        return _ok({"user_id": user_id, "nickname": ""})
    return _ok(dict(user))


def _get_msg(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    message_id = _as_int(params.get("message_id"))
    event = adapter.get_recent_message(message_id) if message_id else None
    if event is None:
        return _failed("官方协议不提供历史消息查询接口，且该消息不在本地最近消息缓存中")
    return _ok(event)


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "retcode": 0, "message": "", "wording": "", "data": data}


def _failed(message: str, *, retcode: int = 1404) -> dict[str, Any]:
    return {
        "status": "failed",
        "retcode": retcode,
        "message": message,
        "wording": message,
        "data": None,
    }

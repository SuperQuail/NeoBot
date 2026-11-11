"""官方模式的 OneBot action 分发。

只映射官方接口真实具备的能力：发送、登录/版本/状态、群信息与群成员（官方白名单
接口）、撤回；官方没有等价接口的列表/资料查询明确返回 failed，不再用 ok+[] 把
「协议做不到」伪装成「查询结果为空」。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from neobot_contracts.models import ConversationRef
from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME
from neobot_contracts.ports.speaking import SpeechBlocked

from neobot_adapter.model import response
from neobot_adapter.official.media import api_data
from neobot_adapter.official.send import OfficialApiError

_SEND_ACTIONS = frozenset({"send_group_msg", "send_private_msg", "send_msg"})
#: 官方适配器实际实现（或明确失败返回）的 action 集合，供插件/宿主查询能力。
SUPPORTED_ACTIONS = frozenset(
    {
        "send_group_msg",
        "send_private_msg",
        "send_msg",
        "get_login_info",
        "get_version_info",
        "get_status",
        "get_msg",
        "delete_msg",
        "get_group_info",
        "get_group_robot_status",
        "get_group_member_list",
        "get_group_member_info",
        "set_group_ban",
        "set_group_kick",
        "set_group_add_request",
        "set_group_whole_ban",
        "set_group_leave",
        "get_robot_uin_range",
    }
)


def supports_action(name: str) -> bool:
    """该 action 在官方适配器里是否有明确实现/明确失败语义。"""
    return str(name or "").strip() in SUPPORTED_ACTIONS
_PROTOCOL_VERSION = "qq-official-v2"
#: 官方撤回只允许 2 分钟内的消息。
_REVOKE_LIMIT_SECONDS = 120.0
#: 群成员列表每页 30 条，最多翻这么多页（防止异常游标把请求拖死）。
_MEMBER_PAGE_LIMIT = 50
_MEMBER_ROLES = frozenset({"owner", "admin", "member"})
_DELETE_ENDPOINTS = {
    "group": "/v2/groups/{openid}/messages/{message_id}",
    "private": "/v2/users/{openid}/messages/{message_id}",
}


class _ActionFailure(RuntimeError):
    """参数/能力不满足；转成 failed 响应。"""


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
            return await _delete_msg(adapter, values)
        if name == "get_group_info":
            return await _get_group_info(adapter, values)
        if name == "get_group_robot_status":
            return await _get_group_robot_status(adapter, values)
        if name == "get_group_member_list":
            return await _get_group_member_list(adapter, values)
        if name == "get_group_member_info":
            return await _get_group_member_info(adapter, values)
        if name == "set_group_ban":
            return await _set_group_ban(adapter, values)
        if name == "set_group_kick":
            return await _set_group_kick(adapter, values)
        if name == "set_group_add_request":
            return await _set_group_add_request(adapter, values)
        if name == "set_group_whole_ban":
            return _failed("QQ 官方机器人没有设置全员禁言的写接口（只提供查询）")
        if name == "set_group_leave":
            return _failed("QQ 官方机器人没有主动退群接口")
        if name == "get_group_list":
            return _failed("QQ 官方机器人协议不提供群列表接口，只能从群消息得知机器人已加入的群")
        if name == "get_friend_list":
            return _failed("QQ 官方机器人协议不提供好友列表接口")
        if name == "get_stranger_info":
            return _failed("QQ 官方机器人协议不提供陌生人资料接口")
        if name == "get_robot_uin_range":
            # 官方模式没有 UIN 段概念；空列表是真实答案，不是占位数据。
            return _ok([])
        if name == "get_forward_msg":
            return _failed("QQ 官方机器人协议没有合并转发消息查询接口")
    except SpeechBlocked:
        # 发言策略拒绝不是接口失败，必须原样抛给调用方（与 OneBot/Local 一致）。
        raise
    except _ActionFailure as exc:
        return _failed(str(exc))
    except OfficialApiError as exc:
        detail = str(exc)
        if exc.code is not None:
            detail = f"{detail}（err_code={exc.code}）"
        return _failed(f"官方接口失败：{detail}")
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


# ── 群信息 / 群成员（官方接口） ─────────────────────────────────────


async def _get_group_info(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id, group_openid = _group_target(adapter, params)
    payload = await _api(adapter).request("GET", f"/v2/groups/{group_openid}/info")
    data = api_data(payload)
    return _ok(
        {
            "group_id": group_id,
            "group_name": str(data.get("group_name") or ""),
            "group_memo": str(data.get("group_finger_memo") or ""),
            "member_count": _as_int(data.get("group_member_num")),
        }
    )


async def _get_group_robot_status(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id, group_openid = _group_target(adapter, params)
    payload = await _api(adapter).request("GET", f"/v2/groups/{group_openid}/bot_state")
    data = api_data(payload)
    return _ok(
        {
            "group_id": group_id,
            "member_role": str(data.get("member_role") or ""),
            "allow_proactive_msg": bool(data.get("allow_proactive_msg")),
            "recv_msg_setting": str(data.get("recv_msg_setting") or ""),
            "joined_at": str(data.get("joined_at") or ""),
        }
    )


async def _get_group_member_list(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id, group_openid = _group_target(adapter, params)
    api = _api(adapter)
    members: list[dict[str, Any]] = []
    cursor = ""
    for _page in range(_MEMBER_PAGE_LIMIT):
        path = f"/v2/groups/{group_openid}/members"
        if cursor:
            path += f"?cursor={quote(cursor, safe='')}"
        payload = await api.request("GET", path)
        data = api_data(payload)
        raw_members = data.get("members")
        if isinstance(raw_members, list):
            for item in raw_members:
                if isinstance(item, dict):
                    mapped = _member_entry(adapter, group_id, item)
                    if mapped is not None:
                        members.append(mapped)
        cursor = str(data.get("next_cursor") or "").strip()
        if not cursor:
            break
    return _ok(members)


async def _get_group_member_info(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id, group_openid = _group_target(adapter, params)
    user_id = _as_int(params.get("user_id"))
    if not user_id:
        raise _ActionFailure("缺少有效的 user_id 参数")
    member_openid = adapter.identity.openid(user_id, "user")
    if not member_openid:
        raise _ActionFailure(f"无法由 user_id {user_id} 反查 member_openid")
    payload = await _api(adapter).request(
        "GET",
        f"/v2/groups/{group_openid}/members/{member_openid}",
    )
    member = _member_entry(adapter, group_id, api_data(payload))
    if member is None:
        raise _ActionFailure("官方群成员信息响应缺少 member_openid")
    return _ok(member)


def _group_target(adapter: Any, params: dict[str, Any]) -> tuple[int, str]:
    group_id = _as_int(params.get("group_id"))
    if not group_id:
        raise _ActionFailure("缺少有效的 group_id 参数")
    return group_id, _target_openid(adapter, group_id, "group")


def _target_openid(adapter: Any, target: Any, kind: str) -> str:
    try:
        synthetic = int(target)
    except (TypeError, ValueError) as exc:
        raise _ActionFailure("缺少有效的 group_id/user_id 参数") from exc
    openid = adapter.identity.openid(synthetic, kind)
    if not openid:
        label = "group_id" if kind == "group" else "user_id"
        raise _ActionFailure(f"无法由 {label} {synthetic} 反查 openid（该会话未在官方事件中出现过）")
    return openid


def _member_entry(
    adapter: Any,
    group_id: int,
    member: dict[str, Any],
) -> dict[str, Any] | None:
    member_openid = str(member.get("member_openid") or "").strip()
    if not member_openid:
        return None
    try:
        user_id = adapter.identity.user_id(member_openid)
    except ValueError:
        return None
    role = str(member.get("member_role") or "").strip().casefold()
    return {
        "group_id": group_id,
        "user_id": user_id,
        "nickname": str(member.get("username") or ""),
        "card": "",
        "role": role if role in _MEMBER_ROLES else "member",
        "is_robot": bool(member.get("bot")),
        "join_time": _epoch_seconds(member.get("joined_at")),
    }


# ── 群管理（官方真实接口） ─────────────────────────────────────────

_MAX_MUTE_SECONDS = 30 * 24 * 3600
_MAX_BATCH_MEMBERS = 20


def _member_openid(adapter: Any, user_id: Any) -> str:
    synthetic = _as_int(user_id)
    if not synthetic:
        raise _ActionFailure("缺少有效的 user_id 参数")
    openid = adapter.identity.openid(synthetic, "user")
    if not openid:
        raise _ActionFailure(f"无法由 user_id {synthetic} 反查 member_openid")
    return openid


async def _set_group_ban(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    group_id, group_openid = _group_target(adapter, params)
    member_openid = _member_openid(adapter, params.get("user_id"))
    duration = _as_int(params.get("duration"))
    if duration < 0:
        raise _ActionFailure("duration 不能为负数")
    if duration == 0:
        member = {"op": "del", "member_openid": member_openid, "mute_expire_at": ""}
    else:
        if duration > _MAX_MUTE_SECONDS:
            raise _ActionFailure("官方单次禁言最长 30 天")
        expire_at = (datetime.now(timezone.utc) + timedelta(seconds=duration)).isoformat()
        member = {"op": "add", "member_openid": member_openid, "mute_expire_at": expire_at}
    await _api(adapter).request(
        "POST",
        f"/v2/groups/{group_openid}/restrict_chat_setting",
        body={"members": [member]},
    )
    return _ok(None)


async def _set_group_kick(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    _group_id, group_openid = _group_target(adapter, params)
    member_openid = _member_openid(adapter, params.get("user_id"))
    body: dict[str, Any] = {"member_openids": [member_openid]}
    if bool(params.get("reject_add_request")):
        body["add_to_member_blacklist"] = True
    payload = await _api(adapter).request(
        "POST",
        f"/v2/groups/{group_openid}/batch_remove_members",
        body=body,
    )
    data = api_data(payload)
    if str(data.get("remove_members_result") or "") != "success":
        raise _ActionFailure(f"官方批量移除成员未成功：{data.get('remove_members_result') or 'unknown'}")
    return _ok(None)


async def _set_group_add_request(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    _group_id, group_openid = _group_target(adapter, params)
    member_openid = _member_openid(adapter, params.get("user_id"))
    approve = params.get("approve")
    if approve is None:
        raise _ActionFailure("缺少 approve 参数")
    body: dict[str, Any] = {"op": "approve" if bool(approve) else "decline"}
    flag = str(params.get("flag") or "").strip()
    if flag:
        body["join_request_id"] = flag
    reason = str(params.get("reason") or "").strip()
    if reason and not bool(approve):
        body["reject_reason"] = reason
    await _api(adapter).request(
        "POST",
        f"/v2/groups/{group_openid}/approval_join_request/{member_openid}",
        body=body,
    )
    return _ok(None)


# ── 撤回 ────────────────────────────────────────────────────────────


async def _delete_msg(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    message_id = _as_int(params.get("message_id"))
    if not message_id:
        raise _ActionFailure("缺少有效的 message_id 参数")
    official_id = adapter.message_ids.official(message_id)
    if not official_id:
        raise _ActionFailure("无法定位该消息的官方 ID（非本进程收发或已超出缓存）")
    kind = ""
    openid = ""
    sent_at = 0.0
    context = adapter.message_ids.context(message_id)
    if isinstance(context, dict):
        kind = str(context.get("kind") or "")
        openid = str(context.get("openid") or "")
        sent_at = _as_float(context.get("at"))
    if kind not in _DELETE_ENDPOINTS or not openid:
        kind, openid, fallback_at = _recent_context(adapter, message_id)
        sent_at = sent_at or fallback_at
    if kind not in _DELETE_ENDPOINTS or not openid:
        raise _ActionFailure("无法确定该消息的会话上下文，官方协议无法撤回")
    if sent_at and time.time() - sent_at > _REVOKE_LIMIT_SECONDS:
        raise _ActionFailure("消息发送已超过 2 分钟，官方不允许撤回")
    path = _DELETE_ENDPOINTS[kind].format(openid=openid, message_id=official_id)
    await _api(adapter).request("DELETE", path)
    adapter.forget_recent_message(message_id)
    return _ok(None)


def _recent_context(adapter: Any, message_id: int) -> tuple[str, str, float]:
    event = adapter.get_recent_message(message_id)
    if not isinstance(event, dict):
        return "", "", 0.0
    message_type = str(event.get("message_type") or "")
    at = _as_float(event.get("time"))
    if message_type == "group":
        group_id = _as_int(event.get("group_id"))
        return "group", adapter.identity.openid(group_id, "group") or "", at
    if message_type == "private":
        user_id = _as_int(event.get("user_id"))
        return "private", adapter.identity.openid(user_id, "private") or "", at
    return "", "", 0.0


# ── 本地最近消息 ────────────────────────────────────────────────────


def _get_msg(adapter: Any, params: dict[str, Any]) -> dict[str, Any]:
    message_id = _as_int(params.get("message_id"))
    event = adapter.get_recent_message(message_id) if message_id else None
    if event is None:
        return _failed("官方协议不提供历史消息查询接口，且该消息不在本地最近消息缓存中")
    return _ok(event)


# ── 工具 ────────────────────────────────────────────────────────────


def _api(adapter: Any) -> Any:
    api = getattr(adapter, "api", None)
    if api is None:
        raise _ActionFailure("QQ 官方机器人尚未连接")
    return api


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _epoch_seconds(value: Any) -> int:
    """RFC3339 → epoch 秒；解析不了返回 0。"""
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
    except ValueError:
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

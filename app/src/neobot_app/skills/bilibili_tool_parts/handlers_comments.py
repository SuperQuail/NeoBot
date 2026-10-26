"""评论区列表、评论树与消息通知的处理函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.bilibili._compat import call_client
from neobot_app.bilibili.comment_monitor import parse_feed_item
from neobot_app.skills.bilibili_tool_parts.common import (
    _COMMENT_ORDERS,
    _COMMENT_TYPE_ALIASES,
    _EMPTY_HINT,
    _TREE_FETCH_BUDGET,
    _aid_from_text,
    _call_kwargs,
    _comment_oid_from_text,
    _comment_type,
    _flag,
    _json,
    _supported_comment_types,
    _to_int,
    _video_identifier,
)
from neobot_app.skills.bilibili_tool_parts.mappers import (
    _comment_item,
    _comment_node,
    _message_item,
    _video_detail,
)

if TYPE_CHECKING:
    from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase


async def _resolve_oid(client: Any, identifier: str) -> int:
    aid = _aid_from_text(identifier)
    if aid:
        return aid
    info = await call_client(client.get_video_info, identifier)
    return _video_detail(info)["aid"]


async def _resolve_comment_oid(client: Any, identifier: str, comment_type: int) -> int:
    """视频解析成 aid；动态/专栏/opus/番剧直接取标识里的数字。"""
    if comment_type == 1:
        return await _resolve_oid(client, identifier)
    return _comment_oid_from_text(identifier)


def _comment_type_error(raw: Any, supported: set[int]) -> str:
    names = "/".join(_COMMENT_TYPE_ALIASES)
    codes = "/".join(str(code) for code in sorted(supported))
    return f"comment_type 必须是 {names} 或客户端支持的类型码（{codes}），收到 {raw!r}"


async def _handle_video_comments(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json(
            {"ok": False, "error": "缺少 identifier（BV号、av号或视频/动态/专栏的 ID/链接）"}
        )
    order = str(args.get("order") or "hot").strip()
    if order not in _COMMENT_ORDERS:
        return _json(
            {"ok": False, "error": f"order 必须是 {'/'.join(_COMMENT_ORDERS)}，收到 {order!r}"}
        )
    client = skill._require_client()
    supported = _supported_comment_types(client)
    comment_type, type_name = _comment_type(args.get("comment_type"), supported)
    if not comment_type:
        return _json(
            {"ok": False, "error": _comment_type_error(args.get("comment_type"), supported)}
        )
    limit = min(max(_to_int(args.get("limit")) or 20, 1), 50)
    cursor = str(args.get("cursor") or "").strip()
    get_comments = getattr(client, "get_comments", None)
    if callable(get_comments):
        oid = await _resolve_comment_oid(client, identifier, comment_type)
        if not oid:
            return _json({"ok": False, "error": f"无法从 {identifier} 解析出评论区 oid"})
        page = await call_client(
            get_comments,
            oid,
            comment_type,
            mode=order,
            cursor=cursor,
            page_size=limit,
        )
        page = page if isinstance(page, dict) else {}
        rows = page.get("items") or []
        next_cursor = str(page.get("cursor") or "")
        is_end = bool(page.get("is_end", True))
    else:
        # 旧客户端只有 get_video_comments（列表形式），仅支持视频评论区。
        legacy = getattr(client, "get_video_comments", None)
        if comment_type != 1 or not callable(legacy):
            return _json(
                {"ok": False, "error": "B站客户端缺少 get_comments 能力（客户端未更新或未配置）"}
            )
        oid = await _resolve_oid(client, identifier)
        if not oid:
            return _json({"ok": False, "error": f"无法从 {identifier} 解析出视频号"})
        rows = await call_client(legacy, oid, order=order)
        next_cursor, is_end = "", True
    items = [_comment_item(item) for item in rows or [] if isinstance(item, dict)][:limit]
    payload: dict[str, Any] = {
        "ok": True,
        "oid": oid,
        "comment_type": type_name,
        "order": order,
        "count": len(items),
        "cursor": next_cursor,
        "is_end": is_end,
        "comments": items,
    }
    if not items:
        payload["note"] = _EMPTY_HINT
    return _json(payload)


async def _handle_comment_tree(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json(
            {"ok": False, "error": "缺少 identifier（BV号、av号或视频/动态/专栏的 ID/链接）"}
        )
    client = skill._require_client("get_video_info", "get_comment_replies")
    supported = _supported_comment_types(client)
    comment_type, type_name = _comment_type(args.get("comment_type"), supported)
    if not comment_type:
        return _json(
            {"ok": False, "error": _comment_type_error(args.get("comment_type"), supported)}
        )
    root_rpid = max(0, _to_int(args.get("root_rpid")))
    limit = min(max(_to_int(args.get("limit")) or 20, 1), 50)
    cursor = str(args.get("cursor") or "").strip()
    oid = await _resolve_comment_oid(client, identifier, comment_type)
    if not oid:
        return _json({"ok": False, "error": f"无法从 {identifier} 解析出评论区 oid"})
    reply_kwargs = _call_kwargs(client.get_comment_replies, {"type_": comment_type})

    if root_rpid:
        replies = await call_client(
            client.get_comment_replies, oid, root_rpid, **reply_kwargs
        )
        comments = [
            _comment_node(item) for item in replies or [] if isinstance(item, dict)
        ][:limit]
        payload: dict[str, Any] = {
            "ok": True,
            "oid": oid,
            "comment_type": type_name,
            "root_rpid": root_rpid,
            "count": len(comments),
            "cursor": "",
            "is_end": True,
            "comments": comments,
        }
        if not comments:
            payload["note"] = _EMPTY_HINT
        return _json(payload)

    get_comments = getattr(client, "get_comments", None)
    if callable(get_comments):
        page = await call_client(
            get_comments,
            oid,
            comment_type,
            mode="hot",
            cursor=cursor,
            page_size=limit,
        )
        page = page if isinstance(page, dict) else {}
        roots = page.get("items") or []
        next_cursor = str(page.get("cursor") or "")
        is_end = bool(page.get("is_end", True))
    else:
        if comment_type != 1:
            return _json(
                {"ok": False, "error": "B站客户端缺少 get_comments 能力（客户端未更新或未配置）"}
            )
        roots = await call_client(client.get_video_comments, oid, order="hot")
        next_cursor, is_end = "", True

    comments: list[dict[str, Any]] = []
    fetches = 0
    for raw in roots or []:
        if len(comments) >= limit:
            break
        if not isinstance(raw, dict):
            continue
        node = _comment_node(raw)
        inline = raw.get("replies")
        children = (
            [item for item in inline if isinstance(item, dict)]
            if isinstance(inline, list)
            else []
        )
        # shortcut: 一轮最多补拉 _TREE_FETCH_BUDGET 条根评论的楼中楼；要看更多用 root_rpid 单独展开。
        if not children and node["reply_count"] > 0 and fetches < _TREE_FETCH_BUDGET:
            fetches += 1
            fetched = await call_client(
                client.get_comment_replies, oid, node["rpid"], **reply_kwargs
            )
            children = [item for item in fetched or [] if isinstance(item, dict)]
        node["replies"] = [_comment_node(item) for item in children][:limit]
        comments.append(node)
    payload = {
        "ok": True,
        "oid": oid,
        "comment_type": type_name,
        "root_rpid": 0,
        "count": len(comments),
        "cursor": next_cursor,
        "is_end": is_end,
        "comments": comments,
    }
    if not comments:
        payload["note"] = _EMPTY_HINT
    return _json(payload)


async def _handle_read_bili_messages(skill: _BilibiliToolBase, args: dict) -> str:
    limit = min(max(_to_int(args.get("limit")) or 20, 1), 50)
    include_at = _flag(args.get("include_at"), True)
    sources = (("get_reply_feed", "reply_feed"), ("get_at_feed", "at_feed"))
    if not include_at:
        sources = sources[:1]
    client = skill._require_client(*(method for method, _ in sources))
    messages: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for method, source in sources:
        feed = await call_client(getattr(client, method), limit=limit)
        for raw in feed or []:
            if not isinstance(raw, dict):
                continue
            try:
                event = parse_feed_item(raw, source)
            except Exception:
                continue
            if event is None:
                continue
            key = (event.oid, event.parent_id)
            if key in seen:  # 同一条评论可能同时出现在两个通知流里
                continue
            seen.add(key)
            messages.append(_message_item(event))
    messages.sort(key=lambda item: item["time"], reverse=True)
    payload: dict[str, Any] = {
        "ok": True,
        "count": len(messages),
        "include_at": include_at,
        "messages": messages[:limit],
        "note": "只读通知，不会自动回复；看完可用 comment_video 回复、comment_tree 展开楼中楼。",
    }
    if not payload["messages"]:
        payload["note"] = (
            "没有读到B站消息（可能没有新的回复/@，或接口失败/登录失效）；"
            "只读，不会自动回复。"
        )
    return _json(payload)

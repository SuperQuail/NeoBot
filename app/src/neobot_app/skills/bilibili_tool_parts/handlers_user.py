"""用户资料、主页、投稿、关注与关联QQ主页的处理函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.skills.bilibili_tool_parts.common import (
    _EMPTY_HINT,
    _PROFILE_CHARS,
    _SELF_ALIASES,
    _Unavailable,
    _call_kwargs,
    _json,
    _page,
    _parse_uid,
    _result_items,
    _text,
    _to_int,
    _write_failed,
    logger,
)
from neobot_app.skills.bilibili_tool_parts.mappers import (
    _dynamic_item,
    _user_item,
    _video_item,
)

if TYPE_CHECKING:
    from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase


async def _resolve_user(skill: _BilibiliToolBase, raw: Any) -> tuple[int, str]:
    """统一解析用户：留空=自己，UID/空间链接直取，否则按昵称搜索（精确同名优先）。"""
    text = str(raw or "").strip()
    if text.lower() in _SELF_ALIASES:
        uid = 0
        status = getattr(skill._service, "status", None)
        if callable(status):
            uid = _to_int(get_field(status(), "uid", 0))
        if not uid:
            uid = _to_int(get_field(skill._require_client(), "my_uid", 0))
        if not uid:
            raise _Unavailable("无法确定当前登录账号的UID，先发 /login bilibili 扫码登录")
        return uid, ""
    uid = _parse_uid(text)
    if uid > 0:
        return uid, ""
    client = skill._require_client("search")
    search = client.search
    data = await call_client(
        search, text, **_call_kwargs(search, {"search_type": "bili_user", "page": 1})
    )
    users = [item for item in (_user_item(raw_item) for raw_item in _result_items(data)) if item["uid"] > 0]
    if not users:
        raise _Unavailable(f"没有搜到昵称「{text}」的B站用户")
    matched = next((user for user in users if user["name"] == text), users[0])
    return matched["uid"], matched["name"]


async def _handle_user_info(skill: _BilibiliToolBase, args: dict) -> str:
    raw = args.get("uid")
    uid, matched_name = await _resolve_user(skill, raw)
    detail = await call_client(skill._read().user_card_detail, uid)
    if not detail.get("ok"):
        return _json(detail)
    payload: dict[str, Any] = {"ok": True, **detail}
    if matched_name:
        payload["matched_by"] = "name"
        payload["keyword"] = matched_name
    elif str(raw or "").strip().lower() in _SELF_ALIASES:
        payload["matched_by"] = "self"
    else:
        payload["matched_by"] = "uid"
    return _json(payload)


async def _handle_user_home(skill: _BilibiliToolBase, args: dict) -> str:
    uid, _ = await _resolve_user(skill, args.get("uid"))
    limit = min(max(_to_int(args.get("limit")) or 5, 1), 20)
    api = skill._read()
    detail = await call_client(api.user_card_detail, uid)
    if not detail.get("ok"):
        return _json(detail)
    payload: dict[str, Any] = {"ok": True, **detail}
    # 名片的 videos 是投稿数，与下面的投稿列表重名，改成 videos_count。
    payload["videos_count"] = payload.pop("videos")
    try:
        dynamics = await call_client(api.user_dynamics, uid, limit=limit)
    except Exception as exc:
        payload["dynamics_error"] = f"动态读取失败：{exc}"
    else:
        if dynamics.get("ok"):
            payload["dynamics"] = [_dynamic_item(item) for item in dynamics.get("items") or []]
            payload["dynamics_has_more"] = bool(dynamics.get("has_more"))
        else:
            payload["dynamics_error"] = str(dynamics.get("error") or "动态读取失败")
    client = skill._require_client()
    try:
        get_videos = client.get_user_videos
        data = await call_client(get_videos, uid, **_call_kwargs(get_videos, {"page": 1}))
        payload["videos"] = [_video_item(item) for item in _result_items(data)][:limit]
    except Exception as exc:
        payload["videos_error"] = f"投稿读取失败：{exc}"
    return _json(payload)


async def _handle_follow_user(skill: _BilibiliToolBase, args: dict) -> str:
    uid = _parse_uid(args.get("uid"))
    if not uid:
        return _json({"ok": False, "error": "缺少或无效的 uid（B站UID 或空间链接）"})
    action = str(args.get("action") or "follow").strip().lower()
    if action not in {"follow", "unfollow"}:
        return _json({"ok": False, "error": "action 必须是 follow 或 unfollow"})
    client = skill._require_client("follow_user")
    action_name = "关注" if action == "follow" else "取消关注"
    try:
        sent = await call_client(client.follow_user, uid, follow=action == "follow")
    except Exception as exc:
        logger.warning(f"B站{action_name}失败：uid={uid}：{type(exc).__name__}: {exc}")
        return _write_failed(skill, action_name, f"{exc}（可能登录失效或触发风控）", uid=uid)
    if not sent:
        return _write_failed(
            skill, action_name, "B站未返回成功，可能登录失效或触发风控", uid=uid
        )
    return _json(
        {
            "ok": True,
            "uid": uid,
            "action": action,
            "note": "已以当前登录B站账号公开操作",
        }
    )


async def _handle_user_videos(skill: _BilibiliToolBase, args: dict) -> str:
    uid = _parse_uid(args.get("uid"))
    if not uid:
        return _json({"ok": False, "error": "缺少或无效的 uid（B站UID 或空间链接）"})
    page = _page(args.get("page"))
    client = skill._require_client("get_user_videos")
    kwargs = _call_kwargs(client.get_user_videos, {"page": page})
    data = await call_client(client.get_user_videos, uid, **kwargs)
    videos = [_video_item(item) for item in _result_items(data)]
    payload: dict[str, Any] = {
        "ok": True,
        "uid": uid,
        "page": page,
        "count": len(videos),
        "videos": videos,
    }
    if not videos:
        payload["note"] = _EMPTY_HINT
    return _json(payload)


async def _archive_get(skill: _BilibiliToolBase, table: str, key: str) -> str:
    if skill._archive is None:
        return ""
    try:
        item = await call_client(skill._archive.get, table, key)
    except Exception as exc:
        logger.debug(f"读取B站关联档案失败：{table}/{key}：{type(exc).__name__}: {exc}")
        return ""
    return str(get_field(item, "value", "") or "").strip()


async def _load_qq_user(skill: _BilibiliToolBase, qq_number: str) -> Any:
    if skill._uow_factory is None:
        return None
    try:
        async with skill._uow_factory() as uow:
            profiles = getattr(uow, "profiles", None)
            if profiles is None:
                return None
            return await call_client(profiles.get_user, qq_number)
    except Exception as exc:
        logger.debug(f"读取QQ用户资料失败：{qq_number}：{type(exc).__name__}: {exc}")
        return None


async def _handle_linked_qq_profile(skill: _BilibiliToolBase, args: dict) -> str:
    uid = _parse_uid(args.get("uid"))
    if not uid:
        return _json({"ok": False, "error": "缺少或无效的 uid（B站UID 或空间链接）"})
    if skill._uow_factory is None:
        return _json({"ok": False, "error": "账户关联存储未配置，无法查关联QQ"})
    try:
        async with skill._uow_factory() as uow:
            repo = getattr(uow, "bilibili_links", None)
            if repo is None:
                return _json({"ok": False, "error": "账号关联表不可用"})
            links = await call_client(repo.find_by_uid, uid)
    except Exception as exc:
        logger.warning(f"查询B站-QQ关联失败：uid={uid}：{type(exc).__name__}: {exc}")
        return _json({"ok": False, "error": f"查询B站-QQ关联失败：{exc}"})

    qq_numbers: list[str] = []
    for link in links or []:
        qq_number = str(get_field(link, "qq_number", "") or "").strip()
        if qq_number and qq_number not in qq_numbers:
            qq_numbers.append(qq_number)
    if not qq_numbers:
        return _json(
            {
                "ok": True,
                "uid": uid,
                "linked": False,
                "message": f"该B站用户（UID:{uid}）还没有关联的QQ主页，查不到QQ资料。",
            }
        )

    profiles: list[dict[str, Any]] = []
    for qq_number in qq_numbers:
        item: dict[str, Any] = {"qq_number": qq_number}
        user_data = await _load_qq_user(skill, qq_number)
        if user_data is not None:
            item["nick_name"] = str(get_field(user_data, "nick_name", "") or "").strip()
            item["remark"] = str(get_field(user_data, "remark", "") or "").strip()
            item["profile"] = _text(get_field(user_data, "profile", ""), _PROFILE_CHARS)
            item["known_gender"] = str(
                get_field(user_data, "known_gender", "") or ""
            ).strip()
        item["user_summary"] = _text(
            await _archive_get(skill, "user_summary", qq_number), _PROFILE_CHARS
        )
        item["user_profile"] = _text(
            await _archive_get(skill, "user_profile", qq_number), _PROFILE_CHARS
        )
        profiles.append(item)

    return _json(
        {
            "ok": True,
            "uid": uid,
            "linked": True,
            "qq_numbers": qq_numbers,
            "count": len(profiles),
            "profiles": profiles,
        }
    )

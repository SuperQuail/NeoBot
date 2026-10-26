"""公开写操作（评论/点赞/投币/分享/收藏）的处理函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.bilibili._compat import call_client
from neobot_app.skills.bilibili_tool_parts.common import (
    _json,
    _to_int,
    _video_identifier,
    _write_failed,
    logger,
)
from neobot_app.skills.bilibili_tool_parts.handlers_comments import _resolve_oid
from neobot_app.skills.bilibili_tool_parts.mappers import _favorite_folder_item

if TYPE_CHECKING:
    from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase


async def _handle_comment_video(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    text = str(args.get("text") or "").strip()
    if not text:
        return _json({"ok": False, "error": "缺少 text（评论内容）"})
    root = max(0, _to_int(args.get("root")))
    parent = max(0, _to_int(args.get("parent")))
    client = skill._require_client("post_video_comment")
    try:
        sent = await call_client(
            client.post_video_comment, identifier, text, root=root, parent=parent
        )
    except Exception as exc:
        logger.warning(f"B站发评论失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "发评论",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not sent:
        return _write_failed(
            skill,
            "发评论",
            "B站未返回成功，可能登录失效、评论受限或触发风控",
            identifier=identifier,
        )
    return _json(
        {
            "ok": True,
            "identifier": identifier,
            "comment": text,
            "root": root,
            "parent": parent,
        }
    )


async def _handle_like_video(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    client = skill._require_client("like_video")
    try:
        liked = await call_client(client.like_video, identifier)
    except Exception as exc:
        logger.warning(f"B站视频点赞失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "点赞",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not liked:
        return _write_failed(
            skill,
            "点赞",
            "B站未返回成功，可能登录失效、已点赞过或触发风控",
            identifier=identifier,
        )
    return _json({"ok": True, "identifier": identifier, "liked": True})


async def _handle_like_comment(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    rpid = _to_int(args.get("rpid"))
    if rpid <= 0:
        return _json({"ok": False, "error": "缺少或无效的 rpid（评论ID）"})
    client = skill._require_client("get_video_info", "like_comment")
    try:
        oid = await _resolve_oid(client, identifier)
    except Exception as exc:
        logger.warning(
            f"B站评论点赞解析视频号失败：{identifier}：{type(exc).__name__}: {exc}"
        )
        return _json(
            {"ok": False, "identifier": identifier, "error": f"无法解析视频号：{exc}"}
        )
    if not oid:
        return _json(
            {
                "ok": False,
                "identifier": identifier,
                "error": f"无法从 {identifier} 解析出视频号",
            }
        )
    try:
        liked = await call_client(client.like_comment, oid, rpid, type_=1)
    except Exception as exc:
        logger.warning(f"B站评论点赞失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "评论点赞",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not liked:
        return _write_failed(
            skill,
            "评论点赞",
            "B站未返回成功，可能登录失效、已点赞过或触发风控",
            identifier=identifier,
        )
    return _json(
        {
            "ok": True,
            "identifier": identifier,
            "oid": oid,
            "rpid": rpid,
            "liked": True,
        }
    )


async def _handle_coin_video(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    multiply = 2 if _to_int(args.get("multiply")) >= 2 else 1
    client = skill._require_client("coin_video")
    try:
        coined = await call_client(client.coin_video, identifier, multiply=multiply)
    except Exception as exc:
        logger.warning(f"B站视频投币失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "投币",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not coined:
        return _write_failed(
            skill,
            "投币",
            "B站未返回成功，可能登录失效、硬币不足或触发风控",
            identifier=identifier,
        )
    return _json({"ok": True, "identifier": identifier, "multiply": multiply, "coined": True})


async def _handle_share_video(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    client = skill._require_client("share_video")
    try:
        shared = await call_client(client.share_video, identifier)
    except Exception as exc:
        logger.warning(f"B站视频分享失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "分享",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not shared:
        return _write_failed(
            skill,
            "分享",
            "B站未返回成功，可能登录失效或触发风控",
            identifier=identifier,
        )
    return _json({"ok": True, "identifier": identifier, "shared": True})


async def _handle_favorite_video(skill: _BilibiliToolBase, args: dict) -> str:
    identifier = _video_identifier(args.get("identifier"))
    if not identifier:
        return _json({"ok": False, "error": "缺少 identifier（BV号、av号或视频链接）"})
    folder_id = _to_int(args.get("folder_id"))
    if folder_id <= 0:
        return _json(
            {"ok": False, "error": "缺少或无效的 folder_id（收藏夹ID，可先用 favorite_folders 查）"}
        )
    client = skill._require_client("favorite_video")
    try:
        favorited = await call_client(client.favorite_video, identifier, folder_id)
    except Exception as exc:
        logger.warning(f"B站视频收藏失败：{identifier}：{type(exc).__name__}: {exc}")
        return _write_failed(
            skill,
            "收藏",
            f"{exc}（可能登录失效或触发风控）",
            identifier=identifier,
        )
    if not favorited:
        return _write_failed(
            skill,
            "收藏",
            "B站未返回成功，可能登录失效、收藏夹无效或触发风控",
            identifier=identifier,
        )
    return _json(
        {"ok": True, "identifier": identifier, "folder_id": folder_id, "favorited": True}
    )


async def _handle_favorite_folders(skill: _BilibiliToolBase, args: dict) -> str:
    client = skill._require_client("get_favorite_folders")
    try:
        raw_folders = await call_client(client.get_favorite_folders)
    except Exception as exc:
        logger.warning(f"B站收藏夹读取失败：{type(exc).__name__}: {exc}")
        return _json({"ok": False, "error": f"读取收藏夹失败：{exc}"})
    folders = [
        _favorite_folder_item(item) for item in raw_folders or [] if isinstance(item, dict)
    ]
    payload: dict[str, Any] = {
        "ok": True,
        "count": len(folders),
        "folders": folders,
        "note": "只读列表，不会改动收藏；favorite_video 的 folder_id 用这里的 id。",
    }
    if not folders:
        payload["note"] = "没有读到收藏夹（可能未登录、没有收藏夹或接口失败）；只读，不会改动收藏。"
    return _json(payload)

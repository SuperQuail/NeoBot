"""把B站接口返回的原始 dict 归一化成工具输出。"""

from __future__ import annotations

from typing import Any

from neobot_app.bilibili._compat import get_field
from neobot_app.skills.bilibili_tool_parts.common import (
    _DYNAMIC_TYPES,
    _detail_node,
    _text,
    _to_int,
)


def _owner_name(raw: Any) -> str:
    owner = get_field(raw, "owner")
    if isinstance(owner, str) and owner.strip():
        return _text(owner)
    name = _text(get_field(owner, "name", "")) if owner else ""
    return name or _text(get_field(raw, "author", "")) or _text(get_field(raw, "up_name", ""))


def _video_item(raw: Any) -> dict[str, Any]:
    bvid = str(get_field(raw, "bvid", "") or "").strip()
    url = str(get_field(raw, "arcurl", "") or get_field(raw, "url", "") or "").strip()
    if not url and bvid:
        url = f"https://www.bilibili.com/video/{bvid}"
    return {
        "title": _text(get_field(raw, "title", "")),
        "bvid": bvid,
        "up": _owner_name(raw),
        "play": _to_int(get_field(raw, "play", get_field(raw, "view", 0))),
        "url": url,
        "desc": _text(get_field(raw, "desc", get_field(raw, "description", "")), 300),
    }


def _user_item(raw: Any) -> dict[str, Any]:
    uid = _to_int(get_field(raw, "mid", get_field(raw, "uid", 0)))
    return {
        "uid": uid,
        "name": _text(get_field(raw, "uname", get_field(raw, "name", ""))),
        "sign": _text(get_field(raw, "usign", get_field(raw, "sign", "")), 300),
        "fans": _to_int(get_field(raw, "fans", get_field(raw, "follower", 0))),
        "videos": _to_int(get_field(raw, "videos")),
        "level": _to_int(get_field(raw, "level")),
        "url": f"https://space.bilibili.com/{uid}" if uid else "",
    }


def _article_item(raw: Any) -> dict[str, Any]:
    cv_id = _to_int(get_field(raw, "id", get_field(raw, "cv_id", 0)))
    url = str(get_field(raw, "url", "") or "").strip()
    if not url and cv_id:
        url = f"https://www.bilibili.com/read/cv{cv_id}"
    return {
        "cv_id": cv_id,
        "title": _text(get_field(raw, "title", "")),
        "author": _text(get_field(raw, "author", "")),
        "view": _to_int(get_field(raw, "view", get_field(raw, "play", 0))),
        "url": url,
        "desc": _text(get_field(raw, "desc", get_field(raw, "summary", "")), 300),
    }


def _comment_item(raw: Any) -> dict[str, Any]:
    member = get_field(raw, "member") or {}
    content = get_field(raw, "content")
    message = content if isinstance(content, str) else get_field(content, "message", "")
    return {
        "rpid": _to_int(get_field(raw, "rpid")),
        "uid": _to_int(get_field(raw, "mid", get_field(member, "mid", get_field(raw, "uid", 0)))),
        "uname": _text(get_field(raw, "uname", get_field(member, "uname", ""))),
        "content": _text(message, 1000),
        "like": _to_int(get_field(raw, "like")),
        "ctime": _to_int(get_field(raw, "ctime")),
        "replies": _to_int(get_field(raw, "rcount", get_field(raw, "reply_count", 0))),
    }


def _comment_node(raw: Any) -> dict[str, Any]:
    """评论树节点：reply_count 是楼中楼总数，replies 留给子评论列表。"""
    node = _comment_item(raw)
    node["reply_count"] = node.pop("replies", 0)
    node["replies"] = []
    return node


def _favorite_folder_item(raw: Any) -> dict[str, Any]:
    return {
        "id": _to_int(get_field(raw, "id", get_field(raw, "fid", 0))),
        "title": _text(get_field(raw, "title", "")),
        "count": _to_int(get_field(raw, "media_count", 0)),
    }


def _content_url(business_id: int, oid: int) -> str:
    """通知没有 uri 时按内容类型拼一个可点链接。"""
    if oid <= 0:
        return ""
    if business_id == 12:
        return f"https://www.bilibili.com/read/cv{oid}"
    if business_id in (11, 17):
        return f"https://t.bilibili.com/{oid}"
    return f"https://www.bilibili.com/video/av{oid}"


def _message_item(event: Any) -> dict[str, Any]:
    """把通知事件归一化成「谁、在哪、说了什么」。"""
    oid = _to_int(get_field(event, "oid"))
    business_id = _to_int(get_field(event, "business_id", 1)) or 1
    url = str(get_field(event, "target_url", "") or "").strip()
    return {
        "source": "at" if get_field(event, "source", "") == "at_feed" else "reply",
        "type": str(get_field(event, "target_type", "") or ""),
        "oid": oid,
        "title": _text(get_field(event, "target_title", "")),
        "url": url if url.startswith("http") else _content_url(business_id, oid),
        "comment": _text(get_field(event, "content", ""), 1000),
        "uid": _to_int(get_field(event, "user_uid")),
        "uname": _text(get_field(event, "user_name", "")),
        "root_rpid": _to_int(get_field(event, "root_id")),
        "parent_rpid": _to_int(get_field(event, "parent_id")),
        "time": _to_int(get_field(event, "ctime")),
    }


def _video_detail(data: Any) -> dict[str, Any]:
    raw = _detail_node(data)
    owner = get_field(raw, "owner")
    stat = get_field(raw, "stat") or {}
    bvid = str(get_field(raw, "bvid", "") or "").strip()
    aid = _to_int(get_field(raw, "aid", get_field(raw, "avid", 0)))
    url = str(get_field(raw, "url", "") or "").strip()
    if not url and bvid:
        url = f"https://www.bilibili.com/video/{bvid}"
    return {
        "bvid": bvid,
        "aid": aid,
        "title": _text(get_field(raw, "title", "")),
        "up": _owner_name(raw),
        "up_uid": _to_int(get_field(owner, "mid", 0)) if owner else 0,
        "duration": _to_int(get_field(raw, "duration", get_field(raw, "length", 0))),
        "desc": _text(get_field(raw, "desc", get_field(raw, "description", "")), 1500),
        "view": _to_int(get_field(stat, "view", get_field(raw, "play", 0))),
        "like": _to_int(get_field(stat, "like", 0)),
        "url": url,
        "cover": str(get_field(raw, "pic", get_field(raw, "cover", "")) or ""),
    }


def _stat_count(value: Any) -> int:
    """module_stat 的计数既可能是 {"count": n}，也可能是裸数字。"""
    return _to_int(get_field(value, "count", 0)) if isinstance(value, dict) else _to_int(value)


def _dynamic_item(raw: Any) -> dict[str, Any]:
    """动态归一化：类型、正文摘要、发布时间、互动数与可点链接。"""
    dynamic_id = _text(get_field(raw, "id_str", ""))
    dynamic_type = _text(get_field(raw, "type", ""))
    module = get_field(raw, "module_dynamic") or {}
    desc = get_field(module, "desc") or {}
    major = get_field(module, "major") or {}
    archive = get_field(major, "archive") or {}
    author = get_field(raw, "module_author") or {}
    stat = get_field(raw, "module_stat") or {}
    text = _text(get_field(desc, "text", "")) or _text(get_field(archive, "title", ""))
    if not text and dynamic_type == "DYNAMIC_TYPE_FORWARD":  # 转发本身常无正文，借用原动态
        orig = get_field(raw, "orig") or {}
        orig_module = get_field(orig, "module_dynamic") or {}
        text = _text(get_field(get_field(orig_module, "desc") or {}, "text", ""))
    if dynamic_type == "DYNAMIC_TYPE_AV":
        bvid = _text(get_field(archive, "bvid", ""))
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else f"https://t.bilibili.com/{dynamic_id}"
    elif dynamic_type == "DYNAMIC_TYPE_ARTICLE":
        cv_id = _to_int(get_field(get_field(major, "article") or {}, "id", 0)) or _to_int(dynamic_id)
        url = f"https://www.bilibili.com/read/cv{cv_id}"
    else:
        url = f"https://t.bilibili.com/{dynamic_id}"
    return {
        "type": _DYNAMIC_TYPES.get(dynamic_type, dynamic_type),
        "id": dynamic_id,
        "text": _text(text, 200),
        "url": url,
        "time": _to_int(get_field(author, "pub_ts")),
        "time_text": _text(get_field(author, "pub_time", "")),
        "likes": _stat_count(get_field(stat, "like")),
        "comments": _stat_count(get_field(stat, "comment")),
        "reposts": _stat_count(get_field(stat, "forward")),
    }

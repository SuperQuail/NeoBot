"""B站工具的共同底座：日志、常量、参数归一化与错误文案。"""

from __future__ import annotations

import html
import inspect
import json
import re
from typing import TYPE_CHECKING, Any

from neobot_app.bilibili._compat import get_field
from neobot_app.utils.logger import get_module_logger

if TYPE_CHECKING:
    from neobot_app.skills.bilibili_tool_parts.base import _BilibiliToolBase

logger = get_module_logger("bilibili.tools_skill")


_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_AV_RE = re.compile(r"(?:^|[^0-9A-Za-z])av(\d+)", re.IGNORECASE)
_UID_RE = re.compile(r"space\.bilibili\.com/(\d+)", re.IGNORECASE)
#: user_info / user_home 的留空值：等同「当前登录账号」。
_SELF_ALIASES = frozenset({"", "me", "self", "我", "自己", "本人"})
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

_VIDEO_ORDERS = ("totalrank", "click", "pubdate", "dm", "stow")
_COMMENT_ORDERS = ("hot", "time")
#: comment_type 名称 -> B站评论区类型码（视频 1、动态 17、专栏/opus 12、番剧 11）。
_COMMENT_TYPE_ALIASES = {
    "video": 1,
    "dynamic": 17,
    "article": 12,
    "opus": 12,
    "bangumi": 11,
}
#: 动态类型码 -> 中文名；未知类型保留原值。
_DYNAMIC_TYPES = {
    "DYNAMIC_TYPE_AV": "视频",
    "DYNAMIC_TYPE_DRAW": "图文",
    "DYNAMIC_TYPE_WORD": "文字",
    "DYNAMIC_TYPE_FORWARD": "转发",
    "DYNAMIC_TYPE_ARTICLE": "专栏",
    "DYNAMIC_TYPE_OPUS": "图文",
    "DYNAMIC_TYPE_PGC": "番剧",
    "DYNAMIC_TYPE_LIVE_RCMD": "直播",
}
_PROFILE_CHARS = 1500
#: comment_tree 一轮最多补拉的楼中楼根评论数（避免大 limit 时串行请求过多）。
_TREE_FETCH_BUDGET = 10
#: 空结果提示：接口失败与真的没有数据在这一层看不出来，别让模型当成"没有"。
_EMPTY_HINT = "没有取到数据：可能是真的为空，也可能是接口失败/风控/登录失效，可再试一次或先确认账号状态。"
#: 会以当前登录账号公开操作的写工具；调用前必须显式 confirm。
_WRITE_TOOLS = frozenset(
    {
        "comment_video",
        "like_video",
        "like_comment",
        "coin_video",
        "share_video",
        "favorite_video",
        "follow_user",
    }
)
_CONFIRM_SCHEMA = {
    "type": "boolean",
    "description": "确认已获得用户明确授权，将以当前登录B站账号公开操作；必须传 true 才会执行",
    "default": False,
}
_CONFIRM_REQUIRED = (
    "写操作需要确认：确认用户意图后带上 confirm=true 再调用（会以当前登录B站账号公开操作）"
)


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _text(value: Any, limit: int = 0) -> str:
    """去掉 B站搜索高亮标签与实体，压成单行。"""
    text = html.unescape(_TAG_RE.sub("", str(value or "")))
    text = _SPACE_RE.sub(" ", text).strip()
    if limit > 0 and len(text) > limit:
        return text[:limit]
    return text


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _page(value: Any) -> int:
    return max(1, _to_int(value) or 1)


def _detail_node(data: Any) -> Any:
    """剥掉 API 的 {"data": {...}} 包装。"""
    if isinstance(data, dict):
        inner = get_field(data, "data")
        if isinstance(inner, dict):
            return inner
    return data


def _call_kwargs(fn: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """只保留目标函数接受的参数，避免并行实现少的参数直接 TypeError。"""
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return dict(kwargs)
    if any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params):
        return dict(kwargs)
    names = {param.name for param in params}
    return {key: value for key, value in kwargs.items() if key in names}


def _result_items(data: Any) -> list[Any]:
    """从搜索/投稿返回里取列表，兼容直接列表与多层 data 包装。"""
    if isinstance(data, list):
        return data
    node = data
    for _ in range(3):
        if not isinstance(node, dict):
            return []
        for key in ("result", "items", "list", "videos"):
            value = get_field(node, key)
            if isinstance(value, list):
                return value
        node = get_field(node, "data")
    return []


def _result_total(data: Any) -> int:
    node = _detail_node(data)
    return _to_int(get_field(node, "numResults", get_field(node, "total", 0)))


def _flag(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("", "0", "false", "no", "off")
    return bool(value)


def _dormant_reason(service: Any) -> str:
    """未登录提示：带上 service 记录的真实原因（网络异常 / 凭证失效）。"""
    base = "B站未登录（功能休眠），先发 /login bilibili 扫码登录"
    status = getattr(service, "status", None)
    detail = ""
    if callable(status):
        try:
            detail = str(get_field(status(), "error", "") or "").strip()
        except Exception:
            detail = ""
    return f"{base}；原因：{detail}" if detail else base


def _service_error(service: Any) -> str:
    """账号最近一次错误，写操作失败时作为真实原因回给模型。"""
    status = getattr(service, "status", None)
    if not callable(status):
        return ""
    try:
        return str(get_field(status(), "error", "") or "").strip()
    except Exception:
        return ""


def _write_failed(
    skill: "_BilibiliToolBase", action: str, hint: str, **extra: Any
) -> str:
    """写操作失败：hint 是接口层原因，再补上账号状态里的真实原因。"""
    detail = _service_error(skill._service)
    error = f"{action}失败：{hint}"
    if detail:
        error = f"{error}；账号状态：{detail}"
    return _json({"ok": False, **extra, "error": error})


def _video_identifier(raw: Any) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    match = _BV_RE.search(text)
    if match:
        return match.group(0)
    match = _AV_RE.search(text)
    if match:
        return f"av{match.group(1)}"
    return text


def _parse_uid(raw: Any) -> int:
    text = str(raw or "").strip()
    if not text:
        return 0
    match = _UID_RE.search(text)
    if match:
        return _to_int(match.group(1))
    return _to_int(text)


def _aid_from_text(text: str) -> int:
    match = _AV_RE.search(text)
    if match:
        return _to_int(match.group(1))
    return _to_int(text) if text.isdigit() else 0


def _supported_comment_types(client: Any) -> set[int]:
    """client 公开的 COMMENT_TYPES（见任务契约）优先，否则按工具文档里的五种。"""
    table = getattr(client, "COMMENT_TYPES", None)
    if isinstance(table, dict) and table:
        return {_to_int(code) for code in table}
    return set(_COMMENT_TYPE_ALIASES.values())


def _comment_type(raw: Any, supported: set[int]) -> tuple[int, str]:
    """comment_type 名称/类型码 -> (类型码, 输出名)；client 不支持则返回 (0, "")。"""
    text = str(raw or "").strip().lower() or "video"
    if text.isdigit():
        code = _to_int(text)
        return (code, text) if code in supported else (0, "")
    code = _COMMENT_TYPE_ALIASES.get(text, 0)
    return code, (text if code and code in supported else "")


def _comment_oid_from_text(text: str) -> int:
    """动态/专栏/opus 的 oid 就是标识里的数字（纯数字或链接都行）。"""
    oid = _aid_from_text(text)
    if oid:
        return oid
    match = re.search(r"(\d+)", text)
    return _to_int(match.group(1)) if match else 0


def _comment_type_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "description": "评论区类型：video=视频（默认），dynamic=动态，article=专栏，"
        "opus=图文，bangumi=番剧",
        "enum": list(_COMMENT_TYPE_ALIASES),
        "default": "video",
    }


class _Unavailable(RuntimeError):
    """依赖不可用；消息直接回给模型。"""

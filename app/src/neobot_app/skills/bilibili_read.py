"""B站只读查询 Skill — 动态、专栏、番剧、名片、直播状态、视频流、弹幕与短链。

全部工具都是只读的：不评论、不私信、不发动态、不点赞。底层用
BilibiliReadApi（复用 BilibiliClient 的 GET 与 WBI 签名）；任何失败都返回
{"ok": false, "error": "中文说明"}，不会把异常丢给模型。
"""

from __future__ import annotations

import html
import json
import re
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.bilibili.read_api import BilibiliReadApi
from neobot_app.skills.base import SkillModule
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.read_skill")

_READ_ONLY_NOTE = "只读查询：不会发评论、私信、动态或点赞。"
#: 专栏正文：剥掉 HTML 标签后最多回给模型多少字（避免整篇灌进上下文）。
_ARTICLE_CHARS = 5000
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RE = re.compile(r"\n{3,}")


class _Unavailable(RuntimeError):
    """依赖不可用；消息直接回给模型。"""


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


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


def _plain(value: Any) -> str:
    """专栏正文去掉 HTML 标签与实体，压掉多余空行。"""
    text = html.unescape(_TAG_RE.sub("", str(value or "")))
    text = _BLANK_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _ids(value: Any) -> list[str]:
    if isinstance(value, (str, int)):
        parts = str(value).split(",")
    elif isinstance(value, (list, tuple)):
        parts = [str(item) for item in value]
    else:
        parts = []
    return [part for part in (item.strip() for item in parts) if part]


class BilibiliReadSkill(SkillModule):
    """B站只读查询 Skill。"""

    def __init__(
        self,
        service: Any = None,
        client: Any = None,
        read_api: Any = None,
    ) -> None:
        self._service = service
        self._client = client
        self._api = read_api

    @property
    def name(self) -> str:
        return "bilibili_read"

    @property
    def description(self) -> str:
        return "B站只读查询：动态、专栏、番剧、用户名片、直播状态、视频流、弹幕与 b23 短链解析"

    @property
    def instructions(self) -> str:
        return (
            "B站只读查询 Skill（只读取，不会发评论/私信/动态或点赞）：\n\n"
            "  dynamic_detail — 按动态ID查动态详情。\n"
            "  user_dynamics — 查用户空间的最新动态列表（默认20条）。\n"
            "  article — 查专栏：cv_id 取标题/作者/正文；ids 批量取卡片信息。\n"
            "  bangumi — 按 ep_id 或 season_id 查番剧信息；同时给 cid 时附带该集流地址。\n"
            "  user_card — 查用户名片、粉丝数与投稿统计。\n"
            "  user_live_status — 查用户直播状态（live_status=1 表示直播中）。\n"
            "  video_stream — 按 bvid+cid 取 DASH/FLV 播放流地址。\n"
            "  video_danmaku — 按 cid 读取 XML 弹幕（文本/出现时间/模式/颜色）。\n"
            "  expand_b23 — 跟随 b23.tv 短链跳转，拿到真实链接与 BV 号。\n\n"
            "所有结果都是只读数据；接口失败会返回中文 error，不要编造结果。"
            "需要登录态，未登录时先发 /login bilibili 扫码登录。"
        )

    def get_tools(self) -> list[dict]:
        if not self._has_source():
            return []
        return [
            self._tool_def(
                "dynamic_detail",
                "只读：按动态ID查询B站动态详情（图文/转发/视频等类型）。",
                {
                    "properties": {
                        "dynamic_id": {
                            "type": "string",
                            "description": "动态ID（纯数字串）",
                        },
                    },
                    "required": ["dynamic_id"],
                },
            ),
            self._tool_def(
                "user_dynamics",
                "只读：查询B站用户空间的最新动态列表（不支持翻页）。",
                {
                    "properties": {
                        "mid": {"type": "integer", "description": "B站用户UID"},
                        "limit": {
                            "type": "integer",
                            "description": "最多返回多少条动态，默认20",
                            "default": 20,
                        },
                    },
                    "required": ["mid"],
                },
            ),
            self._tool_def(
                "article",
                "只读：查询B站专栏文章。传 cv_id 取标题/作者/正文，传 ids 批量取卡片信息。",
                {
                    "properties": {
                        "cv_id": {
                            "type": ["integer", "string"],
                            "description": "专栏CV号（如 777 或 cv777）",
                        },
                        "ids": {
                            "type": "string",
                            "description": "逗号分隔的专栏/视频/直播间ID，用于查卡片",
                        },
                        "include_content": {
                            "type": "boolean",
                            "description": "是否同时取正文，默认true",
                            "default": True,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "bangumi",
                "只读：按 ep_id 或 season_id 查询番剧信息；提供 cid 时附带该集流地址。",
                {
                    "properties": {
                        "ep_id": {
                            "type": "string",
                            "description": "剧集EP ID（如 ep330798）",
                        },
                        "season_id": {
                            "type": "string",
                            "description": "番剧季度SS ID（如 ss33802）",
                        },
                        "cid": {
                            "type": "integer",
                            "description": "分集 cid；提供时额外取该集流地址",
                            "default": 0,
                        },
                        "qn": {
                            "type": "integer",
                            "description": "清晰度代码，默认80",
                            "default": 80,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "user_card",
                "只读：查询B站用户名片（昵称、签名、等级、认证）与粉丝/投稿统计。",
                {
                    "properties": {
                        "mid": {"type": "integer", "description": "B站用户UID"},
                    },
                    "required": ["mid"],
                },
            ),
            self._tool_def(
                "user_live_status",
                "只读：查询B站用户的直播状态与直播间信息（live_status=1 表示直播中）。",
                {
                    "properties": {
                        "mid": {"type": "integer", "description": "B站用户UID"},
                    },
                    "required": ["mid"],
                },
            ),
            self._tool_def(
                "video_stream",
                "只读：按 bvid 和 cid 获取视频播放流地址（DASH 或 FLV）。",
                {
                    "properties": {
                        "bvid": {"type": "string", "description": "视频BV号"},
                        "cid": {"type": "integer", "description": "分P的 cid"},
                        "qn": {
                            "type": "integer",
                            "description": "清晰度代码，默认80",
                            "default": 80,
                        },
                    },
                    "required": ["bvid", "cid"],
                },
            ),
            self._tool_def(
                "video_danmaku",
                "只读：按 cid 读取视频 XML 弹幕（文本、出现时间、模式、颜色）。",
                {
                    "properties": {
                        "cid": {"type": "integer", "description": "分P的 cid"},
                        "limit": {
                            "type": "integer",
                            "description": "最多返回多少条弹幕，默认100",
                            "default": 100,
                        },
                    },
                    "required": ["cid"],
                },
            ),
            self._tool_def(
                "expand_b23",
                "只读：跟随 b23.tv 短链跳转，返回真实链接与解析出的 BV 号。",
                {
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "b23.tv 短链（可省略 https://）",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"未知工具: {tool_name}"})
        try:
            await self._ensure_login()
            result = await handler(self._resolve_api(), args)
        except _Unavailable as exc:
            return _json({"ok": False, "error": str(exc)})
        except Exception as exc:
            logger.warning(f"B站只读查询失败：{tool_name}：{type(exc).__name__}: {exc}")
            return _json({"ok": False, "error": f"B站只读查询失败：{type(exc).__name__}: {exc}"})
        if result.get("ok"):
            result.setdefault("note", _READ_ONLY_NOTE)
        return _json(result)

    def reset(self) -> None:
        pass

    def _has_source(self) -> bool:
        return self._api is not None or self._client is not None or self._service is not None

    async def _ensure_login(self) -> None:
        """登录门禁：先让 service 自愈（refresh），仍不可用才报未登录并带原因。"""
        service = self._service
        if service is None:
            return
        refresh = getattr(service, "refresh", None)
        if callable(refresh):
            try:
                await call_client(refresh)
            except Exception as exc:
                logger.warning(f"B站只读登录态刷新失败：{type(exc).__name__}: {exc}")
        if getattr(service, "available", None) is False:
            raise _Unavailable(_dormant_reason(service))

    def _resolve_api(self) -> Any:
        if self._api is not None:
            return self._api
        client = self._client
        if client is None:
            service = self._service
            if service is None:
                raise _Unavailable("B站服务未配置，无法访问B站")
            if getattr(service, "available", None) is False:
                raise _Unavailable(_dormant_reason(service))
            client = getattr(service, "client", None)
        if client is None or not callable(getattr(client, "_fetch", None)):
            raise _Unavailable("B站客户端不可用（未登录或未配置）")
        return BilibiliReadApi(client)


async def _handle_dynamic_detail(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    dynamic_id = _text(args.get("dynamic_id"))
    if not dynamic_id:
        return {"ok": False, "error": "缺少 dynamic_id（动态ID）"}
    return await call_client(api.dynamic_detail, dynamic_id)


async def _handle_user_dynamics(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _int(args.get("mid"))
    if mid <= 0:
        return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
    return await call_client(api.user_dynamics, mid, limit=_int(args.get("limit")) or 20)


async def _handle_article(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    cv_id = _text(args.get("cv_id"))
    ids = _ids(args.get("ids"))
    if cv_id:
        result = await call_client(api.article_info, cv_id)
        if not result.get("ok") or not _flag(args.get("include_content"), True):
            return result
        content = await call_client(api.article_content, cv_id)
        if content.get("ok"):
            result["title"] = result.get("title") or content.get("title", "")
            result["author"] = content.get("author", "")
            body = _plain(content.get("content", ""))
            result["content"] = body[:_ARTICLE_CHARS]
            result["publish_time"] = content.get("publish_time", 0)
            if len(body) > _ARTICLE_CHARS:
                result["content_chars"] = len(body)
                result["content_truncated"] = True
        else:
            result["content_error"] = content.get("error", "正文读取失败")
        return result
    if ids:
        return await call_client(api.article_cards, ids)
    return {"ok": False, "error": "需要 cv_id（专栏号）或 ids（卡片ID列表）"}


async def _handle_bangumi(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    ep_id = _text(args.get("ep_id"))
    season_id = _text(args.get("season_id"))
    if not ep_id and not season_id:
        return {"ok": False, "error": "需要 ep_id 或 season_id（番剧ID）"}
    result = await call_client(api.bangumi_info, ep_id=ep_id, season_id=season_id)
    if not result.get("ok"):
        return result
    cid = _int(args.get("cid"))
    if cid <= 0:
        return result
    if not ep_id:
        result["stream_error"] = "提供 cid 时还需要 ep_id 才能取番剧流地址"
        return result
    stream = await call_client(api.bangumi_stream, ep_id, cid, qn=_int(args.get("qn")) or 80)
    if stream.get("ok"):
        result["stream"] = stream
    else:
        result["stream_error"] = stream.get("error", "番剧流地址读取失败")
    return result


async def _handle_user_card(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _int(args.get("mid"))
    if mid <= 0:
        return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
    return await call_client(api.user_card, mid)


async def _handle_user_live_status(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    mid = _int(args.get("mid"))
    if mid <= 0:
        return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
    return await call_client(api.user_live_status, mid)


async def _handle_video_stream(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    bvid = _text(args.get("bvid"))
    if not bvid:
        return {"ok": False, "error": "缺少 bvid（视频BV号）"}
    cid = _int(args.get("cid"))
    if cid <= 0:
        return {"ok": False, "error": "缺少或无效的 cid（分P ID）"}
    return await call_client(api.video_stream, bvid, cid, qn=_int(args.get("qn")) or 80)


async def _handle_video_danmaku(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    cid = _int(args.get("cid"))
    if cid <= 0:
        return {"ok": False, "error": "缺少或无效的 cid（分P ID）"}
    return await call_client(api.video_danmaku, cid, limit=_int(args.get("limit")) or 100)


async def _handle_expand_b23(api: Any, args: dict[str, Any]) -> dict[str, Any]:
    url = _text(args.get("url"))
    if not url:
        return {"ok": False, "error": "缺少 url（b23.tv 短链）"}
    return await call_client(api.expand_b23, url)


_HANDLERS = {
    "dynamic_detail": _handle_dynamic_detail,
    "user_dynamics": _handle_user_dynamics,
    "article": _handle_article,
    "bangumi": _handle_bangumi,
    "user_card": _handle_user_card,
    "user_live_status": _handle_user_live_status,
    "video_stream": _handle_video_stream,
    "video_danmaku": _handle_video_danmaku,
    "expand_b23": _handle_expand_b23,
}

"""B 站只读接口扩展：动态、专栏、番剧、名片、视频流、弹幕与短链解析。

只复用 BilibiliClient 的 GET 请求（_fetch / _request）和 WBI 签名，不做任何写操作。
所有失败都返回 {"ok": False, "error": "中文说明"}，不把异常抛给调用方。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

from ._compat import resolve_client
from .client import API_BASE, LIVE_API_BASE, parse_video_id
from .errors import BilibiliError

_DYNAMIC_DETAIL_URL = f"{API_BASE}/x/polymer/web-dynamic/v1/detail"
_USER_DYNAMICS_URL = f"{API_BASE}/x/polymer/web-dynamic/v1/feed/space"
_ARTICLE_INFO_URL = f"{API_BASE}/x/article/viewinfo"
_ARTICLE_CONTENT_URL = f"{API_BASE}/x/article/view"
_ARTICLE_CARDS_URL = f"{API_BASE}/x/article/cards"
_BANGUMI_INFO_URL = f"{API_BASE}/pgc/view/web/season"
_BANGUMI_STREAM_URL = f"{API_BASE}/pgc/player/web/playurl"
_USER_CARD_URL = f"{API_BASE}/x/web-interface/card"
_USER_LIVE_URL = f"{LIVE_API_BASE}/room/v1/Room/getRoomInfoOld"
_VIDEO_STREAM_URL = f"{API_BASE}/x/player/wbi/playurl"
_DANMAKU_URL = f"{API_BASE}/x/v1/dm/list.so"

_DYNAMIC_FEATURES = (
    "itemOpusStyle,opusBigCover,onlyfansVote,endFooterHidden,decorationCard,"
    "onlyfansAssetsV2,ugcDelete,onlyfansQaCard,editable,opusPrivateVisible,avatarAutoTheme"
)
_SPACE_FEATURES = (
    "itemOpusStyle,listOnlyfans,opusBigCover,onlyfansVote,forwardListHidden,decorationCard,"
    "commentsNewVersion,onlyfansAssetsV2,ugcDelete,onlyfansQaCard,avatarAutoTheme,"
    "sunflowerStyle,eva3CardOpus,eva3CardVideo,eva3CardComment"
)

_CV_PATTERN = re.compile(r"(?i)cv(\d+)")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _id_number(value: Any, prefix: str) -> int:
    """ep330798 / ss33802 / 纯数字 -> 数字 ID；无法识别返回 0。"""
    text = _text(value)
    if text.lower().startswith(prefix):
        text = text[len(prefix) :]
    return _int(text)


def _cv_number(value: Any) -> int:
    text = _text(value)
    match = _CV_PATTERN.search(text)
    if match:
        return _int(match.group(1))
    return _int(text)


def _id_list(ids: Any) -> list[str]:
    if isinstance(ids, (str, int)):
        parts = str(ids).split(",")
    elif isinstance(ids, Sequence):
        parts = [str(item) for item in ids]
    else:
        parts = []
    return [part for part in (item.strip() for item in parts) if part]


def _stream_fields(data: dict[str, Any], qn: int) -> dict[str, Any]:
    """从 playurl 的 data/result 里挑 DASH（优先 qn）或 FLV 流地址。"""
    dash = data.get("dash")
    if isinstance(dash, dict):
        videos = [
            item
            for item in dash.get("video") or []
            if isinstance(item, dict) and (item.get("base_url") or item.get("baseUrl"))
        ]
        if videos:
            best = next((item for item in videos if _int(item.get("id")) == qn), None)
            if best is None:
                best = max(videos, key=lambda item: _int(item.get("bandwidth")))
            return {
                "format": "dash",
                "url": str(best.get("base_url") or best.get("baseUrl")),
                "backup": [str(url) for url in best.get("backup_url") or best.get("backupUrl") or [] if url],
                "quality": _int(best.get("id")),
                "codecs": str(best.get("codecs") or ""),
            }
    segments = [item for item in data.get("durl") or [] if isinstance(item, dict) and item.get("url")]
    if segments:
        first = segments[0]
        return {
            "format": "flv",
            "url": str(first.get("url")),
            "backup": [str(url) for url in first.get("backup_url") or [] if url],
            "quality": _int(data.get("quality")),
            "codecs": "",
        }
    return {}


class BilibiliReadApi:
    """B 站只读接口集合；client 可传 BilibiliClient 或带 client 的服务门面。"""

    def __init__(self, client: Any) -> None:
        target = resolve_client(client)
        if target is None or not callable(getattr(target, "_fetch", None)):
            raise ValueError("B站客户端不可用（缺少 _fetch）")
        self._client = target

    # ── 动态 ──

    def dynamic_detail(self, dynamic_id: str | int) -> dict[str, Any]:
        """动态详情；返回 {"ok", "dynamic_id", "item"}。"""
        dynamic_id = _text(dynamic_id)
        if not dynamic_id:
            return {"ok": False, "error": "缺少动态ID"}
        result = self._data(
            _DYNAMIC_DETAIL_URL,
            {"id": dynamic_id, "features": _DYNAMIC_FEATURES},
            action="动态详情读取",
            headers={"Referer": "https://t.bilibili.com/"},
        )
        if not result["ok"]:
            return result
        item = result["data"].get("item")
        return {
            "ok": True,
            "dynamic_id": dynamic_id,
            "item": item if isinstance(item, dict) else result["data"],
        }

    def user_dynamics(self, mid: int, limit: int = 20) -> dict[str, Any]:
        """用户空间第一页动态；返回 {"ok", "mid", "count", "items", "has_more"}。"""
        mid = _int(mid)
        if mid <= 0:
            return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
        limit = max(1, _int(limit) or 20)
        params = self._client._sign_wbi({"host_mid": mid, "offset": "", "platform": "web", "features": _SPACE_FEATURES})
        result = self._data(
            _USER_DYNAMICS_URL,
            params,
            action="用户动态读取",
            headers={
                "Origin": "https://space.bilibili.com",
                "Referer": f"https://space.bilibili.com/{mid}/dynamic",
            },
        )
        if not result["ok"]:
            return result
        data = result["data"]
        items = [item for item in data.get("items") or [] if isinstance(item, dict)][:limit]
        return {
            "ok": True,
            "mid": mid,
            "count": len(items),
            "items": items,
            "has_more": bool(data.get("has_more")),
        }

    # ── 专栏 ──

    def article_info(self, cv_id: str | int) -> dict[str, Any]:
        """专栏元信息；返回 {"ok", "cv_id", "info"}。"""
        cv_id = _cv_number(cv_id)
        if cv_id <= 0:
            return {"ok": False, "error": "缺少或无效的 cv 号（专栏ID）"}
        result = self._data(_ARTICLE_INFO_URL, {"id": cv_id}, action="专栏信息读取")
        if not result["ok"]:
            return result
        return {"ok": True, "cv_id": cv_id, "info": result["data"]}

    def article_content(self, cv_id: str | int) -> dict[str, Any]:
        """专栏正文；返回 {"ok", "cv_id", "title", "author", "content", "publish_time"}。"""
        cv_id = _cv_number(cv_id)
        if cv_id <= 0:
            return {"ok": False, "error": "缺少或无效的 cv 号（专栏ID）"}
        result = self._data(_ARTICLE_CONTENT_URL, {"id": cv_id}, action="专栏正文读取")
        if not result["ok"]:
            return result
        data = result["data"]
        return {
            "ok": True,
            "cv_id": cv_id,
            "title": _text(data.get("title")),
            "author": _text(data.get("author_name")),
            "content": str(data.get("content") or ""),
            "publish_time": _int(data.get("publish_time")),
        }

    def article_cards(self, ids: str | Sequence[str]) -> dict[str, Any]:
        """专栏卡片信息；返回 {"ok", "ids", "cards"}。"""
        id_list = _id_list(ids)
        if not id_list:
            return {"ok": False, "error": "缺少 ids（要查询的专栏/视频/直播间ID）"}
        result = self._data(_ARTICLE_CARDS_URL, {"ids": ",".join(id_list)}, action="专栏卡片读取")
        if not result["ok"]:
            return result
        return {"ok": True, "ids": id_list, "cards": result["data"]}

    # ── 番剧 ──

    def bangumi_info(self, ep_id: str | int = "", season_id: str | int = "") -> dict[str, Any]:
        """番剧季度/单集信息；ep_id 优先；返回 {"ok", "ep_id", "season_id", "info"}。"""
        ep = _id_number(ep_id, "ep")
        season = _id_number(season_id, "ss")
        if ep <= 0 and season <= 0:
            return {"ok": False, "error": "需要 ep_id 或 season_id（番剧ID）"}
        params: dict[str, Any] = {"ep_id": ep} if ep > 0 else {"season_id": season}
        result = self._data(_BANGUMI_INFO_URL, params, action="番剧信息读取")
        if not result["ok"]:
            return result
        return {"ok": True, "ep_id": ep, "season_id": season, "info": result["data"]}

    def bangumi_stream(self, ep_id: str | int, cid: int, qn: int = 80) -> dict[str, Any]:
        """番剧分集流地址；返回 {"ok", "ep_id", "cid", "format", "url", ...}。"""
        ep = _id_number(ep_id, "ep")
        cid = _int(cid)
        qn = max(1, _int(qn) or 80)
        if ep <= 0:
            return {"ok": False, "error": "缺少或无效的 ep_id（番剧EP ID）"}
        if cid <= 0:
            return {"ok": False, "error": "缺少或无效的 cid（分集ID）"}
        result = self._data(
            _BANGUMI_STREAM_URL,
            {"ep_id": ep, "cid": cid, "qn": qn, "fnval": 4048, "fourk": 1},
            action="番剧流地址读取",
            headers={"Referer": f"https://www.bilibili.com/bangumi/play/ep{ep}"},
        )
        if not result["ok"]:
            return result
        stream = _stream_fields(result["data"], qn)
        if not stream:
            return {
                "ok": False,
                "error": "没有取到番剧流地址（可能需要登录或大会员权限）",
            }
        return {"ok": True, "ep_id": ep, "cid": cid, **stream}

    # ── 用户 ──

    def user_card(self, mid: int) -> dict[str, Any]:
        """用户名片与统计；返回 {"ok", "mid", "info"}。"""
        mid = _int(mid)
        if mid <= 0:
            return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
        result = self._data(
            _USER_CARD_URL,
            {"mid": mid, "photo": "true"},
            action="用户名片读取",
            headers={"Referer": f"https://space.bilibili.com/{mid}"},
        )
        if not result["ok"]:
            return result
        return {"ok": True, "mid": mid, "info": result["data"]}

    def user_card_detail(self, mid: int) -> dict[str, Any]:
        """名片归一化；成功返回资料与统计，失败原样透传 user_card 的错误。"""
        result = self.user_card(mid)
        if not result["ok"]:
            return result
        info = result["info"]
        card = info.get("card") if isinstance(info.get("card"), dict) else {}
        level_info = card.get("level_info") if isinstance(card.get("level_info"), dict) else {}
        uid = _int(card.get("mid")) or result["mid"]
        return {
            "ok": True,
            "uid": uid,
            "name": _text(card.get("name")),
            "sign": _text(card.get("sign")),
            "level": _int(level_info.get("current_level")),
            "fans": _int(card.get("fans") or info.get("follower")),
            "following": _int(card.get("attention")),
            "videos": _int(info.get("archive_count")),
            "articles": _int(info.get("article_count")),
            "likes": _int(info.get("like_num")),
            "face": _text(card.get("face")),
            "url": f"https://space.bilibili.com/{uid}" if uid else "",
        }

    def user_live_status(self, mid: int) -> dict[str, Any]:
        """用户直播状态；返回 {"ok", "mid", "info"}（info.live_status=1 为直播中）。"""
        mid = _int(mid)
        if mid <= 0:
            return {"ok": False, "error": "缺少或无效的 mid（B站UID）"}
        result = self._data(
            _USER_LIVE_URL,
            {"mid": mid},
            action="直播状态读取",
            headers={"Referer": f"https://space.bilibili.com/{mid}"},
        )
        if not result["ok"]:
            return result
        return {"ok": True, "mid": mid, "info": result["data"]}

    # ── 视频 ──

    def video_stream(self, bvid: str, cid: int, qn: int = 80) -> dict[str, Any]:
        """视频播放流；返回 {"ok", "bvid", "cid", "format", "url", "backup", ...}。"""
        parsed_bvid, _ = parse_video_id(bvid)
        bvid = parsed_bvid or _text(bvid)
        cid = _int(cid)
        qn = max(1, _int(qn) or 80)
        if not bvid:
            return {"ok": False, "error": "缺少或无效的 bvid（BV号）"}
        if cid <= 0:
            return {"ok": False, "error": "缺少或无效的 cid（分P ID）"}
        params = self._client._sign_wbi({"bvid": bvid, "cid": cid, "qn": qn, "fnval": 4048, "fourk": 1})
        result = self._data(
            _VIDEO_STREAM_URL,
            params,
            action="视频流地址读取",
            headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
        )
        if not result["ok"]:
            return result
        data = result["data"]
        stream = _stream_fields(data, qn)
        if not stream:
            return {
                "ok": False,
                "error": "没有取到视频流地址（可能需要登录或大会员权限）",
            }
        qualities = [_int(item) for item in data.get("accept_quality") or []]
        return {
            "ok": True,
            "bvid": bvid,
            "cid": cid,
            **stream,
            "accept_quality": [item for item in qualities if item > 0],
        }

    def video_danmaku(self, cid: int, limit: int = 100) -> dict[str, Any]:
        """XML 弹幕；返回 {"ok", "cid", "count", "danmakus": [text/time/mode/color]}。"""
        cid = _int(cid)
        if cid <= 0:
            return {"ok": False, "error": "缺少或无效的 cid（分P ID）"}
        limit = min(max(1, _int(limit) or 100), 1000)
        try:
            text = self._client.fetch_text(f"{_DANMAKU_URL}?oid={cid}")
        except Exception as exc:  # 只读接口失败一律降级
            return {"ok": False, "error": f"弹幕读取失败：{type(exc).__name__}: {exc}"}
        if not text:
            return {"ok": False, "error": "弹幕读取失败（接口没有返回内容）"}
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError as exc:
            return {"ok": False, "error": f"弹幕解析失败：{exc}"}
        danmakus: list[dict[str, Any]] = []
        for node in root.iter("d"):
            parts = str(node.get("p") or "").split(",")
            if len(parts) < 4:
                continue
            danmakus.append(
                {
                    "text": node.text or "",
                    "time": _float(parts[0]),
                    "mode": _int(parts[1]),
                    "color": _int(parts[3]),
                }
            )
            if len(danmakus) >= limit:
                break
        return {"ok": True, "cid": cid, "count": len(danmakus), "danmakus": danmakus}

    # ── 短链 ──

    def expand_b23(self, url: str) -> dict[str, Any]:
        """跟随 b23.tv 短链跳转；返回 {"ok", "url", "bvid", "aid"}。"""
        text = _text(url)
        if not text:
            return {"ok": False, "error": "缺少 url（b23.tv 短链）"}
        if not text.startswith(("http://", "https://")):
            text = f"https://{text}"
        parsed = urlparse(text)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {"ok": False, "error": f"无法识别的链接：{text}"}
        try:
            response = self._client._request("GET", text)
        except Exception as exc:
            return {"ok": False, "error": f"短链解析失败：{exc}"}
        if response is None:
            return {"ok": False, "error": "短链解析失败：网络请求失败"}
        final = _text(getattr(response, "url", "")) or text
        if final == text and parsed.netloc.lower().endswith("b23.tv"):
            return {"ok": False, "error": "短链没有跳转（可能已失效）"}
        bvid, aid = parse_video_id(final)
        return {"ok": True, "url": final, "bvid": bvid, "aid": aid}

    # ── 内部 ──

    def _data(
        self,
        url: str,
        params: dict[str, Any],
        *,
        action: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = self._client._fetch("GET", url, params=params, headers=headers)
        except BilibiliError as exc:
            return {"ok": False, "error": f"{action}失败：{exc}"}
        except Exception as exc:  # 只读接口失败一律降级，不抛给调用方
            return {"ok": False, "error": f"{action}失败：{type(exc).__name__}: {exc}"}
        data = payload.get("data")
        if data is None:
            data = payload.get("result")  # PGC 接口把数据放在 result
        if not isinstance(data, dict):
            return {"ok": False, "error": f"{action}失败：接口没有返回数据"}
        return {"ok": True, "data": data}

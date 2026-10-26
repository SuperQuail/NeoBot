"""评论与通知流：读取、回复、点赞。"""

from __future__ import annotations

import json
from typing import Any

from ..errors import BilibiliError
from .common import (
    _AT_FEED_URL,
    _COMMENT_ACTION_URL,
    _COMMENT_ADD_URL,
    _COMMENT_MAIN_URL,
    _COMMENT_MODES,
    _COMMENT_REPLIES_URL,
    _COMMENT_TYPES,
    _REPLY_FEED_URL,
    _empty_comment_page,
    _to_int,
)


class _CommentMixin:
    """评论、楼中楼与「回复我的 / @我的」通知流。"""

    # ── 评论 / 回复 ──

    def get_reply_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取「回复我的」评论通知列表（msgfeed/reply 的 items 原样）。"""
        params = {"platform": "web", "build": 0, "mobi_app": "web"}
        try:
            payload = self._fetch("GET", _REPLY_FEED_URL, params=params)
        except BilibiliError as exc:
            self._log_read_error("评论回复读取", exc)
            return []
        data = payload.get("data")
        items = data.get("items") if isinstance(data, dict) else None
        return [item for item in items or [] if isinstance(item, dict)][: max(int(limit), 0)]

    def get_at_feed(self, limit: int = 20) -> list[dict[str, Any]]:
        """获取「@我的」通知列表（msgfeed/at 的 items 原样）。"""
        params = {"platform": "web", "build": 0, "mobi_app": "web"}
        try:
            payload = self._fetch(
                "GET",
                _AT_FEED_URL,
                params=params,
                # 消息中心接口要求带上它自己的页面上下文，否则可能被风控拒绝。
                headers={
                    "Referer": "https://message.bilibili.com/",
                    "Origin": "https://message.bilibili.com",
                },
            )
        except BilibiliError as exc:
            self._log_read_error("提到我的读取", exc)
            return []
        data = payload.get("data")
        items = data.get("items") if isinstance(data, dict) else None
        return [item for item in items or [] if isinstance(item, dict)][: max(int(limit), 0)]

    def get_comments(
        self,
        oid: int,
        comment_type: int = 1,
        *,
        mode: str = "hot",
        cursor: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """拉一页评论区（wbi/main）：返回 {items, cursor, is_end, raw}。

        comment_type 见 _COMMENT_TYPES（视频 1、动态 17、专栏/opus 12、番剧 11）；
        cursor 传上一页返回的 cursor，空串表示第一页。失败返回空页。
        page_size 会作为 ps 交给接口，本地不再截断——先截断再用服务端游标翻页会丢评论。
        """
        oid = _to_int(oid)
        comment_type = _to_int(comment_type)
        if oid <= 0 or comment_type not in _COMMENT_TYPES:
            return _empty_comment_page()
        page_size = max(_to_int(page_size) or 20, 1)
        params = self._sign_wbi(
            {
                "oid": oid,
                "type": comment_type,
                "mode": _COMMENT_MODES.get(str(mode).strip().lower(), 3),
                "plat": 1,
                "ps": page_size,
                "seek_rpid": "",
                "web_location": "1315875",
                "pagination_str": json.dumps(
                    {"offset": str(cursor or "")}, separators=(",", ":")
                ),
            }
        )
        try:
            payload = self._fetch("GET", _COMMENT_MAIN_URL, params=params)
        except BilibiliError as exc:
            self._log_read_error("评论读取", exc)
            return _empty_comment_page()
        data = payload.get("data")
        if not isinstance(data, dict):
            return _empty_comment_page()
        items: list[dict[str, Any]] = []
        seen: set[int] = set()
        for item in data.get("replies") or []:
            if not isinstance(item, dict):
                continue
            rpid = _to_int(item.get("rpid"))
            if rpid and rpid in seen:  # 翻页边界会重复给同一条评论
                continue
            seen.add(rpid)
            items.append(item)
        cursor_info = data.get("cursor")
        cursor_info = cursor_info if isinstance(cursor_info, dict) else {}
        pagination = cursor_info.get("pagination_reply")
        next_offset = pagination.get("next_offset") if isinstance(pagination, dict) else ""
        return {
            "items": items,
            "cursor": str(next_offset or ""),
            "is_end": bool(cursor_info.get("is_end")) or not next_offset,
            "raw": data,
        }

    def get_work_comments(
        self,
        identifier: str,
        comment_type: int = 1,
        *,
        mode: str = "hot",
        cursor: str | None = None,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """按作品标识拉评论：视频 BV/av/链接先解析成 aid，动态/专栏/opus 用数字 ID。"""
        oid = self._resolve_comment_oid(identifier)
        if oid <= 0:
            self._logger.warning(f"B站评论读取失败：无法解析作品号 {identifier!r}")
            return _empty_comment_page()
        return self.get_comments(
            oid, comment_type, mode=mode, cursor=cursor, page_size=page_size
        )

    def get_video_comments(
        self, oid: int, page: int = 1, *, order: str = "time"
    ) -> list[dict[str, Any]]:
        """兼容旧接口：视频评论区（type=1）。page>1 时沿游标翻到第 page 页。"""
        page = max(_to_int(page) or 1, 1)
        result = self.get_comments(oid, 1, mode=order)
        for _ in range(page - 1):
            if result["is_end"] or not result["cursor"]:
                return []
            result = self.get_comments(oid, 1, mode=order, cursor=result["cursor"])
        return result["items"]

    def get_comment_replies(
        self,
        oid: int,
        root: int,
        *,
        page: int = 1,
        page_size: int = 20,
        type_: int = 1,
        cursor: str | int | None = None,
        pn: int | None = None,
        ps: int | None = None,
    ) -> list[dict[str, Any]]:
        """获取一条根评论下的楼中楼回复（reply/reply 的 replies）；失败返回空列表。

        cursor/pn 是页码（兼容旧游标参数），ps 覆盖 page_size，type_ 是评论区类型。
        """
        oid = _to_int(oid)
        root = _to_int(root)
        if oid <= 0 or root <= 0:
            return []
        type_code = _to_int(type_)
        if type_code not in _COMMENT_TYPES:
            type_code = 1
        page_no = max(_to_int(pn) or _to_int(cursor) or _to_int(page) or 1, 1)
        page_len = max(_to_int(ps) or _to_int(page_size) or 20, 1)
        params = self._sign_wbi(
            {
                "type": type_code,
                "oid": oid,
                "root": root,
                "pn": page_no,
                "ps": page_len,
            }
        )
        try:
            payload = self._fetch("GET", _COMMENT_REPLIES_URL, params=params)
        except BilibiliError as exc:
            self._log_read_error("楼中楼回复读取", exc)
            return []
        data = payload.get("data")
        replies = data.get("replies") if isinstance(data, dict) else None
        return [item for item in replies or [] if isinstance(item, dict)]

    def send_comment_reply(
        self, oid: int, root: int, parent: int, text: str, *, type_: int = 1
    ) -> bool:
        """回复评论。oid=稿件/动态 ID，root=根评论 rpid，parent=被回复评论 rpid。"""
        message = (text or "").strip()
        if not oid or not message:
            self._logger.warning("B站评论回复参数不完整（oid/text 不能为空）")
            return False
        form: dict[str, Any] = {
            "oid": _to_int(oid),
            "type": _to_int(type_),
            "message": message,
            "plat": 1,
            "csrf": self._bili_jct,
        }
        if root:
            form["root"] = _to_int(root)
        if parent:
            form["parent"] = _to_int(parent)
        self._rate_limit_wait()
        try:
            payload = self._fetch(
                "POST",
                _COMMENT_ADD_URL,
                data=form,
                headers={"Referer": "https://www.bilibili.com/"},
            )
        except BilibiliError as exc:
            self._on_write_error("评论回复", exc)
            return False
        data = payload.get("data")
        rpid = data.get("rpid") if isinstance(data, dict) else 0
        self._logger.info(f"B站评论回复成功: oid={oid} root={root} parent={parent} rpid={rpid}")
        return True

    def post_video_comment(
        self, identifier: str, text: str, *, root: int = 0, parent: int = 0
    ) -> bool:
        """给视频发评论/回复：identifier 支持 BV/av/URL，root/parent 为 0 时发顶级评论。"""
        message = (text or "").strip()
        if not message:
            self._logger.warning("B站视频评论参数不完整（text 不能为空）")
            return False
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频评论失败：无法解析视频号 {identifier!r}")
            return False
        return self.send_comment_reply(aid, root, parent, message, type_=1)

    def like_comment(self, oid: int, rpid: int, type_: int = 1) -> bool:
        """点赞评论。oid=稿件/动态 ID，rpid=评论 ID，type_=评论区类型（视频为 1）。"""
        if not oid or not rpid:
            self._logger.warning("B站评论点赞参数不完整（oid/rpid 不能为空）")
            return False
        form: dict[str, Any] = {
            "oid": _to_int(oid),
            "rpid": _to_int(rpid),
            "action": 1,
            "type": _to_int(type_),
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _COMMENT_ACTION_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("评论点赞", exc)
            return False
        self._logger.info(f"B站评论点赞成功: oid={oid} rpid={rpid}")
        return True

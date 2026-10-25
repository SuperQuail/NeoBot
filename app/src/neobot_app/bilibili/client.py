"""B 站 HTTP 客户端：登录态校验、评论/私信读写、动态发布、视频点赞与直播弹幕。

所有方法都是同步实现（requests）。需要 async 的调用方用 asyncio.to_thread
包一层即可（BilibiliService 已经这样做）。

写操作（发评论/私信/动态）统一走 _rate_limit_wait() 限速；只有幂等的 GET/HEAD 在
网络错误与 HTTP 5xx 时退避重试 2 次（写请求不重试，避免重复发评论/私信/投币）；
B 站业务错误码不重试，-352（WBI 签名失效）重取密钥后再试一次。
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import threading
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

import requests

from neobot_contracts.ports.logging import Logger, NullLogger

from .errors import BilibiliApiError, BilibiliAuthError, BilibiliError

API_BASE = "https://api.bilibili.com"
VC_BASE = "https://api.vc.bilibili.com"
_NAV_URL = f"{API_BASE}/x/web-interface/nav"
_REPLY_FEED_URL = f"{API_BASE}/x/msgfeed/reply"
_AT_FEED_URL = f"{API_BASE}/x/msgfeed/at"
_COMMENT_MAIN_URL = f"{API_BASE}/x/v2/reply/wbi/main"
_COMMENT_ADD_URL = f"{API_BASE}/x/v2/reply/add"
_COMMENT_REPLIES_URL = f"{API_BASE}/x/v2/reply/reply"
_DYNAMIC_CREATE_URL = f"{API_BASE}/x/dynamic/feed/create/dyn"
_DYNAMIC_IMAGE_UPLOAD_URL = f"{API_BASE}/x/dynamic/feed/draw/upload_bfs"
_SEARCH_URL = f"{API_BASE}/x/web-interface/wbi/search/type"
_VIDEO_VIEW_URL = f"{API_BASE}/x/web-interface/view"
_SPACE_INFO_URL = f"{API_BASE}/x/space/wbi/acc/info"
_SPACE_VIDEOS_URL = f"{API_BASE}/x/space/arc/search"
_PLAYER_INFO_URL = f"{API_BASE}/x/player/wbi/v2"
_PLAYURL_URL = f"{API_BASE}/x/player/wbi/playurl"
_VIDEO_LIKE_URL = f"{API_BASE}/x/web-interface/archive/like"
_VIDEO_COIN_URL = f"{API_BASE}/x/web-interface/coin/add"
_VIDEO_SHARE_URL = f"{API_BASE}/x/web-interface/share/add"
_FAV_FOLDER_LIST_URL = f"{API_BASE}/x/v3/fav/folder/created/list-all"
_FAV_RESOURCE_DEAL_URL = f"{API_BASE}/x/v3/fav/resource/deal"
_RELATION_MODIFY_URL = f"{API_BASE}/x/relation/modify"
MAX_LIVE_DANMAKU_CHARS = 20
_COMMENT_ACTION_URL = f"{API_BASE}/x/v2/reply/action"

LIVE_API_BASE = "https://api.live.bilibili.com"
_LIVE_ROOM_INFO_URL = f"{LIVE_API_BASE}/xlive/web-room/v1/index/getInfoByRoom"
_LIVE_PLAY_INFO_URL = f"{LIVE_API_BASE}/xlive/web-room/v2/index/getRoomPlayInfo"
_LIVE_DANMU_INFO_URL = f"{LIVE_API_BASE}/xlive/web-room/v1/index/getDanmuInfo"
_LIVE_SEND_DANMAKU_URL = f"{LIVE_API_BASE}/msg/send"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
DEFAULT_DEVICE_ID = "B1994F2C-C5C9-4C0E-8F4C-F8E5F7E8F9E0"

#: WBI 签名用的固定置换表（B 站 web 端一致）。
_WBI_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
)
_WBI_FILTERED_CHARS = frozenset("!'()*")

#: 命中这些业务错误码时加大写操作冷却时间（风控/评论限流）。
_WRITE_RETRY_CODES = frozenset({-412, -429, -799})
#: 这些 HTTP 状态码说明请求被 B 站风控拦下（不是业务错误，也不该重试）。
_RISK_CONTROL_STATUS = frozenset({412, 429})
#: 只有幂等方法重试安全；POST 重发会重复发评论/私信/弹幕/投币。
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})

#: 评论区类型（reply/type）：视频 1、动态 17、专栏/opus 12、番剧 11；3 与 23~32 未使用。
_COMMENT_TYPES = frozenset(
    {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 33}
)
#: 排序：mode 2=按时间，3=按热度。
_COMMENT_MODES = {"hot": 3, "time": 2}

_BV_PATTERN = re.compile(r"(?i)bv1[0-9a-z]{9}")
_AV_PATTERN = re.compile(r"(?i)(?<![0-9a-z])av(\d+)")


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _empty_comment_page() -> dict[str, Any]:
    """评论页读取失败时的空结果（结构固定，调用方不用判空）。"""
    return {"items": [], "cursor": "", "is_end": True, "raw": {}}


def parse_video_id(identifier: str) -> tuple[str, int]:
    """解析 BV 号 / av 号 / 视频 URL，返回 (bvid, aid)；识别失败返回 ("", 0)。"""
    text = (identifier or "").strip()
    match = _BV_PATTERN.search(text)
    if match:
        return "BV" + match.group(0)[2:], 0
    match = _AV_PATTERN.search(text)
    if match:
        return "", int(match.group(1))
    return "", 0


def _live_stream_url(codec: Mapping[str, Any]) -> tuple[str, int]:
    """用 host+base_url+extra 拼直播拉流地址，并推算剩余有效秒数；字段缺失返回 ("", 0)。"""
    url_info = codec.get("url_info")
    info = (
        url_info[0]
        if isinstance(url_info, list) and url_info and isinstance(url_info[0], dict)
        else {}
    )
    host = str(codec.get("host") or info.get("host") or "").strip()
    base_url = str(codec.get("base_url") or codec.get("baseUrl") or "")
    extra = str(codec.get("extra") or info.get("extra") or "")
    if not host or not base_url:
        return "", 0
    if base_url.endswith("?") and extra.startswith("?"):
        extra = extra[1:]
    expires = _to_int(
        codec.get("ttl")
        or codec.get("stream_ttl")
        or info.get("ttl")
        or info.get("stream_ttl")
    )
    if expires <= 0 and extra:
        # 实测 stream_ttl 常为 0，地址有效期在 extra 的 expires/deadline 绝对时间戳里。
        query = parse_qs(extra.lstrip("?"))
        epoch = _to_int((query.get("expires") or query.get("deadline") or [0])[0])
        expires = max(epoch - int(time.time()), 0) if epoch > 0 else 0
    return f"{host}{base_url}{extra}", expires


@dataclass
class BilibiliMessage:
    """B 站私信消息。"""

    talker_id: int
    sender_uid: int
    msg_type: int
    content: str
    timestamp: int
    msg_key: str = ""
    is_self: bool = False

    @property
    def text(self) -> str:
        """纯文本消息的正文；图片等非文本消息返回空串。"""
        if self.msg_type != 1:
            return ""
        try:
            return str(json.loads(self.content).get("content", ""))
        except (ValueError, TypeError, AttributeError):
            return self.content

    @classmethod
    def from_api(cls, raw: Mapping[str, Any], my_uid: int = 0) -> BilibiliMessage:
        content = raw.get("content", "")
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        sender_uid = _to_int(raw.get("sender_uid"))
        talker_id = _to_int(raw.get("receiver_id")) or sender_uid
        message = cls(
            talker_id=talker_id,
            sender_uid=sender_uid,
            msg_type=_to_int(raw.get("msg_type")) or 1,
            content=str(content),
            timestamp=_to_int(raw.get("timestamp")),
        )
        message.is_self = bool(my_uid and sender_uid == my_uid)
        message.msg_key = f"{message.talker_id}_{message.timestamp}_{message.content[:20]}"
        return message


@dataclass
class BilibiliSession:
    """B 站私信会话。"""

    talker_id: int
    last_msg: BilibiliMessage | None = None

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> BilibiliSession:
        session = cls(talker_id=_to_int(raw.get("talker_id")))
        last_msg = raw.get("last_msg")
        if isinstance(last_msg, dict) and last_msg:
            session.last_msg = BilibiliMessage.from_api(last_msg)
        return session


class BilibiliClient:
    """B 站 Web API 同步客户端。"""

    _MAX_RETRIES = 2
    _RETRY_DELAY_SECONDS = 0.5
    _DEFAULT_WRITE_INTERVAL_SECONDS = 1.0
    _MAX_WRITE_INTERVAL_SECONDS = 60.0
    #: WBI 密钥有效期；过期后重新从 nav 接口取，避免长期用失效密钥被 -352。
    _WBI_KEY_TTL_SECONDS = 1800.0

    def __init__(
        self,
        sessdata: str,
        bili_jct: str,
        uid: int = 0,
        *,
        buvid3: str = "",
        logger: Logger | None = None,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        if not sessdata or not bili_jct:
            raise ValueError("SESSDATA 和 bili_jct 不能为空")
        self._sessdata = sessdata
        self._bili_jct = bili_jct
        self._my_uid = int(uid or 0)
        self._buvid3 = buvid3
        self._logger = logger or NullLogger()
        self._timeout = timeout
        # 外部传入的 session 归调用方所有，close() 不关它。
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._session.headers.update(
            {
                "User-Agent": user_agent,
                "Referer": "https://www.bilibili.com/",
                "Origin": "https://www.bilibili.com",
                "Accept": "application/json, text/plain, */*",
            }
        )
        jar = self._session.cookies
        jar.set("SESSDATA", sessdata, domain=".bilibili.com", path="/")
        jar.set("bili_jct", bili_jct, domain=".bilibili.com", path="/")
        if self._my_uid:
            jar.set("DedeUserID", str(self._my_uid), domain=".bilibili.com", path="/")
        if buvid3:
            jar.set("buvid3", buvid3, domain=".bilibili.com", path="/")

        # 并发安全：任务模块可能从多个线程调用同一个客户端。锁只保护 cookie/限速状态，
        # 不包网络 I/O；requests.Session 不保证跨线程安全，所以每个线程用自己的 Session
        # （创建线程继续用 self._session，其余线程复制一份）。
        self._lock = threading.Lock()
        self._local = threading.local()
        self._local.session = self._session
        # 限速：写操作之间的最小间隔，命中风控后自适应放大，风控过去后逐步回落。
        self._write_interval = self._DEFAULT_WRITE_INTERVAL_SECONDS
        self._last_write_at = 0.0
        # WBI 签名密钥缓存（带有效期）。
        self._wbi_mixin_key = ""
        self._wbi_key_at = 0.0
        # 私信去重缓存。
        self._seen_msg_keys: set[str] = set()
        self._last_msg_times: dict[int, int] = defaultdict(int)

    # ── 认证 ──

    @property
    def my_uid(self) -> int:
        """自己的 UID；构造时未给则尝试从 nav 接口取一次（取不到返回 0）。"""
        if self._my_uid > 0:
            return self._my_uid
        try:
            self._my_uid = _to_int(self.get_my_info().get("mid"))
        except BilibiliError as exc:
            self._log_read_error("UID 读取", exc)
            self._my_uid = 0
        return self._my_uid

    def get_my_info(self) -> dict[str, Any]:
        """nav 接口的 data 原样返回（mid/uname/face/isLogin/wbi_img 等）。

        登录失效（-101 或 isLogin=False）抛 BilibiliAuthError；网络/5xx/非法 JSON
        抛 BilibiliApiError —— 调用方必须能区分「接口失败」和「未登录」，不能靠空 dict。
        """
        payload = self._fetch("GET", _NAV_URL)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliApiError(-1, "B站账号信息接口没有返回 data")
        wbi_img = data.get("wbi_img")
        if isinstance(wbi_img, dict):
            self._cache_wbi_keys(wbi_img)
        if not data.get("isLogin"):
            raise BilibiliAuthError("B站未登录或登录态已过期")
        mid = _to_int(data.get("mid"))
        if mid <= 0:
            raise BilibiliAuthError("B站账号信息缺少 mid，登录态无效")
        self._my_uid = mid
        return data

    def verify_auth(self) -> bool:
        """当前 cookie 是否仍处于登录态（网络异常也按 False 处理，bool 没有第三态）。"""
        try:
            self.get_my_info()
        except BilibiliError as exc:
            self._log_read_error("登录态校验", exc)
            return False
        return True

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

    # ── 搜索 / 视频 / 用户空间 ──

    def search(
        self,
        keyword: str,
        *,
        search_type: str = "video",
        page: int = 1,
        page_size: int = 20,
        order: str = "totalrank",
    ) -> dict[str, Any]:
        """综合搜索，返回 data 原样（视频搜索的结果在 data["result"]）；失败返回空 dict。"""
        text = (keyword or "").strip()
        if not text:
            return {}
        params = self._sign_wbi(
            {
                "search_type": search_type or "video",
                "keyword": text,
                "page": max(_to_int(page), 1),
                "page_size": max(_to_int(page_size), 1),
                "order": order or "totalrank",
            }
        )
        try:
            payload = self._fetch(
                "GET",
                _SEARCH_URL,
                params=params,
                headers={"Referer": "https://search.bilibili.com/"},
            )
        except BilibiliError as exc:
            self._log_read_error("视频搜索", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_video_info(self, identifier: str) -> dict[str, Any]:
        """视频信息（view 接口的 data）；identifier 支持 BV 号 / av 号 / 视频 URL。"""
        bvid, aid = parse_video_id(identifier)
        if not bvid and not aid:
            self._logger.warning(f"B站视频号解析失败: {identifier!r}")
            return {}
        params: dict[str, Any] = {"bvid": bvid} if bvid else {"aid": aid}
        try:
            payload = self._fetch("GET", _VIDEO_VIEW_URL, params=params)
        except BilibiliError as exc:
            self._log_read_error("视频信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def like_video(self, identifier: str) -> bool:
        """给视频点赞：identifier 支持 BV/av/URL（BV 会先查 aid）。"""
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频点赞失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {"aid": aid, "like": 1, "csrf": self._bili_jct}
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_LIKE_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频点赞", exc)
            return False
        self._logger.info(f"B站视频点赞成功: aid={aid}")
        return True

    def coin_video(self, identifier: str, multiply: int = 1) -> bool:
        """给视频投币：multiply=1 投一枚、2 投两枚；identifier 支持 BV/av/URL。"""
        if not self._require_login("视频投币"):
            return False
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频投币失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {
            "aid": aid,
            "multiply": 2 if _to_int(multiply) >= 2 else 1,
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_COIN_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频投币", exc)
            return False
        self._logger.info(f"B站视频投币成功: aid={aid} multiply={form['multiply']}")
        return True

    def share_video(self, identifier: str) -> bool:
        """把视频分享到动态：identifier 支持 BV/av/URL（av 会先查 bvid）。"""
        if not self._require_login("视频分享"):
            return False
        bvid, aid = parse_video_id(identifier)
        if not bvid and aid:
            bvid = str(self.get_video_info(f"av{aid}").get("bvid") or "").strip()
        if not bvid:
            self._logger.warning(f"B站视频分享失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {"bvid": bvid, "csrf": self._bili_jct}
        self._rate_limit_wait()
        try:
            self._fetch("POST", _VIDEO_SHARE_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频分享", exc)
            return False
        self._logger.info(f"B站视频分享成功: bvid={bvid}")
        return True

    def get_favorite_folders(self) -> list[dict[str, Any]]:
        """当前账号自建的收藏夹列表（folder/created/list-all 的 data.list）；失败返回空列表。"""
        if not self._require_login("收藏夹读取"):
            return []
        up_mid = self.my_uid
        if up_mid <= 0:
            self._logger.warning("B站收藏夹读取失败：未取到自己的 UID")
            return []
        try:
            payload = self._fetch("GET", _FAV_FOLDER_LIST_URL, params={"up_mid": up_mid})
        except BilibiliError as exc:
            self._log_read_error("收藏夹读取", exc)
            return []
        data = payload.get("data")
        folders = data.get("list") if isinstance(data, dict) else None
        return [item for item in folders or [] if isinstance(item, dict)]

    def favorite_video(self, identifier: str, folder_id: int) -> bool:
        """把视频收藏到指定收藏夹：folder_id 来自 get_favorite_folders。"""
        if not self._require_login("视频收藏"):
            return False
        folder_id = _to_int(folder_id)
        if folder_id <= 0:
            self._logger.warning("B站视频收藏失败：缺少有效的收藏夹ID")
            return False
        aid = self._resolve_video_aid(identifier)
        if not aid:
            self._logger.warning(f"B站视频收藏失败：无法解析视频号 {identifier!r}")
            return False
        form: dict[str, Any] = {
            "rid": aid,
            "type": 2,
            "add_media_ids": folder_id,
            "del_media_ids": "",
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _FAV_RESOURCE_DEAL_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("视频收藏", exc)
            return False
        self._logger.info(f"B站视频收藏成功: aid={aid} folder={folder_id}")
        return True

    # ── 直播 ──

    def get_live_room_info(self, room_id: int) -> dict[str, Any]:
        """直播间信息（getInfoByRoom 的 data：room_info/anchor_info 等）；失败返回空 dict。"""
        room_id = _to_int(room_id)
        if room_id <= 0:
            return {}
        try:
            payload = self._fetch(
                "GET", _LIVE_ROOM_INFO_URL, params={"room_id": room_id}
            )
        except BilibiliError as exc:
            self._log_read_error("直播间信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_live_playurl(self, room_id: int) -> dict[str, Any]:
        """直播拉流地址：优先 http_stream/flv/avc，其次 http_hls/fmp4/avc。

        返回 {ok, room_id, url, format, expires, error}；取不到返回空 dict。
        expires 是地址剩余有效秒数；FLV CDN 需要 UA/Referer/Origin（ffmpeg 拉流时带上）。
        """
        room_id = _to_int(room_id)
        if room_id <= 0:
            return {}
        real_room_id = self._resolve_live_room_id(room_id)
        if real_room_id <= 0:
            return {}
        params = {
            "room_id": real_room_id,
            "protocol": "0,1",
            "format": "0,1,2",
            "codec": "0,1",
            "qn": 150,
            "platform": "web",
            "ptype": 8,
        }
        try:
            payload = self._fetch(
                "GET",
                _LIVE_PLAY_INFO_URL,
                params=params,
                headers={
                    "Referer": f"https://live.bilibili.com/{real_room_id}",
                    "Origin": "https://live.bilibili.com",
                },
            )
        except BilibiliError as exc:
            self._log_read_error("直播拉流地址读取", exc)
            return {}
        data = payload.get("data")
        playurl_info = data.get("playurl_info") if isinstance(data, dict) else None
        playurl = (
            playurl_info.get("playurl") if isinstance(playurl_info, dict) else None
        )
        streams = playurl.get("stream") if isinstance(playurl, dict) else None
        for protocol, format_name, codec_name in (
            ("http_stream", "flv", "avc"),
            ("http_hls", "fmp4", "avc"),
        ):
            for stream in streams or []:
                if not isinstance(stream, dict) or stream.get("protocol_name") != protocol:
                    continue
                for fmt in stream.get("format") or []:
                    if not isinstance(fmt, dict) or fmt.get("format_name") != format_name:
                        continue
                    for codec in fmt.get("codec") or []:
                        if not isinstance(codec, dict) or codec.get("codec_name") != codec_name:
                            continue
                        url, expires = _live_stream_url(codec)
                        if not url:
                            continue
                        return {
                            "ok": True,
                            "room_id": _to_int(data.get("room_id")) or real_room_id,
                            "url": url,
                            "format": format_name,
                            "expires": expires,
                            "error": "",
                        }
        return {}

    def get_live_danmu_info(self, room_id: int) -> dict[str, Any]:
        """弹幕服务器信息（getDanmuInfo 的 data：token/host_list）；失败返回空 dict。"""
        real_room_id = self._resolve_live_room_id(room_id)
        if real_room_id <= 0:
            return {}
        try:
            # getDanmuInfo 2026 起要求 wbi 签名；未签名会返回 -352（实测）。
            params = self._sign_wbi({"id": real_room_id, "type": 0})
            payload = self._fetch(
                "GET",
                _LIVE_DANMU_INFO_URL,
                params=params,
                headers={"Referer": f"https://live.bilibili.com/{real_room_id}"},
            )
        except BilibiliError as exc:
            self._log_read_error("直播弹幕服务器信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def send_danmaku(
        self, room_id: int, text: str, *, reply_mid: int = 0, reply_uname: str = ""
    ) -> bool:
        """发送直播弹幕；reply_mid/reply_uname 非空时 @ 目标观众。"""
        room_id = _to_int(room_id)
        message = (text or "").strip()
        if room_id <= 0 or not message:
            self._logger.warning("B站直播弹幕参数不完整（room_id/text 不能为空）")
            return False
        if len(message) > MAX_LIVE_DANMAKU_CHARS:
            self._logger.warning(
                f"B站直播弹幕超过 {MAX_LIVE_DANMAKU_CHARS} 字，已拦截发送"
            )
            return False
        if not self._sessdata or not self._bili_jct:
            self._logger.warning("B站直播弹幕发送失败：未登录")
            return False
        real_room_id = self._resolve_live_room_id(room_id)
        form: dict[str, Any] = {
            "roomid": real_room_id,
            "msg": message,
            "color": 16777215,
            "mode": 1,
            "fontsize": 25,
            "rnd": int(time.time()),
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
            "reply_mid": _to_int(reply_mid),
            "reply_uname": str(reply_uname or ""),
            "reply_attr": 0,
        }
        self._rate_limit_wait()
        try:
            self._fetch(
                "POST",
                _LIVE_SEND_DANMAKU_URL,
                data=form,
                headers={
                    "Referer": f"https://live.bilibili.com/{real_room_id}",
                    "Origin": "https://live.bilibili.com",
                },
            )
        except BilibiliError as exc:
            self._on_write_error("直播弹幕发送", exc)
            return False
        self._logger.info(f"B站直播弹幕已发送: room={real_room_id}")
        return True

    def follow_user(self, uid: int, *, follow: bool = True) -> bool:
        """关注/取消关注一个 B站用户；失败返回 False（不抛）。"""
        if not self._require_login("关注用户"):
            return False
        target = _to_int(uid)
        if target <= 0 or target == self.my_uid:
            self._logger.warning(f"B站关注用户失败：无效 UID {uid!r}")
            return False
        form: dict[str, Any] = {
            "fid": target,
            "act": 1 if follow else 2,
            "re_src": 11,
            "csrf": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch("POST", _RELATION_MODIFY_URL, data=form)
        except BilibiliError as exc:
            self._on_write_error("关注用户", exc)
            return False
        self._logger.info(f"B站{'关注用户' if follow else '取消关注'}成功: uid={target}")
        return True

    # ── 用户空间 ──

    def get_space_info(self, mid: int) -> dict[str, Any]:
        """用户空间信息（space/wbi/acc/info 的 data）；失败返回空 dict。"""
        mid = _to_int(mid)
        if not mid:
            return {}
        params = self._sign_wbi({"mid": mid})
        try:
            payload = self._fetch(
                "GET",
                _SPACE_INFO_URL,
                params=params,
                headers={"Referer": f"https://space.bilibili.com/{mid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("用户空间信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_user_videos(
        self, mid: int, *, page: int = 1, page_size: int = 20
    ) -> list[dict[str, Any]]:
        """用户投稿视频（space/arc/search 的 vlist）；失败返回空列表。"""
        mid = _to_int(mid)
        if not mid:
            return []
        params = {
            "mid": mid,
            "ps": max(_to_int(page_size), 1),
            "pn": max(_to_int(page), 1),
            "order": "pubdate",
        }
        try:
            payload = self._fetch(
                "GET",
                _SPACE_VIDEOS_URL,
                params=params,
                headers={"Referer": f"https://space.bilibili.com/{mid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("用户投稿读取", exc)
            return []
        data = payload.get("data")
        listing = data.get("list") if isinstance(data, dict) else None
        vlist = listing.get("vlist") if isinstance(listing, dict) else None
        return [item for item in vlist or [] if isinstance(item, dict)]

    def get_player_info(self, bvid: str, cid: int) -> dict[str, Any]:
        """播放器信息（player/wbi/v2 的 data）；字幕在 data["subtitle"]["subtitles"]。"""
        bvid = (bvid or "").strip()
        cid = _to_int(cid)
        if not bvid or not cid:
            return {}
        params = self._sign_wbi({"bvid": bvid, "cid": cid})
        try:
            payload = self._fetch(
                "GET",
                _PLAYER_INFO_URL,
                params=params,
                headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("播放器信息读取", exc)
            return {}
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def get_playurl_audio(self, bvid: str, cid: int) -> str | None:
        """DASH 音频流地址：取 bandwidth 最大的一条；失败返回 None。"""
        bvid = (bvid or "").strip()
        cid = _to_int(cid)
        if not bvid or not cid:
            return None
        params = self._sign_wbi(
            {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
        )
        try:
            payload = self._fetch(
                "GET",
                _PLAYURL_URL,
                params=params,
                headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
            )
        except BilibiliError as exc:
            self._log_read_error("音频地址读取", exc)
            return None
        data = payload.get("data")
        dash = data.get("dash") if isinstance(data, dict) else None
        audios = dash.get("audio") if isinstance(dash, dict) else None
        best = max(
            (
                item
                for item in audios or []
                if isinstance(item, dict) and (item.get("base_url") or item.get("baseUrl"))
            ),
            key=lambda item: _to_int(item.get("bandwidth")),
            default=None,
        )
        if not best:
            return None
        return str(best.get("base_url") or best.get("baseUrl"))

    def fetch_text(self, url: str) -> str | None:
        """下载文本资源（字幕 JSON 等）；失败返回 None。"""
        if not url:
            return None
        response = self._request("GET", url)
        if response is None or response.status_code >= 400:
            self._logger.warning(f"B站文本下载失败: {url}")
            return None
        try:
            return response.text
        except (requests.RequestException, OSError, ValueError) as exc:
            self._logger.warning(f"B站文本下载失败: {url}（{exc}）")
            return None

    def fetch_bytes(self, url: str) -> bytes | None:
        """下载二进制资源（头像等）；失败返回 None。"""
        if not url:
            return None
        response = self._request("GET", url)
        if response is None or response.status_code >= 400:
            self._logger.warning(f"B站二进制下载失败: {url}")
            return None
        try:
            content = response.content
        except (requests.RequestException, OSError, ValueError) as exc:
            self._logger.warning(f"B站二进制下载失败: {url}（{exc}）")
            return None
        if not content:
            self._logger.warning(f"B站二进制下载失败: {url}（空响应）")
            return None
        return content

    def download_file(self, url: str, path: Path) -> bool:
        """把 url 流式下载到 path（先写 .part 再替换）；失败返回 False 并清理半成品。"""
        target = Path(path)
        # 先落 .part：下载中断时不会把已有文件截成半截，调用方也读不到不完整内容。
        partial = target.with_name(f"{target.name}.part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            response = self._http.get(url, stream=True, timeout=self._timeout)
            try:
                if response.status_code >= 400:
                    self._logger.warning(f"B站文件下载失败: HTTP {response.status_code} {url}")
                    return False
                with partial.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1 << 16):
                        if chunk:
                            handle.write(chunk)
            finally:
                response.close()
            if partial.stat().st_size <= 0:
                self._logger.warning(f"B站文件下载失败: {url}（空响应）")
                partial.unlink(missing_ok=True)
                return False
            partial.replace(target)
        except (requests.RequestException, OSError) as exc:
            self._logger.warning(f"B站文件下载失败: {url}（{exc}）")
            partial.unlink(missing_ok=True)
            return False
        return True

    # ── 私信 ──

    def get_sessions(self, count: int = 30) -> list[BilibiliSession]:
        """获取私信会话列表（按最后消息时间倒序）。"""
        params = {
            "session_type": 1,
            "group_fold": 1,
            "unfollow_fold": 0,
            "sort_rule": 2,
            "build": 0,
            "mobi_app": "web",
        }
        try:
            payload = self._fetch("GET", f"{VC_BASE}/session_svr/v1/session_svr/get_sessions", params=params)
        except BilibiliError as exc:
            self._log_read_error("私信会话读取", exc)
            return []
        data = payload.get("data")
        raw_sessions = data.get("session_list") if isinstance(data, dict) else None
        sessions = [
            BilibiliSession.from_api(item)
            for item in raw_sessions or []
            if isinstance(item, dict)
        ]
        sessions.sort(
            key=lambda item: item.last_msg.timestamp if item.last_msg else 0,
            reverse=True,
        )
        return sessions[: max(_to_int(count), 0)]

    def get_messages(self, talker_id: int, size: int = 5) -> list[BilibiliMessage]:
        """获取指定会话的最新消息。"""
        params = {
            "sender_device_id": 1,
            "talker_id": _to_int(talker_id),
            "session_type": 1,
            "size": _to_int(size),
            "build": 0,
            "mobi_app": "web",
        }
        try:
            payload = self._fetch("GET", f"{VC_BASE}/svr_sync/v1/svr_sync/fetch_session_msgs", params=params)
        except BilibiliError as exc:
            self._log_read_error("私信读取", exc)
            return []
        data = payload.get("data")
        raw_messages = data.get("messages") if isinstance(data, dict) else None
        return [
            BilibiliMessage.from_api(item, self._my_uid)
            for item in raw_messages or []
            if isinstance(item, dict)
        ]

    def get_new_messages(self, session: BilibiliSession) -> list[BilibiliMessage]:
        """获取会话里尚未见过、且不是自己发出的新消息。"""
        messages = self.get_messages(session.talker_id, size=3)
        new_messages: list[BilibiliMessage] = []
        for message in messages:
            if not message.msg_key or message.msg_key in self._seen_msg_keys:
                continue
            if self._my_uid and message.sender_uid == self._my_uid:
                continue
            if message.timestamp <= self._last_msg_times.get(session.talker_id, 0):
                continue
            self._seen_msg_keys.add(message.msg_key)
            new_messages.append(message)
        if new_messages:
            self._last_msg_times[session.talker_id] = max(item.timestamp for item in new_messages)
        return new_messages

    def send_message(self, receiver_id: int, text: str) -> bool:
        """发送文本私信。"""
        message = (text or "").strip()
        if not receiver_id or not message:
            self._logger.warning("B站私信参数不完整（receiver_id/text 不能为空）")
            return False
        sender_uid = self.my_uid
        if not sender_uid:
            self._logger.warning("B站私信发送失败：未取到自己的 UID")
            return False
        form: dict[str, Any] = {
            "msg[sender_uid]": sender_uid,
            "msg[receiver_id]": _to_int(receiver_id),
            "msg[receiver_type]": 1,
            "msg[msg_type]": 1,
            "msg[msg_status]": 0,
            "msg[content]": json.dumps({"content": message}, ensure_ascii=False),
            "msg[timestamp]": int(time.time()),
            "msg[new_face_version]": 0,
            "msg[dev_id]": DEFAULT_DEVICE_ID,
            "build": 0,
            "mobi_app": "web",
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch(
                "POST",
                f"{VC_BASE}/web_im/v1/web_im/send_msg",
                data=form,
                headers={"Referer": "https://message.bilibili.com/"},
            )
        except BilibiliError as exc:
            self._on_write_error("私信发送", exc)
            return False
        self._logger.info(f"B站私信已发送: receiver={receiver_id}")
        return True

    # ── 动态 ──

    def upload_dynamic_image(self, image_path: str | Path) -> dict[str, Any]:
        """上传一张动态配图，返回 upload_bfs 的 data（含 image_url/image_width/image_height）。"""
        path = Path(image_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise BilibiliApiError(-1, f"读取图片失败: {path}（{exc}）") from exc
        if not content:
            raise BilibiliApiError(-1, f"图片为空: {path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        self._rate_limit_wait()
        payload = self._fetch(
            "POST",
            _DYNAMIC_IMAGE_UPLOAD_URL,
            data={"category": "daily", "biz": "new_dyn", "csrf": self._bili_jct},
            files={"file_up": (path.name, content, mime_type)},
            headers={"Referer": "https://t.bilibili.com/"},
            # 上传图片重发最多多一份附件，不会产生重复评论/私信，5xx 可以重试。
            retry=True,
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("image_url"):
            raise BilibiliApiError(-1, "图片上传成功但未返回 image_url")
        return data

    def publish_dynamic(
        self, text: str, images: Sequence[str | Path] | None = None
    ) -> int:
        """发布一条文本/图文动态，返回 dynamic_id；失败抛 BilibiliApiError。"""
        content = (text or "").strip()
        image_paths = [Path(item) for item in images or ()]
        if not content and not image_paths:
            raise ValueError("动态内容不能为空")
        pics: list[dict[str, Any]] = []
        for path in image_paths:
            info = self.upload_dynamic_image(path)
            pics.append(
                {
                    "img_src": str(info["image_url"]),
                    "img_width": _to_int(info.get("image_width")),
                    "img_height": _to_int(info.get("image_height")),
                    "img_size": info.get("img_size") or 0,
                }
            )
        dyn_req: dict[str, Any] = {
            "content": {
                "contents": (
                    [{"biz_id": "", "type": 1, "raw_text": content}] if content else []
                )
            },
            "scene": 2 if pics else 1,
            "meta": {"app_meta": {"from": "create.dynamic.web", "mobi_app": "web"}},
            "attach_card": None,
        }
        if pics:
            dyn_req["pics"] = pics
        self._rate_limit_wait()
        payload = self._fetch(
            "POST",
            _DYNAMIC_CREATE_URL,
            params={"csrf": self._bili_jct},
            json_body={"dyn_req": dyn_req},
            headers={"Referer": "https://t.bilibili.com/"},
        )
        data = payload.get("data")
        dynamic_id = 0
        if isinstance(data, dict):
            for key in ("dyn_id", "dyn_id_str", "dynamic_id"):
                value = data.get(key)
                if value in (None, ""):
                    continue
                try:
                    dynamic_id = int(value)
                except (TypeError, ValueError):
                    continue
                if dynamic_id:
                    break
        if not dynamic_id:
            raise BilibiliApiError(-1, "发布动态成功但未返回 dynamic_id")
        self._logger.info(f"B站动态已发布: dynamic_id={dynamic_id}")
        return dynamic_id

    # ── 生命周期 ──

    def close(self) -> None:
        """关闭本客户端自建的 HTTP 会话（外部传入的 session 归调用方所有，不关）。"""
        if not self._owns_session:
            return
        self._session.close()
        session = getattr(self._local, "session", None)
        if session is not None and session is not self._session:
            session.close()

    # ── WBI 签名 ──

    def _ensure_wbi_keys(self) -> None:
        """确保有未过期的 WBI 密钥；取不到就保持无签名（请求仍能发，只是可能被 -352）。"""
        if (
            self._wbi_mixin_key
            and time.monotonic() - self._wbi_key_at < self._WBI_KEY_TTL_SECONDS
        ):
            return
        try:
            self.get_my_info()
        except BilibiliError as exc:
            self._log_read_error("WBI 密钥获取", exc)

    def _invalidate_wbi_keys(self) -> None:
        """签名被服务端判失效时清空缓存，下次请求重新取密钥。"""
        with self._lock:
            self._wbi_mixin_key = ""
            self._wbi_key_at = 0.0

    def _cache_wbi_keys(self, wbi_img: Mapping[str, Any]) -> None:
        img_raw = str(wbi_img.get("img_key") or wbi_img.get("img_url") or "")
        sub_raw = str(wbi_img.get("sub_key") or wbi_img.get("sub_url") or "")
        img_key = img_raw.rsplit("/", 1)[-1].split(".")[0]
        sub_key = sub_raw.rsplit("/", 1)[-1].split(".")[0]
        if len(img_key) < 32 or len(sub_key) < 32:
            self._logger.debug("B站 WBI 密钥提取失败，跳过签名")
            return
        combined = img_key + sub_key
        mixin_key = "".join(
            combined[index] for index in _WBI_MIXIN_KEY_ENC_TAB if index < len(combined)
        )[:32]
        with self._lock:
            self._wbi_mixin_key = mixin_key
            self._wbi_key_at = time.monotonic()

    def _sign_wbi(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """给查询参数加 wts + w_rid（拿不到密钥时原样返回）。"""
        self._ensure_wbi_keys()
        if not self._wbi_mixin_key:
            return dict(params)
        signed = {
            str(key): "".join(ch for ch in str(value) if ch not in _WBI_FILTERED_CHARS)
            for key, value in params.items()
        }
        signed["wts"] = str(int(time.time()))
        signed = dict(sorted(signed.items()))
        query = urlencode(signed)
        signed["w_rid"] = hashlib.md5(
            (query + self._wbi_mixin_key).encode()
        ).hexdigest()
        return signed

    # ── 内部：ID 解析 ──

    def _resolve_video_aid(self, identifier: str) -> int:
        """BV/av/URL -> aid；BV 需要查一次 view 接口，解析失败返回 0。"""
        bvid, aid = parse_video_id(identifier)
        if aid:
            return aid
        if not bvid:
            return 0
        return _to_int(self.get_video_info(bvid).get("aid"))

    def _resolve_comment_oid(self, identifier: str) -> int:
        """BV/av/URL -> aid；动态/专栏/opus 的数字 ID 直接当 oid。"""
        text = str(identifier or "").strip()
        bvid, aid = parse_video_id(text)
        if aid:
            return aid
        if bvid:
            return _to_int(self.get_video_info(bvid).get("aid"))
        return _to_int(text)

    def _resolve_live_room_id(self, room_id: int) -> int:
        """短号/房间号 -> 真实房间号；查不到时原样返回输入值。"""
        room_id = _to_int(room_id)
        if room_id <= 0:
            return 0
        room = self.get_live_room_info(room_id).get("room_info")
        real_room_id = _to_int(room.get("room_id")) if isinstance(room, dict) else 0
        return real_room_id or room_id

    # ── 内部：HTTP / 错误处理 ──

    @property
    def _http(self) -> requests.Session:
        """当前线程的 Session；没有就复制一份（requests.Session 不保证跨线程安全）。"""
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._clone_session()
            self._local.session = session
        return session

    def _clone_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self._session.headers)
        # 按 Cookie 对象复制，保留 domain/path，避免 cookie 被当成全局 cookie 发出去。
        for cookie in self._session.cookies:
            session.cookies.set_cookie(cookie)
        return session

    def _fetch(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Any = None,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool | None = None,
        retry: bool = False,
    ) -> dict[str, Any]:
        response = self._request(
            method,
            url,
            params=params,
            data=data,
            json_body=json_body,
            files=files,
            headers=headers,
            allow_redirects=allow_redirects,
            retry=retry,
        )
        if response is None:
            raise BilibiliApiError(-1, "B站网络请求失败")
        if response.status_code in _RISK_CONTROL_STATUS:
            self._on_risk_control(response.status_code)
            raise BilibiliApiError(-response.status_code, f"B站风控拦截（HTTP {response.status_code}）")
        try:
            return self._decode(response)
        except BilibiliApiError as exc:
            if exc.code != -352 or method.upper() != "GET" or "w_rid" not in (params or {}):
                raise
            # -352：B 站判定 WBI 签名失效。清空密钥、重取后重签一次再试。
            self._invalidate_wbi_keys()
            self._logger.warning("B站 WBI 签名失效（-352），重取密钥后重试一次")
            retried = self._request(
                method,
                url,
                params=self._sign_wbi(
                    {
                        key: value
                        for key, value in params.items()
                        if key not in ("wts", "w_rid")
                    }
                ),
                data=data,
                json_body=json_body,
                files=files,
                headers=headers,
            )
            if retried is None:
                raise BilibiliApiError(-1, "B站网络请求失败") from exc
            return self._decode(retried)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
        json_body: Any = None,
        files: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        allow_redirects: bool | None = None,
        retry: bool = False,
    ) -> requests.Response | None:
        """发一次请求；只有幂等的 GET/HEAD（或显式 retry 安全写）会重试。

        评论/私信/弹幕/投币等写请求重发会造成重复操作，一律只发一次。
        """
        options: dict[str, Any] = {
            "params": params,
            "data": data,
            "json": json_body,
            "files": files,
            "headers": headers,
            "timeout": self._timeout,
        }
        if allow_redirects is not None:
            options["allow_redirects"] = allow_redirects
        idempotent = retry or method.upper() in _IDEMPOTENT_METHODS
        attempts = self._MAX_RETRIES + 1 if idempotent else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._http.request(method, url, **options)
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code < 500:
                    return response
                last_error = BilibiliApiError(-1, f"B站服务异常 HTTP {response.status_code}")
            if attempt + 1 < attempts:
                time.sleep(self._RETRY_DELAY_SECONDS * (attempt + 1))
        self._logger.warning(f"B站请求失败: {method} {url}（{last_error}）")
        return None

    @staticmethod
    def _decode(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BilibiliApiError(-1, "B站响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise BilibiliApiError(-1, "B站响应不是 JSON 对象")
        try:
            code = int(payload.get("code") or 0)
        except (TypeError, ValueError) as exc:
            raise BilibiliApiError(-1, f"B站响应 code 不合法: {payload.get('code')!r}") from exc
        if code == 0:
            return payload
        message = str(payload.get("message") or payload.get("msg") or "")
        if code == -101:
            raise BilibiliAuthError(f"B站登录态失效: {message}")
        raise BilibiliApiError(code, message)

    def _require_login(self, action: str) -> bool:
        """需要登录态的操作前检查：缺 cookie 时直接失败，避免请求打到风控。"""
        if self._sessdata and self._bili_jct:
            return True
        self._logger.warning(f"B站{action}失败：未登录")
        return False

    def _rate_limit_wait(self) -> None:
        """在锁内预约下一个写操作时隙，锁外 sleep —— 并发写不会挤在同一个时隙。"""
        with self._lock:
            now = time.monotonic()
            if now - self._last_write_at > self._write_interval * 3:
                # 距上次写很久说明风控期已过，冷却逐步回落到默认间隔。
                self._write_interval = max(
                    self._DEFAULT_WRITE_INTERVAL_SECONDS, self._write_interval * 0.5
                )
            wait = self._last_write_at + self._write_interval - now
            self._last_write_at = max(now, self._last_write_at + self._write_interval)
        if wait > 0:
            time.sleep(wait)

    def _bump_write_cooldown(self) -> None:
        with self._lock:
            self._write_interval = min(
                self._write_interval * 1.5, self._MAX_WRITE_INTERVAL_SECONDS
            )

    def _on_risk_control(self, status_code: int) -> None:
        """HTTP 412/429 是风控拦截（不是业务错误），同样放大写冷却。"""
        self._bump_write_cooldown()
        self._logger.warning(
            f"B站请求命中风控（HTTP {status_code}），写操作冷却提升到 {self._write_interval:.1f}s"
        )

    def _on_write_error(self, action: str, error: Exception) -> None:
        if isinstance(error, BilibiliApiError) and error.code in _WRITE_RETRY_CODES:
            self._bump_write_cooldown()
            self._logger.warning(
                f"B站{action}命中风控/限流（{error.code}），写操作冷却提升到 {self._write_interval:.1f}s"
            )
            return
        if isinstance(error, BilibiliAuthError):
            self._logger.warning(f"B站{action}失败: {error}")
            return
        self._logger.warning(f"B站{action}失败: {error}")

    def _log_read_error(self, action: str, error: Exception) -> None:
        if isinstance(error, BilibiliAuthError):
            self._logger.warning(f"B站{action}失败: {error}")
        else:
            self._logger.debug(f"B站{action}失败: {error}")

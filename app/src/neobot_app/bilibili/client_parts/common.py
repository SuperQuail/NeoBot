"""B站 Web API 的常量、URL 与无状态小工具。"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs

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

"""B 站 HTTP 客户端：登录态校验、评论/私信读写、动态发布、视频点赞与直播弹幕。

所有方法都是同步实现（requests）。需要 async 的调用方用 asyncio.to_thread
包一层即可（BilibiliService 已经这样做）。

写操作（发评论/私信/动态）统一走 _rate_limit_wait() 限速；只有幂等的 GET/HEAD 在
网络错误与 HTTP 5xx 时退避重试 2 次（写请求不重试，避免重复发评论/私信/投币）；
B 站业务错误码不重试，-352（WBI 签名失效）重取密钥后再试一次。

实现在 neobot_app.bilibili.client_parts（常量、数据模型与七组 mixin），本模块只保留类定义与 re-export。
"""

from __future__ import annotations

import requests  # noqa: F401 - 单测按 client.requests 打桩（打的是模块对象本身）
import time  # noqa: F401 - 单测按 client.time.sleep / client.time.monotonic 打桩

from .client_parts.comments import _CommentMixin
from .client_parts.content import _ContentMixin
from .client_parts.dynamic import _DynamicMixin
from .client_parts.http import _ClientCoreMixin
from .client_parts.live import _LiveMixin
from .client_parts.messages import _MessageMixin
from .client_parts.wbi import _WbiMixin

from .client_parts.common import (
    API_BASE,
    VC_BASE,
    _NAV_URL,
    _REPLY_FEED_URL,
    _AT_FEED_URL,
    _COMMENT_MAIN_URL,
    _COMMENT_ADD_URL,
    _COMMENT_REPLIES_URL,
    _DYNAMIC_CREATE_URL,
    _DYNAMIC_IMAGE_UPLOAD_URL,
    _SEARCH_URL,
    _VIDEO_VIEW_URL,
    _SPACE_INFO_URL,
    _SPACE_VIDEOS_URL,
    _PLAYER_INFO_URL,
    _PLAYURL_URL,
    _VIDEO_LIKE_URL,
    _VIDEO_COIN_URL,
    _VIDEO_SHARE_URL,
    _FAV_FOLDER_LIST_URL,
    _FAV_RESOURCE_DEAL_URL,
    _RELATION_MODIFY_URL,
    MAX_LIVE_DANMAKU_CHARS,
    _COMMENT_ACTION_URL,
    LIVE_API_BASE,
    _LIVE_ROOM_INFO_URL,
    _LIVE_PLAY_INFO_URL,
    _LIVE_DANMU_INFO_URL,
    _LIVE_SEND_DANMAKU_URL,
    DEFAULT_USER_AGENT,
    DEFAULT_DEVICE_ID,
    _WBI_MIXIN_KEY_ENC_TAB,
    _WBI_FILTERED_CHARS,
    _WRITE_RETRY_CODES,
    _RISK_CONTROL_STATUS,
    _IDEMPOTENT_METHODS,
    _COMMENT_TYPES,
    _COMMENT_MODES,
    _BV_PATTERN,
    _AV_PATTERN,
    _to_int,
    _empty_comment_page,
    parse_video_id,
    _live_stream_url,
)

from .client_parts.models import (
    BilibiliMessage,
    BilibiliSession,
)


class BilibiliClient(
    _CommentMixin,
    _ContentMixin,
    _DynamicMixin,
    _LiveMixin,
    _MessageMixin,
    _WbiMixin,
    _ClientCoreMixin,
):
    """B 站 Web API 同步客户端。"""


__all__ = (
    "API_BASE",
    "BilibiliClient",
    "BilibiliMessage",
    "BilibiliSession",
    "DEFAULT_DEVICE_ID",
    "DEFAULT_USER_AGENT",
    "LIVE_API_BASE",
    "MAX_LIVE_DANMAKU_CHARS",
    "VC_BASE",
    "parse_video_id",
    # 拆分后这些私有常量/小工具仍按模块名对外，单测/调用方按名字取用。
    "_AT_FEED_URL",
    "_AV_PATTERN",
    "_BV_PATTERN",
    "_COMMENT_ACTION_URL",
    "_COMMENT_ADD_URL",
    "_COMMENT_MAIN_URL",
    "_COMMENT_MODES",
    "_COMMENT_REPLIES_URL",
    "_COMMENT_TYPES",
    "_DYNAMIC_CREATE_URL",
    "_DYNAMIC_IMAGE_UPLOAD_URL",
    "_FAV_FOLDER_LIST_URL",
    "_FAV_RESOURCE_DEAL_URL",
    "_IDEMPOTENT_METHODS",
    "_LIVE_DANMU_INFO_URL",
    "_LIVE_PLAY_INFO_URL",
    "_LIVE_ROOM_INFO_URL",
    "_LIVE_SEND_DANMAKU_URL",
    "_NAV_URL",
    "_PLAYER_INFO_URL",
    "_PLAYURL_URL",
    "_RELATION_MODIFY_URL",
    "_REPLY_FEED_URL",
    "_RISK_CONTROL_STATUS",
    "_SEARCH_URL",
    "_SPACE_INFO_URL",
    "_SPACE_VIDEOS_URL",
    "_VIDEO_COIN_URL",
    "_VIDEO_LIKE_URL",
    "_VIDEO_SHARE_URL",
    "_VIDEO_VIEW_URL",
    "_WBI_FILTERED_CHARS",
    "_WBI_MIXIN_KEY_ENC_TAB",
    "_WRITE_RETRY_CODES",
    "_empty_comment_page",
    "_live_stream_url",
    "_to_int",
)

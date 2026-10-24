"""B 站模块：二维码登录、HTTP 客户端、动态发布与生命周期服务。

分层：
- BilibiliQrLogin：passport 二维码登录（同步原子操作 + 异步轮询）；
- BilibiliClient：B 站 Web API 同步客户端（asyncio.to_thread 包装由服务层负责）；
- BilibiliService：async 门面，负责登录态/休眠状态与动态发布；
- BilibiliVideoService：视频理解（信息 + 站点字幕/ASR 转写 + 热门评论）；
- BilibiliLiveInteractor：独立的直播间弹幕监听与自动回复；
- BilibiliCookieStore：<DATA_DIR>/bilibili/cookies.json 的读写。
"""

from __future__ import annotations

from .client import BilibiliClient, BilibiliMessage, BilibiliSession
from .cookie_provider import BilibiliCookieStore
from .errors import BilibiliApiError, BilibiliAuthError, BilibiliError
from .live_interact import BilibiliLiveInteractor
from .media import BilibiliVideoService
from .qr_login import (
    QR_STATE_EXPIRED,
    QR_STATE_PENDING,
    QR_STATE_REJECTED,
    QR_STATE_SCANNED,
    QR_STATE_SUCCESS,
    BilibiliQrLogin,
    QrCodeLogin,
    QrPollResult,
    make_qr_png,
)
from .service import BilibiliService

__all__ = [
    "QR_STATE_EXPIRED",
    "QR_STATE_PENDING",
    "QR_STATE_REJECTED",
    "QR_STATE_SCANNED",
    "QR_STATE_SUCCESS",
    "BilibiliApiError",
    "BilibiliAuthError",
    "BilibiliClient",
    "BilibiliCookieStore",
    "BilibiliError",
    "BilibiliLiveInteractor",
    "BilibiliMessage",
    "BilibiliQrLogin",
    "BilibiliService",
    "BilibiliSession",
    "BilibiliVideoService",
    "QrCodeLogin",
    "QrPollResult",
    "make_qr_png",
]

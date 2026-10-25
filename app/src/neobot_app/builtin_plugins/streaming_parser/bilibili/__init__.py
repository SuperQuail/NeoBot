"""B 站直播协议层（纯 Python，仅依赖标准库；httpx 在传输实现里按需导入）。

来源与冻结策略（v1）：本包是 amagi 的 TypeScript 协议（packages/core 的
bilibili live 三条端点 + judge/headers/urls）逐字翻译后固定在 v1 的副本，
只服务「轮询开播状态 + 渲染卡片」这一件事，**不再跟进上游**。

迁移策略（写在这里，避免下一个人再问"为什么不用 WBI / 为什么有两套 HTTP 栈"）：
- 只需要 getRoomInfoOld / room_init / get_info / card 四个不签名接口，
  因此不实现 WBI 签名（原 wbi.py 与它的测试已删除；需要签名的接口一律
  走本体 `neobot_app.bilibili.client`）；
- 长期方向是把这四条请求合回本体 B 站客户端，插件只保留模型与卡片渲染；
  在那之前本包保持冻结，改动请只做 bug 修复，不要在这里加新协议能力。
"""

from __future__ import annotations

from .client import BilibiliLiveClient, HttpxTransport, RawResponse, Transport
from .errors import BilibiliAPIError, BilibiliError, BilibiliTransportError
from .headers import DEFAULT_UA, live_room_headers, sec_ch_ua
from .judge import (
    ANTIBOT_PAGE,
    COOKIE_EXPIRED,
    NOT_FOUND,
    PLATFORM_ERROR,
    RATE_LIMITED,
    RISK_CONTROL,
    Verdict,
    judge,
)
from .models import (
    LiveRoomInfo,
    LiveRoomInit,
    UserLiveStatus,
    normalize_live_time,
)
from .urls import (
    LIVE_API_BASE,
    LIVE_WEB_BASE,
    live_room_info_url,
    live_room_init_url,
    live_room_page_url,
    normalize_room_id,
    user_live_status_url,
)

__all__ = [
    "ANTIBOT_PAGE",
    "COOKIE_EXPIRED",
    "DEFAULT_UA",
    "LIVE_API_BASE",
    "LIVE_WEB_BASE",
    "NOT_FOUND",
    "PLATFORM_ERROR",
    "RATE_LIMITED",
    "RISK_CONTROL",
    "BilibiliAPIError",
    "BilibiliError",
    "BilibiliLiveClient",
    "BilibiliTransportError",
    "HttpxTransport",
    "LiveRoomInfo",
    "LiveRoomInit",
    "RawResponse",
    "Transport",
    "UserLiveStatus",
    "Verdict",
    "judge",
    "live_room_headers",
    "live_room_info_url",
    "live_room_init_url",
    "live_room_page_url",
    "normalize_live_time",
    "normalize_room_id",
    "sec_ch_ua",
    "user_live_status_url",
]

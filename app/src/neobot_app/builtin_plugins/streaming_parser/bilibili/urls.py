"""B 站直播接口 URL 构造。

对照参考：amagi `packages/core/src/platforms/bilibili/api.ts:205-218`
（URL 为纯字符串拼接；本模块保持一致，并额外做参数校验）。
"""

from __future__ import annotations

API_BASE = "https://api.bilibili.com"
LIVE_API_BASE = "https://api.live.bilibili.com"
LIVE_WEB_BASE = "https://live.bilibili.com"


def normalize_room_id(room_id: int | str) -> str:
    """把房间号归一化成字符串。

    参考项目在 zod 里要求 `room_id` 必须是字符串；本实现故意更宽容：
    数字也会被 `str()` 化，避免调用方因类型细节踩坑。
    """
    if isinstance(room_id, bool):
        raise TypeError("room_id 不能是 bool")
    if isinstance(room_id, int):
        value = str(room_id)
    elif isinstance(room_id, str):
        value = room_id.strip()
    else:
        raise TypeError("room_id 必须是 int 或 str")
    if not value:
        raise ValueError("room_id 不能为空")
    if not value.isdigit():
        raise ValueError("room_id 必须是纯数字房间号")
    if int(value) < 1:
        raise ValueError("room_id 必须大于 0")
    return value


def normalize_host_mid(host_mid: int | str) -> int:
    """归一化主播 uid（对应 amagi 的 `zod.coerce.number().int().min(1)`）。"""
    if isinstance(host_mid, bool):
        raise TypeError("host_mid 不能是 bool")
    if isinstance(host_mid, str):
        text = host_mid.strip()
        if not text or not text.isdigit():
            raise ValueError("host_mid 必须是正整数")
        host_mid = int(text)
    if not isinstance(host_mid, int):
        raise TypeError("host_mid 必须是 int 或 str")
    if host_mid < 1:
        raise ValueError("host_mid 必须大于 0")
    return host_mid


def user_live_status_url(host_mid: int | str) -> str:
    """GET `room/v1/Room/getRoomInfoOld?mid={host_mid}`（uid → 直播状态 / 房间号）。"""
    return f"{LIVE_API_BASE}/room/v1/Room/getRoomInfoOld?mid={normalize_host_mid(host_mid)}"


def live_room_info_url(room_id: int | str) -> str:
    """GET `room/v1/Room/get_info?room_id={room_id}`（直播间展示信息）。"""
    return f"{LIVE_API_BASE}/room/v1/Room/get_info?room_id={normalize_room_id(room_id)}"


def live_room_init_url(room_id: int | str) -> str:
    """GET `room/v1/Room/room_init?id={room_id}`（短号 ↔ 真实房间号互转）。"""
    return f"{LIVE_API_BASE}/room/v1/Room/room_init?id={normalize_room_id(room_id)}"


def live_room_page_url(room_id: int | str) -> str:
    """直播间网页地址，用作 `Referer` 的构造来源。"""
    return f"{LIVE_WEB_BASE}/{normalize_room_id(room_id)}"


def user_card_url(host_mid: int | str) -> str:
    """GET api.bilibili.com/x/web-interface/card?mid={mid}&photo=true

    用途：取主播昵称与头像（卡片渲染必需）。对照 amagi api.ts:202；
    该端点不签名，与直播三接口同属「无 WBI」集合。
    """
    return f"{API_BASE}/x/web-interface/card?mid={normalize_host_mid(host_mid)}&photo=true"


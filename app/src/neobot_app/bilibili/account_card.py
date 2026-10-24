"""B 站账号卡片：/B站账号 把当前登录账号渲染成自包含 HTML 卡片。

数据只来自两处，都不碰凭证：
- `BilibiliService.status()`：登录态 / 昵称 / 头像 URL（零额外请求）；
- `BilibiliReadApi.user_card_detail()`：粉丝 / 关注 / 获赞 / 投稿等公开统计。

只读接口与头像下载失败都只降级对应块（统计显示「—」、头像回退首字色块），
卡片照常发送；截图不可用时由 `send_card` 降级为等价纯文本。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html as html_module
from typing import Any

from neobot_app.commands.card import AVATAR_MARKER, _FALLBACK_COLORS, send_card

from .read_api import BilibiliReadApi

LOGIN_HINT = "B站未登录，发送 /login bilibili 扫码登录。"
#: 统计读取失败时统计位显示这个占位符（卡片与文本一致）
STATS_PLACEHOLDER = "—"
STATS_UNAVAILABLE_NOTE = "统计暂不可用"

#: 头像字节 → MIME（只认图片魔数，不信任 URL 后缀）
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def _image_mime(data: bytes) -> str:
    for signature, mime in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


async def _avatar_data_uri(service: Any, url: str) -> str | None:
    """下载头像并转 data URI；下载失败/格式不识别都返回 None（绝不外抛）。"""
    client = getattr(service, "client", None)
    fetch = getattr(client, "fetch_bytes", None)
    if not url or not callable(fetch):
        return None
    try:
        data = await asyncio.to_thread(fetch, url)
    except Exception:
        return None
    if not data:
        return None
    mime = _image_mime(bytes(data))
    if not mime:
        return None
    return f"data:{mime};base64,{base64.b64encode(bytes(data)).decode('ascii')}"


def _stats_value(detail: dict[str, Any], key: str, stats_ok: bool) -> str:
    return str(_to_int(detail.get(key))) if stats_ok else STATS_PLACEHOLDER


def _login_state(snapshot: dict[str, Any]) -> str:
    if not snapshot.get("available"):
        return "未登录"
    return "有效" if snapshot.get("valid") else "待校验"


def _avatar_fragment(snapshot: dict[str, Any]) -> str:
    """头像**可信片段**：data URI 图片，取不到回落昵称首字色块。"""
    uri = _text(snapshot.get("avatar_data_uri"))
    if uri:
        return (
            '<img class="cmd-avatar cmd-avatar--target" '
            f'src="{html_module.escape(uri, quote=True)}" alt="B站头像">'
        )
    initial = _text(snapshot.get("uname"))[:1] or "?"
    seed = _text(snapshot.get("uid")) or initial
    color = _FALLBACK_COLORS[int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(_FALLBACK_COLORS)]
    return (
        f'<div class="cmd-avatar cmd-avatar-fallback" style="background:{color}">'
        f"{html_module.escape(initial)}</div>"
    )


async def build_account_snapshot(service: Any, *, read_api: Any = None) -> dict[str, Any]:
    """收集卡片数据；未登录只回状态，统计/头像失败只降级对应字段。"""
    status = service.status()
    snapshot: dict[str, Any] = {
        "available": bool(service.available),
        "uid": _to_int(status.get("uid")),
        "uname": _text(status.get("uname")),
        "face_url": "",
        "avatar_data_uri": None,
        "login_at": status.get("login_at"),
        "valid": bool(status.get("valid")),
        "detail": {},
        "stats_ok": False,
    }
    if not snapshot["available"]:
        return snapshot
    detail: dict[str, Any] = {}
    if snapshot["uid"] > 0:
        try:
            api = read_api if read_api is not None else BilibiliReadApi(service.client)
            result = await asyncio.to_thread(api.user_card_detail, snapshot["uid"])
        except Exception:
            result = {}
        if isinstance(result, dict) and result.get("ok"):
            detail = result
    snapshot["detail"] = detail
    snapshot["stats_ok"] = bool(detail)
    snapshot["face_url"] = _https(_text(detail.get("face")) or _text(status.get("face")))
    snapshot["avatar_data_uri"] = await _avatar_data_uri(service, snapshot["face_url"])
    return snapshot


def account_card_blocks(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """卡片块：头像行 / 三列统计 / 账号信息 / 空间链接。"""
    detail = snapshot.get("detail") or {}
    stats_ok = bool(snapshot.get("stats_ok"))
    blocks: list[dict[str, Any]] = [
        # note 块先放占位符，渲染后替换为头像可信片段（见 commands/card.py）
        {"kind": "note", "text": AVATAR_MARKER},
        {
            "kind": "stats",
            "cols": 3,
            "items": [
                ("粉丝", _stats_value(detail, "fans", stats_ok)),
                ("关注", _stats_value(detail, "following", stats_ok)),
                ("获赞", _stats_value(detail, "likes", stats_ok)),
            ],
        },
        {
            "kind": "kv",
            "items": [
                ("UID", str(snapshot.get("uid") or STATS_PLACEHOLDER)),
                ("登录状态", _login_state(snapshot)),
                ("登录时间", _text(snapshot.get("login_at")) or STATS_PLACEHOLDER),
                ("投稿", _stats_value(detail, "videos", stats_ok)),
            ],
        },
    ]
    if not stats_ok:
        blocks.append({"kind": "note", "text": STATS_UNAVAILABLE_NOTE})
    if snapshot.get("uid"):
        blocks.append(
            {"kind": "note", "text": f"空间 https://space.bilibili.com/{snapshot['uid']}"}
        )
    return blocks


def account_card_text(snapshot: dict[str, Any]) -> str:
    """与卡片信息等价的多行纯文本（渲染不可用时的降级，同样不含凭证）。"""
    if not snapshot.get("available"):
        return LOGIN_HINT
    detail = snapshot.get("detail") or {}
    stats_ok = bool(snapshot.get("stats_ok"))
    lines = [
        f"B站账号 @{_text(snapshot.get('uname')) or STATS_PLACEHOLDER}",
        f"UID: {snapshot.get('uid') or STATS_PLACEHOLDER}",
        f"登录状态: {_login_state(snapshot)}",
        f"登录时间: {_text(snapshot.get('login_at')) or STATS_PLACEHOLDER}",
        f"粉丝: {_stats_value(detail, 'fans', stats_ok)} · "
        f"关注: {_stats_value(detail, 'following', stats_ok)} · "
        f"获赞: {_stats_value(detail, 'likes', stats_ok)}",
        f"投稿: {_stats_value(detail, 'videos', stats_ok)}",
    ]
    if not stats_ok:
        lines.append(STATS_UNAVAILABLE_NOTE)
    if snapshot.get("uid"):
        lines.append(f"空间: https://space.bilibili.com/{snapshot['uid']}")
    return "\n".join(lines)


async def send_account_card(ctx: Any, service: Any) -> str | None:
    """未登录回提示文本；已登录出卡片（失败时由 send_card 降级为纯文本）。"""
    snapshot = await build_account_snapshot(service)
    if not snapshot["available"]:
        return LOGIN_HINT
    uname = _text(snapshot.get("uname"))
    return await send_card(
        ctx,
        title="B站账号",
        subtitle=f"@{uname}" if uname else "已登录",
        blocks=account_card_blocks(snapshot),
        avatars=_avatar_fragment(snapshot),
        fallback_text=account_card_text(snapshot),
        filename="bilibili-account.png",
    )


def register_account_command(registry: Any, runtime: Any) -> None:
    """注册 /B站账号（所有人可见；只展示公开资料与统计）。"""
    from neobot_app.commands.model import PERM_EVERYONE, Command

    async def _handle(ctx: Any) -> str | None:
        return await send_account_card(ctx, runtime.service)

    registry.register(
        Command(
            name="B站账号",
            aliases=("biliaccount", "bili_account"),
            permission=PERM_EVERYONE,
            description="查看当前登录的B站账号（头像/昵称/UID/粉丝/关注）",
            usage="",
            handler=_handle,
        )
    )


__all__ = [
    "LOGIN_HINT",
    "STATS_UNAVAILABLE_NOTE",
    "account_card_blocks",
    "account_card_text",
    "build_account_snapshot",
    "register_account_command",
    "send_account_card",
]

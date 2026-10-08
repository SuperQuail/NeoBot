"""命令结果卡片：payload → 自包含 HTML → PNG → 纯文本降级。

命令面此前只有 `/help` 与 `/status` 出图，两者的渲染逻辑各自长在自己的模块里、不可复用，
其余命令一律回多行纯文本。这里把「渲染可用就出图、不可用就回等价文本」收敛成一个入口：

    return await send_card(
        ctx,
        title="次级管理员已添加",
        blocks=[{"kind": "kv", "items": [("当前次级管理员", "3 人")]}],
        fallback_text="已添加次级管理员（当前 3 人）。",
    )

三级口径（与 `/status` 一致；`render_card_image` 与 `send_image_bytes` 都**绝不外抛**）：

1. 自包含 HTML 卡片 → PNG（截图端口取 `CommandService.screenshots`）；
2. `send_image_bytes` 落盘后经适配器发送；
3. 任一级失败 → 返回 `fallback_text`，由命令服务按普通文本发送
   （handler 返回 `None` 表示「已自行发送」，命令服务不再补发）。

**硬规则**：`fallback_text` 与 payload 一样**不得出现任何 QQ 号** —— 渲染不可用时用户
看到的文本同样不能泄露身份（issue #85）。
"""

from __future__ import annotations

import asyncio
import hashlib
import html as html_module
from typing import Any, Sequence

from neobot_app.runtime.html_card import (
    inject_marker,
    render_card_html,
    render_card_image,
)

#: 单张卡片的截图超时（秒），与 /help、/status 同档
SCREENSHOT_TIMEOUT_SECONDS = 20.0
#: 命令内兜底超时（秒，在截图超时之上）
COMMAND_TIMEOUT_SECONDS = 25.0
#: 降级提示：让用户知道这条本该是图
FALLBACK_HINT = "（图片渲染不可用，本条为纯文本）"

#: 头像行占位符（写在 note 块的文本里，渲染完成后替换为可信片段）
AVATAR_MARKER = "@@CMD_AVATARS@@"

#: 首字母色块调色板（取不到头像时的回落；与主题无关的固定色）
FALLBACK_COLORS: tuple[str, ...] = (
    "#4493f8",
    "#e2714b",
    "#2ea043",
    "#a371f7",
    "#d29922",
    "#db61a2",
    "#1f9ea8",
    "#8b6f47",
)

#: 头像行样式（自包含，无外链）
AVATAR_CSS = """\
.cmd-avatars { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 0; }
.cmd-avatar {
  width: 56px; height: 56px; border-radius: 50%; flex: 0 0 auto;
  border: 1px solid var(--card-border); object-fit: cover;
}
.cmd-avatar--target { border: 2px solid var(--card-accent, #4493f8); }
.cmd-avatar-fallback {
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; font-weight: 700; color: #ffffff;
}
.cmd-avatar-more {
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700; color: var(--card-muted, #8b949e);
}
"""


def build_html(
    *,
    title: str,
    subtitle: str = "",
    blocks: Any = (),
    footer: str = "",
    theme: str = "default",
    width: int = 720,
) -> str:
    """渲染自包含 HTML 卡片（与 /help、/status 同一个渲染器）。"""
    return render_card_html(
        title=str(title or ""),
        subtitle=str(subtitle or ""),
        blocks=list(blocks or ()),
        footer=str(footer or ""),
        theme=theme,
        width=int(width or 720),
    )


def avatar_fragment(
    store: Any,
    user_ids: Sequence[Any],
    *,
    highlight: Any = None,
    max_shown: int = 12,
) -> str:
    """头像行**可信片段**：每个 QQ 一个圆形头像，取不到回落首字母色块。

    片段里**只有图片和色块，没有任何号码文本** —— 即使头像缺失也不泄露身份
    （issue #85）。调用方负责把它注入卡片：`inject_marker(html, AVATAR_MARKER, 片段)`。
    """
    items: list[str] = []
    shown = list(user_ids)[: max(1, int(max_shown or 1))]
    for raw in shown:
        user_id = str(raw or "").strip()
        uri = _avatar_uri(store, user_id)
        css = "cmd-avatar" + (" cmd-avatar--target" if highlight is not None and user_id == str(highlight) else "")
        if uri:
            items.append(
                f'<img class="{css}" src="{html_module.escape(uri, quote=True)}" alt="管理员头像">'
            )
            continue
        color = _fallback_color(user_id)
        items.append(
            f'<div class="{css} cmd-avatar-fallback" style="background:{color}">管</div>'
        )
    hidden = len(list(user_ids)) - len(shown)
    if hidden > 0:
        items.append(f'<div class="cmd-avatar cmd-avatar-fallback cmd-avatar-more" '
                     f'style="background:transparent">+{hidden}</div>')
    return f'<div class="cmd-avatars">{"".join(items)}</div>'


def _avatar_uri(store: Any, user_id: str) -> str:
    """头像 data URI；store 缺失 / 未就绪 / 异常都返回空串（绝不联网、绝不外抛）。"""
    if not user_id or store is None:
        return ""
    getter = getattr(store, "get_data_uri", None)
    if not callable(getter):
        return ""
    try:
        value = getter(user_id)
    except Exception:
        return ""
    return str(value or "")


def _fallback_color(seed: str) -> str:
    digest = hashlib.sha256(str(seed or "?").encode("utf-8")).hexdigest()
    return FALLBACK_COLORS[int(digest, 16) % len(FALLBACK_COLORS)]


def finalize(html: str, *, avatars: str = "") -> str:
    """把可信头像片段注入卡片（没有头像片段时原样返回）。"""
    if not avatars:
        return html
    with_style = html.replace("</style>", AVATAR_CSS + "\n</style>", 1)
    return inject_marker(with_style, AVATAR_MARKER, avatars)


async def send_card(
    ctx: Any,
    *,
    title: str,
    subtitle: str = "",
    blocks: Any = (),
    footer: str = "",
    fallback_text: str,
    avatars: str = "",
    theme: str = "default",
    width: int = 720,
    filename: str | None = None,
) -> str | None:
    """出图成功返回 `None`（已自行发送）；否则返回**不含 QQ 号**的等价纯文本。"""
    service = getattr(ctx, "service", None)
    if service is None:
        return fallback_text
    try:
        html = finalize(
            build_html(
                title=title,
                subtitle=subtitle,
                blocks=blocks,
                footer=footer,
                theme=theme,
                width=width,
            ),
            avatars=avatars,
        )
        png = await asyncio.wait_for(
            render_card_image(
                html,
                timeout=SCREENSHOT_TIMEOUT_SECONDS,
                screenshots=getattr(service, "screenshots", None),
            ),
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, TimeoutError):
        png = None
    except Exception:
        png = None
    if png:
        try:
            sent = await service.send_image_bytes(
                getattr(ctx, "kind", "") or "",
                getattr(ctx, "conv_id", "") or "",
                png,
                at_user_id=getattr(ctx, "user_id", None),
                filename=filename,
            )
        except Exception:
            sent = False
        if sent:
            return None
    return fallback_text


def with_hint(text: str) -> str:
    """给降级文本补一句「本条本该是图」。"""
    body = str(text or "").rstrip()
    if not body:
        return FALLBACK_HINT
    return f"{body}\n{FALLBACK_HINT}"


__all__ = [
    "AVATAR_CSS",
    "AVATAR_MARKER",
    "COMMAND_TIMEOUT_SECONDS",
    "FALLBACK_COLORS",
    "FALLBACK_HINT",
    "SCREENSHOT_TIMEOUT_SECONDS",
    "avatar_fragment",
    "build_html",
    "finalize",
    "send_card",
    "with_hint",
]

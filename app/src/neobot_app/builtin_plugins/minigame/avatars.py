"""漂流瓶卡片的头像取用（spec(5) §4.5 / R33）。

**一律走本体 AvatarStore**（宿主服务 avatar_store），插件**不自行联网**：

- 优先 get_data_uri(user_id) 拿 data:image/png;base64,... 内联进卡片；
- 取不到（未就绪 / 失败 / 被清理）时回落**首字母色块**，仍然出图；
- 发瓶时用 get_path(user_id) 把本地头像路径记进 mg_bottle.sender_avatar 留档。

头像与 Markdown 正文都是**可信片段注入**：本模块先用 render_card_html 渲染整张
卡片，再把「由本模块生成、不含任何用户输入」的片段替换进渲染器提供的插槽（slot）
与标记（marker，见 runtime/html_card.py 的 inject_slot / inject_marker）。用户可控
文本永远先经 html.escape + Markdown 渲染 + URL 白名单清洗，不会带进标签或属性。
"""

from __future__ import annotations

import html as html_module
import hashlib
from typing import Any

#: 头像片段的占位符（note 块文本；渲染后被替换成可信片段）
AVATAR_MARKER = "@@MG_AVATAR@@"

#: 首字母色块调色板（与主题无关的固定色）
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

#: 头像片段的内联样式（自包含，无外链）
AVATAR_CSS = """\
.mg-avatar-row { display: flex; align-items: center; gap: 12px; margin: 0; }
.mg-avatar {
  width: 64px; height: 64px; border-radius: 50%; flex: 0 0 auto;
  border: 1px solid var(--card-border); object-fit: cover;
}
.mg-avatar-fallback {
  display: flex; align-items: center; justify-content: center;
  font-size: 26px; font-weight: 700; color: #ffffff;
}
"""


def safe_user_key(user_id: Any) -> str:
    return str(user_id or "").strip()


class AvatarProvider:
    """本体 AvatarStore 的只读包装（带可用性兜底）。"""

    def __init__(self, ctx: Any, *, cache_days: int = 7) -> None:
        self._ctx = ctx
        self._cache_days = int(cache_days or 0)
        self._store = self._resolve_store(ctx)

    @staticmethod
    def _resolve_store(ctx: Any) -> Any:
        host = getattr(ctx, "plugin_host", None)
        services = getattr(host, "services", None)
        getter = getattr(services, "get", None)
        if not callable(getter):
            return None
        try:
            return getter("avatar_store", None)
        except Exception:
            return None

    @property
    def store(self) -> Any:
        return self._store

    @property
    def available(self) -> bool:
        return self._store is not None

    @property
    def refresh_days(self) -> int:
        return self._cache_days

    def data_uri(self, user_id: Any) -> str | None:
        """头像 data URI；未就绪返回 None（绝不抛异常、绝不联网）。"""
        store = self._store
        if store is None:
            return None
        getter = getattr(store, "get_data_uri", None)
        if not callable(getter):
            return None
        try:
            value = getter(safe_user_key(user_id))
        except Exception:
            return None
        return str(value) if value else None

    def path(self, user_id: Any) -> str:
        """本地头像路径（仅用于 mg_bottle.sender_avatar 留档）；未就绪返回空串。"""
        store = self._store
        if store is None:
            return ""
        getter = getattr(store, "get_path", None)
        if not callable(getter):
            return ""
        try:
            value = getter(safe_user_key(user_id))
        except Exception:
            return ""
        return str(value) if value else ""

    async def refresh(self, user_id: Any) -> bool:
        """触发本体惰性刷新（尽力而为；永不抛异常）。"""
        store = self._store
        if store is None:
            return False
        refresher = getattr(store, "maybe_refresh", None)
        if not callable(refresher):
            return False
        try:
            return bool(await refresher(safe_user_key(user_id)))
        except Exception:
            return False

    def html(self, user_id: Any, name: str, *, anonymous: bool = False) -> str:
        """可信头像片段：data URI 图 或 首字母色块。"""
        uri = self.data_uri(user_id)
        if uri:
            return (
                '<div class="mg-avatar-row">'
                f'<img class="mg-avatar" src="{html_module.escape(uri, quote=True)}" alt="头像">'
                "</div>"
            )
        # 匿名瓶的色块用 QQ 号而非昵称取首字母：不泄露真实昵称的任何字符
        source = safe_user_key(user_id) if anonymous else str(name or "")
        initial = (source.strip() or "?")[0]
        seed = safe_user_key(user_id) or str(name or "?")
        color = FALLBACK_COLORS[
            int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(FALLBACK_COLORS)
        ]
        return (
            '<div class="mg-avatar-row">'
            f'<div class="mg-avatar mg-avatar-fallback" style="background:{color}">'
            f"{html_module.escape(initial)}</div>"
            "</div>"
        )


def with_style(card_html: str, css: str) -> str:
    """把一段内联 CSS 追加进卡片的 style 块（自包含）。"""
    if not css:
        return card_html
    if "</style>" not in card_html:
        return card_html
    return card_html.replace("</style>", css + "\n</style>", 1)


__all__ = [
    "AVATAR_CSS",
    "AVATAR_MARKER",
    "AvatarProvider",
    "FALLBACK_COLORS",
    "safe_user_key",
    "with_style",
]

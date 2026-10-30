"""卡片渲染：把数据填进 templates 里的 HTML，再交给宿主的截图端口出图。

三条实测得到的硬约束（决定了本模块的写法）：
1. 截图端口用 CDP setDocumentContent 写进 about:blank，file:// 与相对路径资源都不生效，
   所以 CSS 必须内联、图片必须用 data URI；
2. 内嵌字体时 wait_for_fonts=True 可能抛 FontLoadError，必须降级重试；
3. 浏览器被空闲回收后首张渲染约 3s，命令里要给足超时，渲染失败要能退回纯文本。
"""

from __future__ import annotations

import html
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

STYLE_ORDER: tuple[str, ...] = ("sakura", "neon", "minimal")
RANDOM_STYLE = "random"
OPEN_TAG = "{{"
CLOSE_TAG = "}}"


def style_names() -> tuple[str, ...]:
    return STYLE_ORDER


def resolve_style(name: str | None) -> str:
    """把 random / 空值 / 非法值归一成一个可用风格。"""
    value = (name or "").strip().lower()
    if not value or value == RANDOM_STYLE or value not in STYLE_ORDER:
        return random.choice(STYLE_ORDER)
    return value


def format_online(online: int) -> str:
    """人气文案：12345 -> 1.2万人气。"""
    value = max(0, int(online or 0))
    if value >= 10000:
        return f"{value / 10000:.1f}万人气"
    return f"{value}人气"


def format_live_time(value: datetime | None, *, now: datetime | None = None) -> str:
    """开播时间文案：今天 20:30 开播 / 昨天 20:30 开播 / 09-26 20:30 开播。"""
    if value is None:
        return ""
    moment = now or datetime.now(value.tzinfo)
    if value.date() == moment.date():
        return f"今天 {value:%H:%M} 开播"
    if value.date() == (moment - timedelta(days=1)).date():
        return f"昨天 {value:%H:%M} 开播"
    return f"{value:%m-%d %H:%M} 开播"


def format_room_id(room_id: int) -> str:
    """房间号文案。模板按整串显示，不再自己加前缀。"""
    return "房间 " + str(int(room_id))


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _fill(
    template: str, values: dict[str, Any], *, raw_keys: tuple[str, ...] = ()
) -> str:
    """替换 {{key}}；raw_keys 里的键原样插入（它们必须是渲染端自己生成的 HTML）。"""
    out: list[str] = []
    index = 0
    while True:
        start = template.find(OPEN_TAG, index)
        if start < 0:
            out.append(template[index:])
            break
        end = template.find(CLOSE_TAG, start + len(OPEN_TAG))
        if end < 0:
            out.append(template[index:])
            break
        out.append(template[index:start])
        key = template[start + len(OPEN_TAG) : end].strip()
        if key in raw_keys:
            out.append(str(values.get(key, "")))
        else:
            out.append(_escape(values.get(key, "")))
        index = end + len(CLOSE_TAG)
    return "".join(out)


def host_fragment(*, avatar_src: str, name: str, live: bool) -> str:
    """总览图里单个主播的片段（结构是 templates 里样式的契约）。"""
    classes = "host host-live" if live else "host"
    if avatar_src:
        avatar = f'<img src="{_escape(avatar_src)}" alt="">'
    else:
        avatar = '<span class="host-placeholder"></span>'
    badge = '<span class="host-badge">LIVE</span>' if live else ""
    return (
        f'<div class="{classes}">'
        f'<span class="host-avatar">{avatar}{badge}</span>'
        f'<span class="host-name">{_escape(name)}</span>'
        "</div>"
    )


class CardRenderer:
    """模板 + 截图端口；渲染失败一律返回 None，由调用方降级。"""

    def __init__(
        self,
        template_dir: Path,
        *,
        screenshots_provider: Any = None,
        selector: str = ".card",
        timeout: float = 30.0,
        scale: float = 2.0,
    ) -> None:
        self.template_dir = Path(template_dir)
        # 软重启会重建浏览器与截图端口，所以这里存的是「取端口的函数」而不是端口本身
        self._provider = screenshots_provider
        self.selector = selector
        self.timeout = float(timeout)
        self.scale = float(scale)

    def _screenshots(self) -> Any:
        provider = self._provider
        if provider is None:
            return None
        try:
            return provider() if callable(provider) else provider
        except Exception:
            return None

    def _template(self, name: str) -> str | None:
        try:
            return (self.template_dir / name).read_text(encoding="utf-8")
        except OSError:
            return None

    def _font_faces(self) -> tuple[Any, ...]:
        """templates/fonts 下的字体文件，交给截图端口按 data URI 内联。"""
        fonts_dir = self.template_dir / "fonts"
        if not fonts_dir.is_dir():
            return ()
        try:
            from neobot_modloader import FontFace
        except Exception:
            return ()
        formats = {
            ".woff2": "woff2",
            ".woff": "woff",
            ".ttf": "truetype",
            ".otf": "opentype",
        }
        faces: list[Any] = []
        for path in sorted(fonts_dir.iterdir()):
            fmt = formats.get(path.suffix.lower())
            if fmt is None:
                continue
            faces.append(FontFace(family="FusionPixel", source=path, format=fmt))
        return tuple(faces)

    def _render_options(self, *, wait_fonts: bool) -> Any:
        from neobot_modloader import RenderOptions, ScreenshotOptions

        return RenderOptions(
            screenshot=ScreenshotOptions(
                mode="element",
                selector=self.selector,
                format="png",
                scale=self.scale,
            ),
            fonts=self._font_faces(),
            timeout=self.timeout,
            # 内嵌中日韩 woff2 时等字体校验会抛 FontLoadError，字形其实仍然生效，
            # 所以先试「等」，失败再试「不等」。
            wait_for_fonts=wait_fonts,
            wait_for_images=True,
        )

    async def _render_html(self, html_text: str) -> bytes | None:
        for wait_fonts in (True, False):
            port = self._screenshots()
            if port is None:
                return None
            try:
                options = self._render_options(wait_fonts=wait_fonts)
                result = await port.render(html=html_text, options=options)
            except Exception:
                # 渲染失败不能让调用方崩：失败一律返回 None，由调用方降级成纯文本
                if wait_fonts:
                    continue
                return None
            data = getattr(result, "data", None)
            if data:
                return bytes(data)
            return None
        return None

    def card_html(self, values: dict[str, Any], *, style: str) -> str | None:
        """通知与面板预览共用同一模板，所有外部文字仍统一转义。"""
        template = self._template(f"card_{style}.html")
        if template is None:
            return None
        payload = dict(values)
        payload["font_style"] = ""
        return _fill(template, payload, raw_keys=("font_style",))

    async def render_card(self, values: dict[str, Any], *, style: str) -> bytes | None:
        """渲染开播/下播卡片；style 必须是具体风格名。"""
        html_text = self.card_html(values, style=style)
        return await self._render_html(html_text) if html_text is not None else None

    async def render_overview(
        self,
        hosts: list[dict[str, Any]],
        *,
        style: str,
        title_text: str,
        summary_text: str,
    ) -> bytes | None:
        """渲染开播状态总览图；hosts 每项：avatar_src / name / live。"""
        template = self._template(f"overview_{style}.html")
        if template is None:
            return None
        grid = "".join(
            host_fragment(
                avatar_src=str(item.get("avatar_src") or ""),
                name=str(item.get("name") or ""),
                live=bool(item.get("live")),
            )
            for item in hosts
        )
        values = {
            "grid": grid,
            "title_text": title_text,
            "summary_text": summary_text,
            "font_style": "",
        }
        html_text = _fill(template, values, raw_keys=("grid", "font_style"))
        return await self._render_html(html_text)

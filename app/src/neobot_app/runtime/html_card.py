"""公共 HTML 卡片渲染器（多主题）—— spec(5) §4.3 约定的通用接口。

/help、/status 与后续游戏卡片共用同一份实现：
- render_card_html 生成**自包含** HTML：内联 CSS、无 JS、无外链、无外部资源；
- render_card_image 走既有的 ScreenshotService（与 markdown→图片共享
  同一个 operation_lock）；不可用或失败一律返回 None，**不抛异常**，
  由调用方降级（spec(4) R28）。

主题表只放 CSS 变量块：新增主题 = 加一个变量块，不需要改渲染器。
未知主题回落 default 并记 warning。
"""

from __future__ import annotations

import html as html_module
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from neobot_app.utils.logger import get_module_logger
from neobot_contracts.ports.screenshot import (
    RenderOptions,
    ScreenshotOptions,
    ScreenshotPort,
)

logger = get_module_logger("runtime.html_card")

#: 默认卡片宽度（px）
DEFAULT_WIDTH = 720

#: 主题 id -> CSS 变量块（--card-* / --accent / --radius）
THEMES: dict[str, dict[str, str]] = {
    # 极简深色：/help、/status、排行榜
    "default": {
        "--card-bg": "#12151c",
        "--card-fg": "#e6edf3",
        "--card-muted": "#8b949e",
        "--accent": "#4493f8",
        "--radius": "14px",
        "--card-border": "#232a35",
        "--card-font": (
            'system-ui, -apple-system, "Segoe UI", "Microsoft YaHei", '
            '"PingFang SC", "Hiragino Sans GB", sans-serif'
        ),
    },
    # 海蓝渐变 + 圆角 + 衬线正文：漂流瓶
    "bottle": {
        "--card-bg": "linear-gradient(160deg, #0b2a4a 0%, #124a72 55%, #1d6a9c 100%)",
        "--card-fg": "#eaf4ff",
        "--card-muted": "#9dc3e0",
        "--accent": "#63c8ff",
        "--radius": "22px",
        "--card-border": "rgba(157, 195, 224, 0.35)",
        "--card-font": 'Georgia, "Songti SC", "SimSun", "Noto Serif SC", serif',
    },
    # 高饱和 + 粗边框 + 等宽数字：小游戏
    "game": {
        "--card-bg": "#1b1035",
        "--card-fg": "#fdf6ff",
        "--card-muted": "#c0a8e8",
        "--accent": "#ffd447",
        "--radius": "6px",
        "--card-border": "#7a4dff",
        "--card-font": (
            'ui-monospace, "Cascadia Mono", Consolas, "Microsoft YaHei", monospace'
        ),
    },
    # 抽签 / 今日运势
    "fortune": {
        "--card-bg": "linear-gradient(150deg, #fff7e6 0%, #ffe6c7 60%, #ffd7a8 100%)",
        "--card-fg": "#4a2b12",
        "--card-muted": "#8a6135",
        "--accent": "#c8382b",
        "--radius": "16px",
        "--card-border": "#e8c69a",
        "--card-font": '"Kaiti SC", "KaiTi", Georgia, "Songti SC", serif',
    },
}

#: 主题 id 的对外顺序（面板 / 文档使用）
THEME_NAMES: tuple[str, ...] = tuple(THEMES)

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title_text}</title>
<style>
{variables}
{common}
</style>
</head>
<body>
<main class="card" style="width: {width}px;">
  <header class="card-head">
    <h1>{title}</h1>
    {subtitle}
  </header>
  <section class="card-body">
{body}
  </section>
  {footer}
</main>
</body>
</html>
"""

_COMMON_CSS = """* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: var(--card-bg);
  color: var(--card-fg);
  font-family: var(--card-font);
}
.card {
  padding: 26px 28px 22px;
  border: 1px solid var(--card-border);
  border-radius: var(--radius);
  background: var(--card-bg);
  color: var(--card-fg);
  font-family: var(--card-font);
  font-size: 15px;
  line-height: 1.55;
}
.card-head { border-bottom: 1px solid var(--card-border); padding-bottom: 12px; margin-bottom: 16px; }
.card-head h1 { margin: 0; font-size: 22px; line-height: 1.3; }
.card-head .subtitle { margin-top: 6px; color: var(--card-muted); font-size: 13px; }
.card-body { display: block; }
.card-footer { margin-top: 18px; padding-top: 10px; border-top: 1px solid var(--card-border); color: var(--card-muted); font-size: 12px; }
.block { margin-bottom: 18px; }
.block:last-child { margin-bottom: 0; }
.block-heading { font-size: 16px; font-weight: 700; color: var(--accent); margin: 0 0 8px; }
.kv { width: 100%; border-collapse: collapse; }
.kv th, .kv td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--card-border); vertical-align: top; }
.kv th { width: 42%; font-weight: 500; color: var(--card-muted); }
.kv td { font-variant-numeric: tabular-nums; }
.rows { width: 100%; border-collapse: collapse; }
.rows th, .rows td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--card-border); }
.rows th { color: var(--card-muted); font-weight: 600; }
.note { padding: 10px 12px; border-left: 3px solid var(--accent); background: rgba(127,127,127,0.12); border-radius: 6px; color: var(--card-fg); }
.empty { color: var(--card-muted); }
"""


def resolve_theme(theme: str | None) -> str:
    """解析主题 id：未知主题回落 default 并记 warning。"""
    name = str(theme or "default").strip().lower() or "default"
    if name not in THEMES:
        logger.warning(f"未知卡片主题，已回落 default: {name!r}")
        return "default"
    return name


def theme_variables(theme: str | None) -> str:
    """主题的 CSS 变量块（可直接内联进 :root）。"""
    variables = THEMES[resolve_theme(theme)]
    body = "\n".join(f"  {key}: {value};" for key, value in variables.items())
    return f":root {{\n{body}\n}}"


def _escape(value: Any) -> str:
    return html_module.escape(str(value if value is not None else ""), quote=True)


def _render_block(block: Any) -> str:
    """渲染单个块：heading / rows / kv / note。"""
    if not isinstance(block, Mapping):
        return ""
    kind = str(block.get("kind") or "").strip().lower()
    if kind == "heading":
        return (
            '<div class="block">'
            f'<h2 class="block-heading">{_escape(block.get("text"))}</h2>'
            "</div>"
        )
    if kind == "note":
        return (
            '<div class="block">'
            f'<div class="note">{_escape(block.get("text"))}</div>'
            "</div>"
        )
    if kind == "kv":
        rows: list[str] = []
        for item in block.get("items") or ():
            if isinstance(item, Mapping):
                label = item.get("label", item.get("key", ""))
                value = item.get("value", "")
            elif isinstance(item, Sequence) and len(item) >= 2:
                label, value = item[0], item[1]
            else:
                continue
            rows.append(f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>")
        if not rows:
            rows.append('<tr><td class="empty" colspan="2">暂无数据</td></tr>')
        title = block.get("title")
        heading = f'<h3 class="block-heading">{_escape(title)}</h3>' if title else ""
        return (
            '<div class="block">'
            f"{heading}"
            f'<table class="kv">{"".join(rows)}</table>'
            "</div>"
        )
    if kind == "rows":
        columns = [str(column) for column in (block.get("columns") or ())]
        head = (
            "<tr>" + "".join(f"<th>{_escape(column)}</th>" for column in columns) + "</tr>"
            if columns
            else ""
        )
        body_rows: list[str] = []
        for row in block.get("rows") or ():
            cells = list(row.values()) if isinstance(row, Mapping) else row
            body_rows.append(
                "<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in cells) + "</tr>"
            )
        if not body_rows:
            span = max(1, len(columns))
            body_rows.append(f'<tr><td class="empty" colspan="{span}">暂无数据</td></tr>')
        title = block.get("title")
        heading = f'<h3 class="block-heading">{_escape(title)}</h3>' if title else ""
        return (
            '<div class="block">'
            f"{heading}"
            f'<table class="rows">{head}{"".join(body_rows)}</table>'
            "</div>"
        )
    return ""


def render_card_html(
    *,
    title: str,
    subtitle: str = "",
    blocks: Iterable[Any] = (),
    footer: str = "",
    theme: str = "default",
    width: int = DEFAULT_WIDTH,
) -> str:
    """生成自包含 HTML 卡片（内联 CSS、无 JS、无外链）。

    DSL 示例::

        render_card_html(
            title="运行状态",
            subtitle="NeoBot v1.0.0",
            blocks=[
                {"kind": "heading", "text": "概况"},
                {"kind": "kv", "items": [("在线状态", "在线"), ("延迟", "42 ms")]},
                {"kind": "rows", "columns": ["名称", "版本"], "rows": [["a", "1.0.0"]]},
                {"kind": "note", "text": "纯文本降级时信息等价"},
            ],
            footer="第 1 页",
            theme="default",
            width=720,
        )
    """
    safe_width = max(240, int(width or DEFAULT_WIDTH))
    theme_id = resolve_theme(theme)
    body = "\n".join(part for part in (_render_block(block) for block in blocks) if part)
    subtitle_html = f'<div class="subtitle">{_escape(subtitle)}</div>' if subtitle else ""
    footer_html = f'<footer class="card-footer">{_escape(footer)}</footer>' if footer else ""
    return _TEMPLATE.format(
        title_text=_escape(title),
        title=_escape(title),
        subtitle=subtitle_html,
        footer=footer_html,
        body=body or '<div class="block empty">暂无数据</div>',
        variables=theme_variables(theme_id),
        common=_COMMON_CSS,
        width=safe_width,
    )


#: 模块级默认截图端口（组合根可用 set_screenshots 注入）。
_screenshots: ScreenshotPort | None = None


def set_screenshots(port: ScreenshotPort | None) -> None:
    """注入默认截图端口（None 表示不可用，渲染一律返回 None）。"""
    global _screenshots
    _screenshots = port


def get_screenshots() -> ScreenshotPort | None:
    return _screenshots


async def render_card_image(
    html: str,
    *,
    timeout: float = 20.0,
    screenshots: ScreenshotPort | None = None,
) -> bytes | None:
    """把自包含 HTML 渲染为 PNG 字节；不可用 / 失败 / 超时一律返回 None。

    ScreenshotService.render 内部已持有共享 operation_lock，因此本函数与
    markdown→图片天然串行，不会产生 Chromium 并发。
    """
    port = screenshots if screenshots is not None else _screenshots
    if port is None:
        logger.warning("截图端口不可用，卡片渲染降级为纯文本")
        return None
    try:
        result = await port.render(
            html=html,
            options=RenderOptions(
                screenshot=ScreenshotOptions(mode="full_page", format="png"),
                wait_for_fonts=False,
                wait_for_images=False,
                timeout=float(timeout),
            ),
        )
    except Exception as exc:  # noqa: BLE001 - 任何失败都降级，绝不外抛
        logger.warning(f"卡片渲染失败，已降级: {exc}")
        return None
    data = getattr(result, "data", None)
    if not data:
        logger.warning("卡片渲染未返回图片数据，已降级")
        return None
    return bytes(data)


__all__ = [
    "DEFAULT_WIDTH",
    "THEMES",
    "THEME_NAMES",
    "get_screenshots",
    "render_card_html",
    "render_card_image",
    "resolve_theme",
    "set_screenshots",
    "theme_variables",
]

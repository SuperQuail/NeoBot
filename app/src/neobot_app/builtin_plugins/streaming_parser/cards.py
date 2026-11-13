"""命令回复卡片。

这里刻意复用宿主 /help 的那套卡片渲染（neobot_app.runtime.html_card 的 blocks DSL +
同一个 default 主题），这样插件命令的回复与 /help 长得一样，不用各写一套美术。

渲染失败（没装浏览器、html_card 不可用等）时自动退化成信息等价的纯文本。
"""

from __future__ import annotations

from typing import Any

#: 与 /help 一致的主题
CARD_THEME = "default"
CARD_WIDTH = 720
CARD_TIMEOUT = 20.0
CARD_FILENAME = "streaming_parser_card.png"


def kv_card(
    *,
    title: str,
    items: list[tuple[str, str]],
    subtitle: str = "",
    note: str = "",
    footer: str = "",
) -> dict[str, Any]:
    """键值卡片：适合「已开始监听」「设置已更新」这类结果。"""
    blocks: list[dict[str, Any]] = [
        {"kind": "kv", "items": [(str(k), str(v)) for k, v in items]}
    ]
    if note:
        blocks.append({"kind": "note", "text": note})
    return {"title": title, "subtitle": subtitle, "blocks": blocks, "footer": footer}


def rows_card(
    *,
    title: str,
    columns: list[str],
    rows: list[list[Any]],
    subtitle: str = "",
    note: str = "",
    footer: str = "",
) -> dict[str, Any]:
    """表格卡片：适合「直播监听列表」。"""
    blocks: list[dict[str, Any]] = [
        {"kind": "rows", "columns": [str(c) for c in columns], "rows": rows},
    ]
    if note:
        blocks.append({"kind": "note", "text": note})
    return {"title": title, "subtitle": subtitle, "blocks": blocks, "footer": footer}


def message_card(
    *,
    title: str,
    lines: list[str],
    subtitle: str = "",
    note: str = "",
    footer: str = "",
) -> dict[str, Any]:
    """说明卡片：适合「用法」「当前设置」这类多行文本。"""
    blocks: list[dict[str, Any]] = []
    for line in lines:
        if str(line).strip():
            blocks.append({"kind": "note", "text": str(line)})
    if note:
        blocks.append({"kind": "note", "text": note, "tone": "accent"})
    return {"title": title, "subtitle": subtitle, "blocks": blocks, "footer": footer}


def error_card(*, title: str, text: str, hint: str = "") -> dict[str, Any]:
    """失败卡片：红色语气，一眼看出没成功。"""
    blocks: list[dict[str, Any]] = [{"kind": "note", "text": text, "tone": "danger"}]
    if hint:
        blocks.append({"kind": "note", "text": hint, "tone": "muted"})
    return {"title": title, "subtitle": "", "blocks": blocks, "footer": ""}


def payload_text(payload: dict[str, Any]) -> str:
    """卡片 -> 等价纯文本（渲染不可用时的降级，也是 /help 的既有做法）。"""
    lines: list[str] = [str(payload.get("title") or "")]
    subtitle = str(payload.get("subtitle") or "")
    if subtitle:
        lines.append(subtitle)
    for block in payload.get("blocks") or ():
        if not isinstance(block, dict):
            continue
        kind = block.get("kind")
        if kind == "kv":
            lines.extend(str(k) + ": " + str(v) for k, v in block.get("items") or ())
        elif kind == "rows":
            columns = block.get("columns") or ()
            if columns:
                lines.append(" ".join(str(c) for c in columns))
            for row in block.get("rows") or ():
                lines.append(" | ".join(str(cell) for cell in row))
        elif kind in ("note", "heading"):
            lines.append(str(block.get("text") or ""))
        elif kind == "pager":
            page = block.get("page")
            pages = block.get("pages")
            lines.append("第 " + str(page) + " / " + str(pages) + " 页")
    footer = str(payload.get("footer") or "")
    if footer:
        lines.append(footer)
    return "\n".join(line for line in lines if line.strip())


async def render_payload_png(
    payload: dict[str, Any],
    *,
    screenshots: Any,
    theme: str = CARD_THEME,
    timeout: float = CARD_TIMEOUT,
) -> bytes | None:
    """渲染成 PNG；任何失败都返回 None（绝不抛给命令链路）。"""
    if screenshots is None:
        return None
    try:
        from neobot_app.runtime.html_card import render_card_html, render_card_image
    except Exception:
        return None
    try:
        html = render_card_html(
            title=str(payload.get("title") or ""),
            subtitle=str(payload.get("subtitle") or ""),
            blocks=payload.get("blocks") or (),
            footer=str(payload.get("footer") or ""),
            theme=theme,
            width=CARD_WIDTH,
        )
    except Exception:
        return None
    return await render_card_image(html, timeout=timeout, screenshots=screenshots)


async def send_card(
    command_ctx: Any,
    payload: dict[str, Any],
    *,
    screenshots: Any,
    theme: str = CARD_THEME,
) -> bool:
    """先试图发卡片，失败就把卡片内容降级成纯文本发出去。"""
    png = await render_payload_png(payload, screenshots=screenshots, theme=theme)
    if png:
        try:
            ok = await command_ctx.service.send_image_bytes(
                command_ctx.kind,
                command_ctx.conv_id,
                png,
                at_user_id=None,
                filename=CARD_FILENAME,
            )
        except Exception:
            ok = False
        if ok:
            return True
    await command_ctx.reply_plain(payload_text(payload))
    return False


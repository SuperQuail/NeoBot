"""块渲染：所有文本一律 escape 后进文本节点。"""

from __future__ import annotations

import html as html_module
from collections.abc import Mapping, Sequence
from typing import Any

from neobot_app.utils.logger import get_module_logger

from .base import _MARKER_NAME, _SLOT_NAME, _TONES, _VARIANT_NAME, _WIDTH_VALUE

logger = get_module_logger("runtime.html_card")

# ----------------------------------------------------------------------
# 块渲染（所有文本一律 escape 后进文本节点）
# ----------------------------------------------------------------------


def _escape(value: Any) -> str:
    return html_module.escape(str(value if value is not None else ""), quote=True)


def _tone(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if name in _TONES else ""


def _variant(value: Any) -> str:
    name = str(value or "").strip().lower()
    return name if _VARIANT_NAME.fullmatch(name) else ""


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _escape_cell(cell: Any) -> str:
    """单元格：标量 escape 后直出；映射可带 tone / mono / chip；序列按多行堆叠。"""
    if isinstance(cell, Mapping):
        tone = _tone(cell.get("tone"))
        classes = ["cell"]
        if tone:
            classes.append(f"cell--{tone}")
        if cell.get("mono"):
            classes.append("cell--mono")
        if cell.get("chip"):
            classes.append("cell--chip")
        text = cell.get("text", cell.get("value", ""))
        return f'<span class="{" ".join(classes)}">{_escape(text)}</span>'
    if isinstance(cell, Sequence) and not isinstance(cell, (str, bytes)):
        lines = "".join(f'<span class="cell-line">{_escape(item)}</span>' for item in cell)
        return lines or '<span class="cell-line"></span>'
    return _escape(cell)


def _row_cells(row: Any) -> list[Any]:
    if isinstance(row, Mapping):
        return list(row.values())
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
        return list(row)
    return []


def _width_values(value: Any) -> list[str]:
    """列宽（colgroup）：只接受 NN% / NNpx 形式，非法值忽略。"""
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    widths: list[str] = []
    for item in value:
        text = str(item).strip()
        widths.append(text if _WIDTH_VALUE.fullmatch(text) else "")
    return widths


def _colgroup(widths: Sequence[str]) -> str:
    if not widths or not any(widths):
        return ""
    cols = "".join(f'<col style="width: {width}">' if width else "<col>" for width in widths)
    return f"<colgroup>{cols}</colgroup>"


def _subheading(block: Mapping[str, Any]) -> str:
    title = block.get("title")
    return f'<h3 class="block-subheading">{_escape(title)}</h3>' if title else ""


def _kv_rows(items: Any) -> str:
    rows: list[str] = []
    for item in items or ():
        if isinstance(item, Mapping):
            label = item.get("label", item.get("key", ""))
            value = item.get("value", "")
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
            label, value = item[0], item[1]
        else:
            continue
        rows.append(f"<tr><th>{_escape(label)}</th><td>{_escape_cell(value)}</td></tr>")
    if not rows:
        rows.append('<tr><td class="empty" colspan="2">暂无数据</td></tr>')
    return "".join(rows)


def _rows_table(block: Mapping[str, Any]) -> str:
    columns = [str(column) for column in (block.get("columns") or ())]
    widths = _width_values(block.get("widths"))
    head = (
        "<thead><tr>"
        + "".join(f"<th>{_escape(column)}</th>" for column in columns)
        + "</tr></thead>"
        if columns
        else ""
    )
    body_rows: list[str] = []
    for row in block.get("rows") or ():
        cells = _row_cells(row)
        if not cells:
            continue
        body_rows.append(
            "<tr>" + "".join(f"<td>{_escape_cell(cell)}</td>" for cell in cells) + "</tr>"
        )
    if not body_rows:
        span = max(1, len(columns))
        body_rows.append(f'<tr><td class="empty" colspan="{span}">暂无数据</td></tr>')
    return f"{_colgroup(widths)}{head}<tbody>{''.join(body_rows)}</tbody>"


def _stats_grid(items: Any) -> str:
    tiles: list[str] = []
    for item in items or ():
        if isinstance(item, Mapping):
            label = item.get("label", item.get("key", ""))
            value = item.get("value", "")
            tone = _tone(item.get("tone"))
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)) and len(item) >= 2:
            label, value = item[0], item[1]
            tone = _tone(item[2]) if len(item) >= 3 else ""
        else:
            continue
        classes = "stat" + (f" stat--{tone}" if tone else "")
        tiles.append(
            f'<div class="{classes}">'
            f'<span class="stat-label">{_escape(label)}</span>'
            f'<span class="stat-value">{_escape_cell(value)}</span>'
            "</div>"
        )
    return f'<div class="stats">{"".join(tiles)}</div>' if tiles else ""


def _pager_strip(block: Mapping[str, Any]) -> str:
    pages = max(1, _safe_int(block.get("pages"), 1))
    page = min(max(_safe_int(block.get("page"), 1), 1), pages)
    dots = ""
    if 1 < pages <= 10:
        dots = "".join(
            f'<i class="pager-dot{" is-current" if index == page else ""}"></i>'
            for index in range(1, pages + 1)
        )
    hint = block.get("hint")
    hint_html = f'<span class="pager-sep">·</span><span>{_escape(hint)}</span>' if hint else ""
    return (
        '<div class="card-pager">'
        f'<span class="pager-page">第 {page}/{pages} 页</span>'
        f"{hint_html}"
        f'<span class="pager-dots">{dots}</span>'
        "</div>"
    )


def _render_blocks(blocks: Any) -> str:
    return "\n".join(
        part for part in (_render_block(block) for block in (blocks or ())) if part
    )


def _render_block(block: Any) -> str:
    """渲染单个块：heading / kv / rows / stats / grid / note / pager / slot / marker。"""
    if not isinstance(block, Mapping):
        return ""
    kind = str(block.get("kind") or "").strip().lower()
    tone = _tone(block.get("tone"))
    variant = _variant(block.get("variant"))
    base = f"block--{kind or 'empty'}"
    classes = ["block", base]
    if tone:
        classes.append(f"tone-{tone}")
    if variant:
        classes.append(f"variant-{variant}")
    inner = ""

    if kind == "heading":
        inner = f'<h2 class="block-heading">{_escape(block.get("text"))}</h2>'
    elif kind == "note":
        inner = f'<div class="note">{_escape(block.get("text"))}</div>'
    elif kind == "kv":
        items = block.get("items")
        if items is None:
            items = block.get("rows")
        inner = f'{_subheading(block)}<table class="kv">{_kv_rows(items)}</table>'
    elif kind in ("rows", "table"):
        table_classes = "rows" + (f" rows--{variant}" if variant else "")
        classes[1] = "block--rows"
        inner = f'{_subheading(block)}<table class="{table_classes}">{_rows_table(block)}</table>'
    elif kind == "stats":
        cols = min(max(_safe_int(block.get("cols"), 3), 1), 4)
        inner = (
            f'{_subheading(block)}'
            f'<div class="stats-wrap" style="--stat-cols: {cols}">'
            f'{_stats_grid(block.get("items"))}</div>'
        )
    elif kind == "grid":
        cols = min(max(_safe_int(block.get("cols"), 2), 1), 4)
        cells = "".join(
            f'<div class="grid-cell">{_render_blocks(cell)}</div>'
            for cell in (block.get("cells") or ())
        )
        inner = f'<div class="grid" style="--grid-cols: {cols}">{cells}</div>'
    elif kind == "pager":
        inner = _pager_strip(block)
    elif kind == "slot":
        name = str(block.get("name") or "").strip().lower()
        if not _SLOT_NAME.fullmatch(name):
            logger.warning(f"非法插槽名，已忽略: {block.get('name')!r}")
            return ""
        return (
            f'<div class="block block--slot card-slot" data-slot="{name}">'
            f"<!--slot:{name}--></div>"
        )
    elif kind == "marker":
        text = str(block.get("text") or "").strip()
        if not _MARKER_NAME.fullmatch(text):
            logger.warning(f"非法标记名，已忽略: {block.get('text')!r}")
            return ""
        return f'<div class="block block--marker card-marker" data-marker="{text}">{text}</div>'
    else:
        return ""
    return f'<div class="{" ".join(classes)}">{inner}</div>'



"""/help 卡片的内容构建：列表分页 / 详情 / 三级降级用的 markdown 与纯文本。

只做内容与 HTML 结构，不碰缓存与截图（见 runtime/help_cache.py）。

安全边界（spec(5) R7 / A12）：卡片只允许出现命令自身的元数据
（命令名 / 描述 / 权限 / 用法 / 别名 / 参数 / 来源），不得包含配置值、
token 或任何用户标识 —— 因此本模块的输入只有 Command 对象与页码。
"""

from __future__ import annotations

from typing import Any

from neobot_app.commands.model import permission_name
from neobot_app.runtime.html_card import render_card_html

#: 列表卡片每页最多条数（spec(5) R5）
PAGE_SIZE = 30

#: 卡片标题
LIST_TITLE = "可用命令"
DETAIL_TITLE_PREFIX = "命令"

#: 空态文案（无可见命令时）
EMPTY_TEXT = "当前没有你可用的命令（可能是权限不足或插件未加载）。"

#: 降级到纯文本时附在末尾的提示
FALLBACK_HINT = "图片渲染不可用，已回退为文字版。"

#: 渲染 markdown 反引号（避免在源码里直接写 markdown 定界符）
_BT = chr(96)


def parse_help_args(args: Any) -> tuple[str | None, int | None]:
    """解析 /help 参数：能 int() 成功的视为页码（多个数字取最后一个），其余视为命令名。

    /help 给出 (None, None)；/help 2 给出 (None, 2)；
    /help ping 给出 ("ping", None)；/help ping 2 给出 ("ping", 2)。
    """
    target: str | None = None
    page: int | None = None
    for raw in args or ():
        token = str(raw or "").strip()
        if not token:
            continue
        try:
            page = int(token)
            continue
        except (TypeError, ValueError):
            pass
        if target is None:
            target = token.lstrip("/")
    return target, page


def total_pages(count: int, size: int = PAGE_SIZE) -> int:
    """总页数（至少 1 页，空列表也算 1 页）。"""
    step = max(1, int(size or PAGE_SIZE))
    return max(1, -(-max(0, int(count)) // step))


def clamp_page(page: int | None, pages: int) -> int:
    """把页码夹到 [1, pages]；None 视为第 1 页。"""
    if page is None:
        return 1
    return min(max(int(page), 1), max(1, int(pages)))


def paginate(items: Any, page: int, size: int = PAGE_SIZE) -> list[Any]:
    """取第 page 页（1-based）的条目。"""
    step = max(1, int(size or PAGE_SIZE))
    start = max(0, (int(page) - 1) * step)
    return list(items)[start : start + step]


def command_usage_text(command: Any) -> str:
    """命令的用法文本：/命令 [用法]。"""
    usage = str(getattr(command, "usage", "") or "")
    return f"{command.display_name} {usage}".strip()


def command_row_left(command: Any) -> str:
    """列表行左侧：/命令 [用法]。"""
    return command_usage_text(command)


def command_description(command: Any) -> str:
    """命令的一句话描述。"""
    return str(getattr(command, "description", "") or "")


def command_permission_label(command: Any) -> str:
    """权限标签：[权限: xxx]。"""
    return f"[权限: {permission_name(int(getattr(command, 'permission', 0) or 0))}]"


def command_meta_lines(command: Any) -> list[str]:
    """列表行右侧的元信息行（权限 + 来源），逐行渲染，避免窄列里折行。"""
    lines = [command_permission_label(command)]
    source_label = str(getattr(command, "source_label", "") or "")
    if source_label:
        lines.append(source_label)
    return lines


def command_row_right(command: Any) -> str:
    """列表行右侧（markdown / 纯文本降级用）：描述 + [权限: xxx] + [来源: plugin]。"""
    parts = [command_description(command), *command_meta_lines(command)]
    return " ".join(part for part in parts if part)


def build_list_payload(
    commands: Any,
    *,
    page: int | None = None,
    size: int = PAGE_SIZE,
    requested_page: int | None = None,
) -> dict[str, Any]:
    """列表卡片 payload：排序、分页、页脚与越界提示都在这里定稿。"""
    ordered = sorted(list(commands or ()), key=lambda item: str(item.name))
    total = len(ordered)
    step = max(1, int(size or PAGE_SIZE))
    pages = total_pages(total, step)
    current = clamp_page(page, pages)
    items = paginate(ordered, current, step)

    if total > step:
        # 页码信息交给翻页条（第 X/Y 页 + 圆点进度），页脚只留总量与翻页提示
        footer = f"共 {total} 条 · 用 /help <页码> 翻页"
    else:
        footer = f"共 {total} 条"

    requested = current if requested_page is None else int(requested_page)
    subtitle = ""
    if requested != current:
        subtitle = f"页码 {requested} 超出范围（共 {pages} 页），已显示第 {current} 页"

    if items:
        # 三列固定布局：命令列不再被挤到折行，权限 / 来源各自成行且不折行
        blocks: list[dict[str, Any]] = [
            {
                "kind": "rows",
                "columns": ["命令", "说明", "权限 / 来源"],
                "widths": ["36%", "42%", "22%"],
                "variant": "commands",
                "rows": [
                    [command_row_left(item), command_description(item), command_meta_lines(item)]
                    for item in items
                ],
            }
        ]
        if total > step:
            blocks.append({"kind": "pager", "page": current, "pages": pages})
    else:
        blocks = [{"kind": "note", "text": EMPTY_TEXT}]

    return {
        "kind": "list",
        "title": LIST_TITLE,
        "subtitle": subtitle,
        "footer": footer,
        "blocks": blocks,
        "commands": items,
        "page": current,
        "pages": pages,
        "total": total,
        "size": step,
    }


def build_detail_payload(command: Any) -> dict[str, Any]:
    """详情卡片 payload：命令名、描述、权限 / 用法 / 别名 / 来源 + 参数表。"""
    aliases = "、".join(f"/{alias}" for alias in (getattr(command, "aliases", ()) or ()))
    items: list[tuple[str, str]] = [
        ("描述", str(getattr(command, "description", "") or "（无）")),
        ("权限", permission_name(int(getattr(command, "permission", 0) or 0))),
        ("用法", command_usage_text(command)),
        ("别名", aliases or "（无）"),
    ]
    source = str(getattr(command, "source", "") or "")
    if source:
        items.append(("来源", source))

    blocks: list[dict[str, Any]] = [{"kind": "kv", "items": items}]
    params = tuple(getattr(command, "params", ()) or ())
    if params:
        blocks.append(
            {
                "kind": "rows",
                "columns": ["参数", "说明"],
                "rows": [[str(name), str(desc)] for name, desc in params],
            }
        )
    return {
        "kind": "detail",
        "title": f"{DETAIL_TITLE_PREFIX} {command.display_name}",
        "subtitle": str(getattr(command, "description", "") or ""),
        "footer": "命令以 / 开头，群聊中需先 @bot。",
        "blocks": blocks,
        "command": command,
    }


#: 详情卡里用等宽字体展示的字段（命令 / 用法这类要逐字符读的内容）
_MONO_LABELS = frozenset({"用法"})

#: 详情卡里用胶囊标签展示的字段（权限 / 来源这类短标签）
_CHIP_LABELS = frozenset({"权限", "来源"})


def _detail_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """详情卡的呈现微调：用法用等宽、权限 / 来源用胶囊标签（仅影响 HTML）。"""
    blocks: list[dict[str, Any]] = []
    for block in payload.get("blocks") or ():
        if not isinstance(block, dict) or block.get("kind") != "kv":
            blocks.append(block)
            continue
        items: list[tuple[Any, Any]] = []
        for item in block.get("items") or ():
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                label, value = item[0], item[1]
            else:
                items.append(item)
                continue
            key = str(label)
            if key in _MONO_LABELS:
                items.append((label, {"text": value, "mono": True}))
            elif key in _CHIP_LABELS:
                items.append((label, {"text": value, "chip": True}))
            else:
                items.append((label, value))
        blocks.append({"kind": "kv", "items": items})
    return blocks


def render_payload_html(
    payload: dict[str, Any], *, theme: str = "default", width: int = 720
) -> str:
    """把 payload 渲染为自包含 HTML 卡片（复用 runtime/html_card.py）。"""
    blocks = payload.get("blocks") or ()
    if payload.get("kind") != "list":
        blocks = _detail_blocks(payload)
    return render_card_html(
        title=str(payload.get("title") or ""),
        subtitle=str(payload.get("subtitle") or ""),
        blocks=blocks,
        footer=str(payload.get("footer") or ""),
        theme=theme,
        width=width,
    )


def render_payload_markdown(payload: dict[str, Any]) -> str:
    """二级降级：与卡片等价的 markdown（交给既有 markdown 转图片渲染器）。"""
    if payload.get("kind") == "list":
        lines = [f"# {payload.get('title') or ''}"]
    else:
        # 详情标题沿用既有 markdown 约定：一级标题是行内代码的命令名
        display = str(getattr(payload.get("command"), "display_name", "") or "")
        lines = [f"# {_BT}{display or payload.get('title') or ''}{_BT}"]
    subtitle = str(payload.get("subtitle") or "")
    if subtitle:
        lines.append(f"> {subtitle}")
    lines.append("")
    if payload.get("kind") == "list":
        for command in payload.get("commands") or ():
            usage = command_row_left(command)
            lines.append(f"- {_BT}{usage}{_BT} — {command_row_right(command)}")
    else:
        lines.append("| 项目 | 内容 |")
        lines.append("| --- | --- |")
        for block in payload.get("blocks") or ():
            if block.get("kind") == "kv":
                for label, value in block.get("items") or ():
                    # 用法沿用既有 markdown 约定：写成行内代码
                    shown = f"{_BT}{value}{_BT}" if label == "用法" else value
                    lines.append(f"| {label} | {shown} |")
            elif block.get("kind") == "rows":
                lines.append("")
                lines.append("## 参数")
                lines.append("")
                for row in block.get("rows") or ():
                    lines.append(f"| {_BT}{row[0]}{_BT} | {row[1]} |")
    footer = str(payload.get("footer") or "")
    if footer:
        lines.append("")
        lines.append(f"> {footer}")
    return "\n".join(lines)


def render_payload_text(payload: dict[str, Any]) -> str:
    """三级降级：纯文本（用户一定有反馈，标题沿用既有「可用命令:」文案）。"""
    lines = [f"{payload.get('title') or ''}:"]
    subtitle = str(payload.get("subtitle") or "")
    if subtitle:
        lines.append(subtitle)
    if payload.get("kind") == "list":
        commands = list(payload.get("commands") or ())
        if commands:
            for command in commands:
                lines.append(f"  {command.help_line}")
        else:
            lines.append(f"  {EMPTY_TEXT}")
    else:
        for block in payload.get("blocks") or ():
            if block.get("kind") == "kv":
                for label, value in block.get("items") or ():
                    lines.append(f"  {label}: {value}")
            elif block.get("kind") == "rows":
                lines.append("  参数:")
                for row in block.get("rows") or ():
                    lines.append(f"    {row[0]} — {row[1]}")
    footer = str(payload.get("footer") or "")
    if footer:
        lines.append(footer)
    return "\n".join(line for line in lines if line != "")


__all__ = [
    "DETAIL_TITLE_PREFIX",
    "EMPTY_TEXT",
    "FALLBACK_HINT",
    "LIST_TITLE",
    "PAGE_SIZE",
    "build_detail_payload",
    "build_list_payload",
    "clamp_page",
    "command_description",
    "command_meta_lines",
    "command_permission_label",
    "command_row_left",
    "command_row_right",
    "command_usage_text",
    "paginate",
    "parse_help_args",
    "render_payload_html",
    "render_payload_markdown",
    "render_payload_text",
    "total_pages",
]

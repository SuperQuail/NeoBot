"""
agent-browser — 页面快照系统

生成页面的可访问性树，为 AI 代理提供带 @ref 引用的元素列表。
每个交互元素分配唯一标识符（@e1, @e2, ...），代理可通过引用操作元素。
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from DrissionPage import ChromiumPage


@dataclass
class ElementRef:
    """页面中一个可交互元素的引用。"""
    ref: str           # @e1, @e2, ...
    tag: str           # a, button, input, textarea, select, [role=*]
    text: str          # 可见文本
    attrs: dict = field(default_factory=dict)
    selector: str = "" # 最佳 CSS 选择器


# 需要获取的可交互元素标签
_INTERACTIVE_TAGS = {"a", "button", "input", "textarea", "select", "details", "summary"}
# 具有交互角色的元素
_INTERACTIVE_ROLES = {"button", "link", "checkbox", "radio", "tab", "menuitem",
                      "combobox", "switch", "slider", "textbox", "searchbox",
                      "spinbutton", "option"}


def _build_css_selector(el) -> str:
    """为元素生成最佳 CSS 选择器。"""
    tag = el.tag
    # 优先用 id
    el_id = el.attr("id")
    if el_id:
        return f"#{el_id}"

    # 用 class
    classes = (el.attr("class") or "").strip()
    if classes:
        cls_part = ".".join(c for c in classes.split() if c)[:60]
        if cls_part:
            return f"{tag}.{cls_part}"

    # 用文本内容（仅对 a/button 有效）
    text = (el.text or "").strip()[:30]
    if text and tag in ("a", "button"):
        return f"{tag}:has-text('{text}')"

    return tag


def _get_element_text(el) -> str:
    """获取元素的最佳可见文本。"""
    text = (el.text or "").strip()
    if text:
        return text[:120]
    # 对 input，用 placeholder 或 value
    placeholder = el.attr("placeholder")
    if placeholder:
        return f"[placeholder={placeholder}]"
    value = el.attr("value")
    if value:
        return f"[value={value[:30]}]"
    # 对 a 用 href
    href = el.attr("href")
    if href:
        return f"[href={href[:60]}]"
    alt = el.attr("alt")
    if alt:
        return f"[img:{alt[:60]}]"
    aria = el.attr("aria-label")
    if aria:
        return f"[aria-label={aria[:60]}]"
    return f"<{el.tag}>"


def _get_element_depth(page: ChromiumPage, el) -> int:
    """获取元素在 DOM 树中的深度。"""
    try:
        result = page.run_js(
            "(function(el){let d=0;while(el&&el.tagName!=='BODY'){el=el.parentElement;d++}return d})",
            el,
        )
        return int(result) if result else 0
    except Exception:
        return 0


def _collect_elements(
    page: ChromiumPage,
    interactive_only: bool = True,
    scope: str = "",
    max_depth: int = 0,
) -> list[ElementRef]:
    """收集页面中所有可交互元素，生成带 @ref 的列表。"""
    refs: list[ElementRef] = []
    seen_selectors: set[str] = set()

    scope_el = None
    if scope:
        try:
            scope_el = page.ele(scope)
        except Exception:
            pass

    def _query(selector: str):
        if scope_el:
            try:
                return scope_el.eles(selector)
            except Exception:
                return []
        return page.eles(selector)

    def _is_visible(el) -> bool:
        try:
            return bool(page.run_js("return arguments[0].offsetParent !== null", el))
        except Exception:
            return False

    def _check_depth(el) -> bool:
        if max_depth <= 0:
            return True
        return _get_element_depth(page, el) <= max_depth

    # 1. 收集可交互元素
    for tag in _INTERACTIVE_TAGS:
        els = _query(f"tag:{tag}")
        for el in els:
            try:
                if not _is_visible(el) or not _check_depth(el):
                    continue
                text = _get_element_text(el)
                sel = _build_css_selector(el)
                tag_name = el.tag
                attrs = {}
                for attr in ("href", "src", "type", "role", "aria-label", "placeholder", "value"):
                    v = el.attr(attr)
                    if v:
                        attrs[attr] = v
                key = f"{tag_name}:{text[:40]}:{attrs.get('href','')[:40]}"
                if key in seen_selectors:
                    continue
                seen_selectors.add(key)
                refs.append(ElementRef("", tag_name, text, attrs, sel))
            except Exception:
                continue

    # 2. 收集 [role=*] 交互元素
    for role in _INTERACTIVE_ROLES:
        try:
            els = _query(f"[role=\"{role}\"]")
            for el in els:
                try:
                    if not _is_visible(el) or not _check_depth(el):
                        continue
                    text = _get_element_text(el)
                    sel = _build_css_selector(el)
                    attrs = {"role": role}
                    for attr in ("aria-label", "aria-expanded", "aria-selected"):
                        v = el.attr(attr)
                        if v:
                            attrs[attr] = v
                    key = f"role:{role}:{text[:40]}"
                    if key in seen_selectors:
                        continue
                    seen_selectors.add(key)
                    refs.append(ElementRef("", el.tag, text, attrs, sel))
                except Exception:
                    continue
        except Exception:
            continue

    # 3. 非交互模式：收集标题/图片/段落等重要可见元素
    if not interactive_only:
        _CONTENT_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "img", "li", "span", "label", "td", "th"}
        for tag in _CONTENT_TAGS:
            try:
                els = _query(f"tag:{tag}")
                for el in els:
                    try:
                        if not _is_visible(el) or not _check_depth(el):
                            continue
                        text = _get_element_text(el)
                        sel = _build_css_selector(el)
                        tag_name = el.tag
                        attrs = {}
                        for attr in ("src", "alt", "aria-label"):
                            v = el.attr(attr)
                            if v:
                                attrs[attr] = v
                        key = f"content:{tag_name}:{text[:40]}:{attrs.get('src','')[:40]}"
                        if key in seen_selectors:
                            continue
                        seen_selectors.add(key)
                        refs.append(ElementRef("", tag_name, text, attrs, sel))
                    except Exception:
                        continue
            except Exception:
                continue

    # 4. 分配 @ref 编号
    for i, ref in enumerate(refs):
        ref.ref = f"@e{i + 1}"

    return refs


def format_snapshot(refs: list[ElementRef]) -> str:
    """将元素快照格式化为 AI 可读的紧凑文本。"""
    if not refs:
        return "(页面无可交互元素)"

    lines = ["【页面可交互元素】"]
    for ref in refs:
        parts = [ref.ref, f"<{ref.tag}>", ref.text]
        extra = []
        if "href" in ref.attrs:
            extra.append(f"href={ref.attrs['href'][:60]}")
        if "role" in ref.attrs:
            extra.append(f"role={ref.attrs['role']}")
        if "placeholder" in ref.attrs:
            extra.append(f"placeholder={ref.attrs['placeholder']}")
        if extra:
            parts.append(f"({' '.join(extra)})")
        lines.append("  " + "  ".join(parts))

    lines.append(f"\n共 {len(refs)} 个可交互元素")
    return "\n".join(lines)


def format_detailed(refs: list[ElementRef]) -> str:
    """详细的快照格式（含选择器信息）。"""
    if not refs:
        return "(页面无可交互元素)"

    lines = ["【页面可交互元素快照】"]
    for ref in refs:
        lines.append(f"  {ref.ref}  <{ref.tag}>  {ref.text}")
        lines.append(f"       selector: {ref.selector}")
        if ref.attrs:
            attrs_str = "  ".join(f"{k}={v}" for k, v in ref.attrs.items())
            lines.append(f"       attrs: {attrs_str}")
    lines.append(f"\n共 {len(refs)} 个元素")
    return "\n".join(lines)


def format_compact(refs: list[ElementRef]) -> str:
    """极简快照格式（一行一个元素）。"""
    if not refs:
        return "(页面无可交互元素)"
    lines = []
    for ref in refs:
        extra = ""
        if "href" in ref.attrs:
            extra = f" →{ref.attrs['href'][:50]}"
        elif "role" in ref.attrs:
            extra = f" [{ref.attrs['role']}]"
        lines.append(f"  {ref.ref}  <{ref.tag}>  {ref.text[:60]}{extra}")
    lines.append(f"\n共 {len(refs)} 个元素")
    return "\n".join(lines)


async def snapshot_page(
    page: ChromiumPage,
    detailed: bool = False,
    compact: bool = False,
    interactive_only: bool = True,
    scope: str = "",
    max_depth: int = 0,
    as_json: bool = False,
) -> str | dict:
    """获取当前页面快照。"""
    try:
        refs = await asyncio.to_thread(
            _collect_elements, page, interactive_only=interactive_only,
            scope=scope, max_depth=max_depth,
        )
        if as_json:
            return {
                "element_count": len(refs),
                "elements": [
                    {
                        "ref": r.ref,
                        "tag": r.tag,
                        "text": r.text,
                        "selector": r.selector,
                        "attrs": r.attrs,
                    }
                    for r in refs
                ],
            }
        if compact:
            return format_compact(refs)
        if detailed:
            return format_detailed(refs)
        return format_snapshot(refs)
    except Exception as e:
        error_msg = f"[快照失败] {e}"
        if as_json:
            return {"error": error_msg, "element_count": 0, "elements": []}
        return error_msg


async def get_element_by_ref(page: ChromiumPage, ref: str) -> Optional[object]:
    """根据 @ref 从快照中查找元素（异步）。"""
    refs = await asyncio.to_thread(_collect_elements, page)
    for r in refs:
        if r.ref == ref:
            return await asyncio.to_thread(page.ele, r.selector)
    return None


def get_element_by_ref_sync(page: ChromiumPage, ref: str) -> Optional[object]:
    """根据 @ref 从快照中查找元素（同步）。"""
    refs = _collect_elements(page)
    for r in refs:
        if r.ref == ref:
            return page.ele(r.selector)
    return None

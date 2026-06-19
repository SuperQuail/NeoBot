"""
agent-browser — 页面快照系统

生成页面的可访问性树，为 AI 代理提供带 @ref 引用的元素列表。
每个交互元素分配唯一标识符（@e1, @e2, ...），代理可通过引用操作元素。
"""
from __future__ import annotations

import asyncio
import json
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


JS_COLLECT_SCRIPT = r"""
var _it, _ir, _ct, _parts, _sel, _results, _seen;

_it=['a','button','input','textarea','select','details','summary'];
_ir=['button','link','checkbox','radio','tab','menuitem','combobox','switch','slider','textbox','searchbox','spinbutton','option'];
_ct=['h1','h2','h3','h4','h5','h6','p','img','li','span','label','td','th'];

_parts=[];
_it.forEach(function(t){_parts.push(t);_parts.push('[role="'+t+'"]');});
_ir.forEach(function(r){_parts.push('[role="'+r+'"]');});
_sel=_parts.join(',');

_results=[];
_seen={};

function _gd(el){var d=0,p=el.parentElement;while(p&&p.tagName!=='BODY'){d++;p=p.parentElement;}return d;}
function _iv(el){try{if(el.offsetParent===null)return false;if(typeof el.checkVisibility==='function'&&!el.checkVisibility())return false;return true;}catch(e){return false;}}
function _tx(el){var t=(el.innerText||'').trim().slice(0,120);if(t)return t;if(el.placeholder)return '[placeholder='+el.placeholder+']';if(el.value)return '[value='+(el.value+'').slice(0,30)+']';if(el.href)return '[href='+el.href.slice(0,60)+']';if(el.alt)return '[img:'+el.alt.slice(0,60)+']';var al=el.getAttribute('aria-label');if(al)return '[aria-label='+al.slice(0,60)+']';return '<'+el.tagName.toLowerCase()+'>';}
function _sl(el){var t=el.tagName.toLowerCase();if(el.id)return '#'+el.id;if(el.className&&typeof el.className==='string'){var c=el.className.trim().split(/\s+/).filter(function(x){return x}).join('.');if(c)return t+'.'+c.slice(0,60);}var x=(el.innerText||'').trim().slice(0,30);if(x&&(t==='a'||t==='button')){return t+":has-text('"+x.replace(/'/g,"\\'")+"')";}return t;}
function _at(el){var a={};['href','src','type','role','aria-label','aria-expanded','aria-selected','placeholder','value','alt'].forEach(function(k){try{var v=el.getAttribute(k);if(v)a[k]=v;}catch(e){}});if(el.role&&!a.role)a.role=el.role;return a;}

function _cl(items, maxD){
for(var i=0;i<items.length;i++){try{
var el=items[i];
if(!_iv(el))continue;
if(maxD>0&&_gd(el)>maxD)continue;
var tag=el.tagName.toLowerCase(),text=_tx(el),attrs=_at(el),selector=_sl(el);
var key=tag+':'+text.slice(0,40)+':'+(attrs.href||'').slice(0,40);
if(_seen[key])continue;_seen[key]=true;
_results.push({tag:tag,text:text,selector:selector,attrs:attrs});
}catch(e){}}
}

// Determine calling convention
var root, iOnly, maxD;
if(arguments.length===3&&typeof arguments[0]==='object'&&arguments[0]!==null){
  root=arguments[0];iOnly=arguments[1]!==false;maxD=arguments[2]||0;
}else{
  root=document;iOnly=arguments[0]!==false;maxD=arguments[1]||0;
}

_cl(root.querySelectorAll(_sel),maxD);
if(!iOnly)_cl(root.querySelectorAll(_ct.join(',')),maxD);

return JSON.stringify(_results);
"""


def _collect_elements(
    page: ChromiumPage,
    interactive_only: bool = True,
    scope: str = "",
    max_depth: int = 0,
) -> list[ElementRef]:
    """收集页面中所有可交互元素，生成带 @ref 的列表。

    使用单次 JS 评估批量采集，避免逐元素 CDP 往返。
    """
    refs: list[ElementRef] = []

    # 解析 scope 元素
    scope_el = None
    if scope:
        try:
            scope_el = page.ele(scope)
        except Exception:
            pass

    # 单次 JS 调用采集所有元素数据
    try:
        if scope_el:
            raw = page.run_js(JS_COLLECT_SCRIPT, scope_el, interactive_only, max_depth)
        else:
            raw = page.run_js(JS_COLLECT_SCRIPT, interactive_only, max_depth)
    except Exception as e:
        raise RuntimeError(f"快照 JS 采集失败: {e}") from e

    # 解析 JSON 结果
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"快照结果 JSON 解析失败: {e}") from e
    elif isinstance(raw, (list, tuple)):
        data = raw
    else:
        data = []

    # 构建 ElementRef 列表
    for item in data:
        refs.append(ElementRef(
            ref="",
            tag=item.get("tag", "unknown"),
            text=item.get("text", ""),
            attrs=item.get("attrs", {}),
            selector=item.get("selector", ""),
        ))

    # 分配 @ref 编号
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

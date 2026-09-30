#!/usr/bin/env python3
"""docs/flow/*.md 的可视化查看器（spec(13) R4 / §4.2）。

两种用法::

    uv run python scripts/flow/view_flow.py                      # 起本地只读服务并打印地址
    uv run python scripts/flow/view_flow.py --port 8791 --no-open
    uv run python scripts/flow/view_flow.py --export docs/flow/_site   # 导出静态 HTML（可分享）

设计约束（与 spec(13) 一致）：

* **只读**：不写 docs/flow/ 下的任何文件，也不碰运行时代码；
* **不依赖网络**：mermaid 运行时随仓库分发（scripts/flow/vendor/mermaid.min.js），
  找不到时才回落到 CDN；
* **不引前端工程**：一个文件 + 标准库 http.server + 极简 Markdown 渲染，够看就行。

单文件视图 /view/<flow>?bare=1 只画一张图，供 scripts/flow/screenshot_flow.mjs 截图。
"""

from __future__ import annotations

import argparse
import html
import re
import socket
import sys
import threading
import urllib.parse
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

#: 图目录相对仓库根的路径
FLOW_DIR = "docs/flow"
#: 仓库内自带的 mermaid 运行时（离线渲染）
VENDOR_MERMAID = "scripts/flow/vendor/mermaid.min.js"
#: 仓库里没有 vendor 文件时的回落地址
CDN_MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
#: 导出静态站点时的默认目录（相对仓库根，已 gitignore）
DEFAULT_EXPORT_DIR = "docs/flow/_site"
#: 截图脚本等待的哨兵文字（页面渲染完成后出现在 /shot 页面里）
READY_MARKER = "渲染完成"

_FENCE = "\x60" * 3
_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_TABLE_DIVIDER = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_INLINE_CODE = re.compile("\x60([^\x60]+)\x60")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


class ViewError(RuntimeError):
    """用法或环境错误。"""


@dataclass
class Doc:
    """一张图（一个 markdown 文件）。"""

    path: Path
    stem: str
    title: str
    meta: dict[str, Any]
    body: str

    @property
    def covers(self) -> list[str]:
        raw = self.meta.get("covers")
        if isinstance(raw, list):
            return [str(item) for item in raw]
        if isinstance(raw, str) and raw:
            return [raw]
        return []


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise ViewError("找不到仓库根（向上没有 pyproject.toml）")


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta: dict[str, Any] = {}
    current: str | None = None
    for raw in match.group(1).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and current is not None:
            value = stripped[2:].strip().strip('"').strip("'")
            existing = meta.get(current)
            if isinstance(existing, list):
                existing.append(value)
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.split("  #", 1)[0].strip()
        current = key
        if not value:
            meta[key] = []
        elif value.startswith("[") and value.endswith("]"):
            meta[key] = [item.strip().strip('"') for item in value[1:-1].split(",") if item.strip()]
        else:
            meta[key] = value.strip('"').strip("'")
    return meta, text[match.end():]


def load_docs(flow_dir: Path) -> list[Doc]:
    if not flow_dir.is_dir():
        raise ViewError(f"图目录不存在：{flow_dir}")
    docs: list[Doc] = []
    for path in sorted(flow_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(text)
        title = next(
            (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("# ")),
            path.stem,
        )
        docs.append(Doc(path=path, stem=path.stem, title=title, meta=meta, body=body))
    return docs


# ────────────────────────────── Markdown -> HTML ──────────────────────────────


def inline(text: str) -> str:
    """行内标记：先转义，再还原代码/加粗/斜体/链接。"""

    escaped = html.escape(text, quote=False)
    placeholders: list[str] = []

    def stash(value: str) -> str:
        placeholders.append(value)
        return f"\x00{len(placeholders) - 1}\x00"

    escaped = _INLINE_CODE.sub(lambda m: stash(f"<code>{html.escape(m.group(1))}</code>"), escaped)
    escaped = _LINK.sub(
        lambda m: stash(
            '<a href="{href}" target="_blank" rel="noreferrer">{label}</a>'.format(
                href=html.escape(m.group(2), quote=True), label=m.group(1)
            )
        ),
        escaped,
    )
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC.sub(r"<em>\1</em>", escaped)
    escaped = re.sub("\x00(\\d+)\x00", lambda m: placeholders[int(m.group(1))], escaped)
    return escaped


def _is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|")


_DETAILS_OPEN = "<details>"
_DETAILS_CLOSE = "</details>"
_DETAILS_OPEN_WITH_ATTRS = re.compile(r"<details\s+([^>]*)>", re.IGNORECASE)


def _split_details_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """把 <details>…</details> 块解析成 [(标题, 正文)]，并返回不在块内的剩余文本。

    约定（docs/flow/README.md）：细节小节用

        <details>
        ### 小节标题
        正文（可含 mermaid）
        </details>

    写 Markdown 就能得到「可折叠的细节」，同时 GitHub 上仍然可见（默认折叠）。
    """

    sections: list[tuple[str, str]] = []
    outside: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        is_open = line.lower() == _DETAILS_OPEN or bool(_DETAILS_OPEN_WITH_ATTRS.fullmatch(line))
        if not is_open:
            outside.append(lines[index])
            index += 1
            continue
        block: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip().lower() != _DETAILS_CLOSE:
            block.append(lines[index])
            index += 1
        index += 1
        title = next(
            (item.lstrip("# ").strip() for item in block if item.strip().startswith("#")),
            "细节",
        )
        body = "\n".join(item for item in block if not item.strip().startswith("#"))
        sections.append((title, body))
    return "\n".join(outside), sections


def _render_details_sections(sections: list[tuple[str, str]], *, open_all: bool) -> str:
    """把细节小节渲染成可折叠卡片（默认折叠，供按需展开）。"""

    if not sections:
        return ""
    open_attr = " open" if open_all else ""
    parts: list[str] = ['<div class="details-block" id="details">']
    parts.append(
        '<div class="details-toolbar"><strong>细节（按需展开）</strong>'
        f'<span class="hint">{len(sections)} 个折叠小节 · 主链路在上方，看不懂再展开</span>'
        "</div>"
    )
    for position, (title, body) in enumerate(sections, start=1):
        parts.append(f'<details class="detail"{open_attr}>')
        parts.append(
            f'<summary><span class="detail-no">{position:02d}</span>'
            f'<span class="detail-title">{inline(title)}</span>'
            '<span class="detail-hint">展开 / 收起</span></summary>'
        )
        parts.append(f'<div class="detail-body">{render_markdown(body)}</div>')
        parts.append("</details>")
    parts.append("</div>")
    return "\n".join(parts)



def render_markdown(body: str) -> str:
    """够用的 Markdown 渲染：标题/列表/引用/表格/围栏代码块/段落。"""

    lines = body.splitlines()
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        # 围栏代码块（mermaid 单独标注）
        if stripped.startswith(_FENCE):
            lang = stripped[len(_FENCE):].strip()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith(_FENCE):
                block.append(lines[index])
                index += 1
            index += 1
            payload = html.escape("\n".join(block))
            css = ' class="mermaid"' if lang.lower() == "mermaid" else ""
            out.append(f"<pre class=\"code\"><code{css}>{payload}</code></pre>")
            continue

        if stripped.lower() == _DETAILS_CLOSE:
            index += 1
            continue

        # 标题
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            anchor = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-")
            out.append(f'<h{level} id="{anchor}">{inline(text)}</h{level}>')
            index += 1
            continue

        # 表格
        if _is_table_row(line) and index + 1 < len(lines) and _TABLE_DIVIDER.match(lines[index + 1]):
            header = [cell.strip() for cell in stripped.strip("|").split("|")]
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and _is_table_row(lines[index]):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            head_html = "".join(f"<th>{inline(cell)}</th>" for cell in header)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows
            )
            out.append(
                '<div class="table-wrap"><table><thead><tr>'
                + head_html
                + "</tr></thead><tbody>"
                + body_html
                + "</tbody></table></div>"
            )
            continue

        # 引用
        if stripped.startswith(">"):
            quote: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip(">").strip())
                index += 1
            out.append("<blockquote>" + inline(" ".join(quote)) + "</blockquote>")
            continue

        # 列表
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            items: list[str] = []
            while index < len(lines) and re.match(r"^\s*([-*+]|\d+\.)\s+", lines[index]):
                item = re.sub(r"^\s*([-*+]|\d+\.)\s+", "", lines[index])
                index += 1
                while (
                    index < len(lines)
                    and lines[index].strip()
                    and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[index])
                    and not lines[index].strip().startswith(("#", "|", ">", _FENCE))
                ):
                    item += " " + lines[index].strip()
                    index += 1
                items.append(f"<li>{inline(item)}</li>")
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        # 水平线
        if stripped in {"---", "***", "___"}:
            out.append("<hr />")
            index += 1
            continue

        # 段落
        paragraph: list[str] = []
        while (
            index < len(lines)
            and lines[index].strip()
            and not lines[index].strip().startswith(("#", "|", ">", _FENCE))
            and not re.match(r"^\s*([-*+]|\d+\.)\s+", lines[index])
        ):
            paragraph.append(lines[index].strip())
            index += 1
        out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
    return "\n".join(out)


def render_meta_card(doc: Doc) -> str:
    rows = []
    if doc.meta.get("verified_against"):
        rows.append(("最近核对", str(doc.meta["verified_against"])))
    if doc.meta.get("verified_hash"):
        rows.append(("内容哈希", str(doc.meta["verified_hash"])))
    covers = doc.covers
    if covers:
        rows.append(("覆盖范围", "、".join(covers)))
    if not rows:
        return ""
    cells = "".join(
        f'<div class="meta-row"><span>{html.escape(key)}</span><code>{html.escape(value)}</code></div>'
        for key, value in rows
    )
    return f'<div class="meta-card">{cells}</div>'


# ────────────────────────────── 页面 ──────────────────────────────


PAGE_CSS = """
:root { color-scheme: light; --bg:#f6f7f9; --panel:#ffffff; --ink:#1b1f24; --muted:#6b7280;
        --line:#e3e6ea; --accent:#2563eb; --code-bg:#f3f4f6; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font-family: "Segoe UI", "Microsoft YaHei", system-ui, -apple-system, sans-serif; }
.layout { display:flex; min-height:100vh; }
.sidebar { width:280px; flex:0 0 280px; background:var(--panel); border-right:1px solid var(--line);
           padding:18px 14px; position:sticky; top:0; height:100vh; overflow:auto; }
.sidebar h1 { font-size:15px; margin:0 0 4px; }
.sidebar .sub { color:var(--muted); font-size:12px; margin-bottom:14px; }
.sidebar a.item { display:block; padding:7px 9px; border-radius:7px; color:var(--ink);
                  text-decoration:none; font-size:13px; line-height:1.35; }
.sidebar a.item:hover { background:#eef2ff; }
.sidebar a.item.active { background:var(--accent); color:#fff; }
.sidebar a.item code { font-size:11px; opacity:.75; display:block; }
.main { flex:1; min-width:0; padding:22px 30px 60px; }
.toolbar { display:flex; gap:10px; align-items:center; margin-bottom:14px; flex-wrap:wrap; }
.toolbar .spacer { flex:1; }
.toolbar a, .toolbar button { font-size:13px; padding:6px 12px; border-radius:7px; border:1px solid var(--line);
       background:var(--panel); color:var(--ink); cursor:pointer; text-decoration:none; }
.toolbar a:hover, .toolbar button:hover { border-color:var(--accent); color:var(--accent); }
.doc { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:26px 30px; }
.doc h1 { font-size:23px; margin:0 0 6px; }
.doc h2 { font-size:17px; margin:30px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--line); }
.doc h3 { font-size:14px; margin:20px 0 8px; }
.doc p, .doc li { font-size:13.5px; line-height:1.7; }
.doc code { background:var(--code-bg); padding:1px 5px; border-radius:4px; font-size:12.5px;
            font-family: "Cascadia Mono", Consolas, monospace; }
.doc pre.code { background:var(--code-bg); padding:12px 14px; border-radius:8px; overflow:auto; }
.doc pre.code code { background:none; padding:0; }
.doc pre.mermaid, .doc .mermaid { background:#fff; padding:8px 0; text-align:center; }
.mermaid-rendered { text-align:center; padding:8px 0; overflow:auto; }
blockquote { margin:12px 0; padding:8px 14px; border-left:3px solid var(--accent);
             background:#f8fafc; color:var(--muted); font-size:13px; }
.table-wrap { overflow:auto; margin:12px 0; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th, td { border:1px solid var(--line); padding:7px 10px; text-align:left; vertical-align:top; }
th { background:#f1f5f9; font-weight:600; }
.meta-card { display:flex; gap:18px; flex-wrap:wrap; background:#f8fafc; border:1px dashed var(--line);
             border-radius:9px; padding:10px 14px; margin:10px 0 4px; }
.meta-row { font-size:12px; color:var(--muted); display:flex; gap:7px; align-items:baseline; }
.meta-row code { font-size:12px; color:var(--ink); }
.bare { padding:0; background:#fff; }
.bare .doc { border:0; border-radius:0; padding:18px; width:100%; max-width:100%; margin:0 auto; overflow-x:hidden; }
.bare .mermaid-rendered svg { max-width:100%; height:auto; }
.hint { color:var(--muted); font-size:12px; }
.details-block { margin-top:26px; border-top:2px dashed var(--line); padding-top:14px; }
.details-toolbar { display:flex; gap:12px; align-items:baseline; margin-bottom:10px; }
.details-toolbar strong { font-size:15px; }
details.detail { border:1px solid var(--line); border-radius:10px; margin:8px 0; background:#fcfcfe; }
details.detail > summary { cursor:pointer; padding:10px 14px; font-size:13.5px; display:flex;
                           gap:10px; align-items:center; list-style:none; }
details.detail > summary::-webkit-details-marker { display:none; }
details.detail > summary:hover { background:#eef2ff; }
.detail-no { font-family:"Cascadia Mono",Consolas,monospace; font-size:12px; color:var(--accent); }
.detail-title { font-weight:600; flex:1; }
.detail-hint { font-size:11px; color:var(--muted); }
.detail-body { padding:6px 16px 14px; border-top:1px solid var(--line); background:#fff;
               border-radius:0 0 10px 10px; }
details.diagram-fold { margin:10px 0; border:1px solid var(--line); border-radius:9px; background:#fff; }
details.diagram-fold > summary { cursor:pointer; padding:8px 12px; font-size:12.5px; display:flex;
                                 gap:10px; align-items:center; list-style:none; background:#f8fafc;
                                 border-radius:9px; }
details.diagram-fold > summary::-webkit-details-marker { display:none; }
details.diagram-fold[open] > summary { border-radius:9px 9px 0 0; border-bottom:1px solid var(--line); }
.fold-no { font-family:"Cascadia Mono",Consolas,monospace; color:var(--accent); font-size:12px; }
.fold-title { flex:1; color:var(--muted); }
.fold-hint { font-size:11px; color:var(--muted); }
.toggle-all { font-size:12px; padding:5px 10px; border-radius:6px; border:1px solid var(--line);
              background:var(--panel); cursor:pointer; }
.toggle-all:hover { border-color:var(--accent); color:var(--accent); }
.shot-ready { text-align:center; color:#9ca3af; font-size:12px; padding:10px 0 22px; }
"""

RUNTIME_JS = """
(function () {
  var cfg = { startOnLoad: false, securityLevel: 'loose', theme: 'default',
              flowchart: { htmlLabels: true, useMaxWidth: false },
              sequence: { useMaxWidth: false } };
  function render() {
    if (!window.mermaid) { document.body.setAttribute('data-mermaid', 'missing'); return; }
    window.mermaid.initialize(cfg);
    var nodes = Array.prototype.slice.call(document.querySelectorAll('.mermaid'));
    Promise.all(nodes.map(function (node, i) {
      var source = node.textContent;
      return window.mermaid.render('mmd-' + i, source).then(function (out) {
        var holder = document.createElement('div');
        holder.className = 'mermaid-rendered';
        holder.setAttribute('data-mermaid-index', String(i));
        holder.innerHTML = out.svg;
        node.parentNode.replaceChild(holder, node);
      }).catch(function (err) {
        var pre = document.createElement('pre');
        pre.className = 'mermaid-error';
        pre.style.color = '#b91c1c';
        pre.style.whiteSpace = 'pre-wrap';
        pre.textContent = '[mermaid 渲染失败] ' + (err && err.message ? err.message : err);
        node.parentNode.replaceChild(pre, node);
        document.body.setAttribute('data-mermaid', 'error');
      });
    })).then(function () {
      wrapDetails();
      if (document.body.getAttribute('data-mermaid') !== 'error') {
        document.body.setAttribute('data-mermaid', 'ready');
      }
    });
  }

  // 每个图块包一层 <details>：默认展开主图，折叠后续细节图，按需打开
  function wrapDetails() {
    var blocks = Array.prototype.slice.call(document.querySelectorAll('.mermaid-rendered'));
    blocks.forEach(function (block, i) {
      if (block.parentNode && block.parentNode.classList.contains('diagram-fold')) { return; }
      var fold = document.createElement('details');
      fold.className = 'diagram-fold';
      fold.setAttribute('data-mermaid-index', String(i));
      var summary = document.createElement('summary');
      var head = (block.textContent || '').trim().slice(0, 60);
      summary.innerHTML = '<span class="fold-no">图 ' + (i + 1) + '</span>' +
        '<span class="fold-title">' + escapeHtml(head) + '</span>' +
        '<span class="fold-hint">展开 / 收起</span>';
      block.parentNode.insertBefore(fold, block);
      fold.appendChild(summary);
      fold.appendChild(block);
      // open 状态统一在循环结束后按「是否展开全部」设置
    });
    var block0 = document.querySelectorAll('.diagram-fold')[0];
    var expandAll = document.body.getAttribute('data-expand') === '1';
    Array.prototype.forEach.call(document.querySelectorAll('.diagram-fold'), function (fold, i) {
      fold.open = expandAll || i === 0;
    });
    void block0;
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"]/g, function (ch) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch];
    });
  }

  // 「仅图」页面上的全展开 / 全收起
  document.addEventListener('click', function (event) {
    var button = event.target.closest ? event.target.closest('.toggle-all') : null;
    if (!button) { return; }
    var expand = button.getAttribute('data-mode') === 'expand';
    Array.prototype.forEach.call(document.querySelectorAll('details'), function (node) {
      node.open = expand;
    });
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', render);
  } else { render(); }
})();
"""


def render_page(
    doc: Doc,
    docs: Sequence[Doc],
    *,
    bare: bool,
    mermaid_href: str,
    base_href: str = "",
    expand_all: bool = False,
) -> str:
    """渲染一页。bare=True 时去掉侧栏/工具栏（截图用），expand_all 展开全部细节。"""

    main_body, sections = _split_details_sections(doc.body)
    body_html = (
        render_meta_card(doc)
        + render_markdown(main_body)
        + _render_details_sections(sections, open_all=expand_all)
    )
    title = html.escape(doc.title)
    if bare:
        return (
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
            f"<title>{title}</title><style>{PAGE_CSS}</style></head>"
            f'<body class="bare" data-expand="{int(expand_all)}"><div class="doc">{body_html}</div>'
            f'<div class="shot-ready">{READY_MARKER}</div>'
            f'<script src="{mermaid_href}"></script><script>{RUNTIME_JS}</script></body></html>'
        )

    items: list[str] = []
    for item in docs:
        active = " active" if item.stem == doc.stem else ""
        flow_id = item.meta.get("flow") or item.stem
        items.append(
            f'<a class="item{active}" href="{base_href}view/{urllib.parse.quote(item.stem)}">'
            f"{html.escape(item.title)}<code>{html.escape(str(flow_id))}</code></a>"
        )
    order = [item.stem for item in docs]
    position = order.index(doc.stem) if doc.stem in order else 0
    prev_link = (
        f'<a href="{base_href}view/{urllib.parse.quote(order[position - 1])}">上一张</a>'
        if position > 0
        else "<span></span>"
    )
    next_link = (
        f'<a href="{base_href}view/{urllib.parse.quote(order[position + 1])}">下一张</a>'
        if position + 1 < len(order)
        else "<span></span>"
    )
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{title} · NeoBot 流程图</title><style>{PAGE_CSS}</style></head><body>"
        '<div class="layout"><aside class="sidebar"><h1>NeoBot 全链路流程图</h1>'
        f'<div class="sub">{len(docs)} 张图 · spec(13)</div>'
        + "".join(items)
        + '</aside><main class="main"><div class="toolbar">'
        + prev_link
        + next_link
        + '<span class="spacer"></span>'
        + f'<a href="{base_href}view/{urllib.parse.quote(doc.stem)}?bare=1">仅图视图</a>'
        + f'<a href="{base_href}">总索引</a>'
        + '<button type="button" class="toggle-all" data-mode="expand">展开全部细节</button>'
        + '<button type="button" class="toggle-all" data-mode="collapse">收起全部</button>'
        + '<span class="hint">改图后在仓库根跑 scripts/flow/check_flow_diagrams.py --update</span>'
        + f'</div><div class="doc">{body_html}</div></main></div>'
        + f'<script src="{mermaid_href}"></script>'
        + f"<script>{RUNTIME_JS}</script></body></html>"
    )


def render_index(docs: Sequence[Doc], *, base_href: str = "") -> str:
    cards: list[str] = []
    for doc in docs:
        covers = "、".join(doc.covers)
        cards.append(
            '<div style="border:1px solid var(--line);border-radius:10px;'
            'padding:14px 16px;margin:10px 0;background:#fff">'
            f'<a href="{base_href}view/{urllib.parse.quote(doc.stem)}" style="font-size:15px;'
            f'font-weight:600;text-decoration:none;color:#1b1f24">{html.escape(doc.title)}</a>'
            f'<div class="hint" style="margin-top:6px">覆盖：{html.escape(covers)}</div>'
            f'<div class="hint" style="margin-top:4px">最近核对 '
            f'{html.escape(str(doc.meta.get("verified_against") or "-"))} · '
            f'哈希 {html.escape(str(doc.meta.get("verified_hash") or "-"))}</div></div>'
        )
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
        "<title>NeoBot 全链路流程图</title>"
        f"<style>{PAGE_CSS}</style></head><body><div class=\"main\">"
        '<div class="doc"><h1>NeoBot 全链路流程图</h1>'
        f'<p class="hint">共 {len(docs)} 张图（spec(13)）。点开任意一张查看流程图与时序图。</p>'
        + "".join(cards)
        + "</div></div></body></html>"
    )


# ────────────────────────────── 服务 ──────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    server_version = "NeoBotFlowView/1.0"
    docs: list[Doc] = []
    mermaid_href = CDN_MERMAID
    asset_dir = Path(".")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 基类签名
        if getattr(self.server, "verbose", False):
            super().log_message(format, *args)

    def do_GET(self) -> None:  # noqa: N802 - 基类签名
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"

        if route == "/":
            self._send_html(render_index(self.docs))
            return
        if route.startswith("/view/"):
            stem = urllib.parse.unquote(route[len("/view/"):])
            doc = next((d for d in self.docs if d.stem == stem), None)
            if doc is None:
                self._send_html("<h1>404</h1><p>没有这张图</p>", status=404)
                return
            bare = query.get("bare", ["0"])[0] in {"1", "true", "yes"}
            self._send_html(render_page(doc, self.docs, bare=bare, mermaid_href=self.mermaid_href))
            return
        if route.startswith("/shot/"):
            stem = urllib.parse.unquote(route[len("/shot/"):])
            doc = next((d for d in self.docs if d.stem == stem), None)
            if doc is None:
                self._send_html("<h1>404</h1><p>没有这张图</p>", status=404)
                return
            expand = query.get("expand", ["0"])[0] in {"1", "true", "yes"}
            self._send_html(
                render_page(
                    doc,
                    self.docs,
                    bare=True,
                    mermaid_href=self.mermaid_href,
                    expand_all=expand,
                )
            )
            return
        if route.startswith("/asset/"):
            name = Path(urllib.parse.unquote(route[len("/asset/"):])).name
            target = self.asset_dir / name
            if target.is_file():
                self._send_bytes(target.read_bytes(), "application/javascript; charset=utf-8")
                return
            self._send_html("<h1>404</h1>", status=404)
            return
        self._send_html("<h1>404</h1>", status=404)

    def _send_html(self, body: str, *, status: int = 200) -> None:
        self._send_bytes(body.encode("utf-8"), "text/html; charset=utf-8", status=status)

    def _send_bytes(self, payload: bytes, content_type: str, *, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def _pick_port(host: str, port: int) -> int:
    if port:
        return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def create_server(
    root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    verbose: bool = False,
) -> ThreadingHTTPServer:
    docs = load_docs(root / FLOW_DIR)
    if not docs:
        raise ViewError(f"{FLOW_DIR} 下没有 *.md")

    vendor = root / VENDOR_MERMAID
    if vendor.is_file():
        asset_dir = vendor.parent
        mermaid_href = f"/asset/{vendor.name}"
    else:
        print(
            f"[flow-view] 未找到 {VENDOR_MERMAID}，回落到 CDN（离线环境会渲染失败）",
            file=sys.stderr,
        )
        asset_dir = root / "docs" / "flow"
        mermaid_href = CDN_MERMAID

    server = ThreadingHTTPServer((host, _pick_port(host, port)), _Handler)
    server.docs = docs  # type: ignore[attr-defined]
    server.asset_dir = asset_dir  # type: ignore[attr-defined]
    server.verbose = verbose  # type: ignore[attr-defined]
    _Handler.docs = docs
    _Handler.mermaid_href = mermaid_href
    _Handler.asset_dir = asset_dir
    return server


# ────────────────────────────── 导出 ──────────────────────────────


def export_static(root: Path, out_dir: Path) -> list[Path]:
    """把每张图导出成单文件、自包含的 HTML（mermaid 内联），可直接分享。"""

    docs = load_docs(root / FLOW_DIR)
    if not docs:
        raise ViewError(f"{FLOW_DIR} 下没有 *.md")
    vendor = root / VENDOR_MERMAID
    if vendor.is_file():
        runtime = vendor.read_text(encoding="utf-8")
        script = f"<script>{runtime}</script>"
    else:
        script = f'<script src="{CDN_MERMAID}"></script>'

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index_items: list[str] = []
    for doc in docs:
        body_html = render_meta_card(doc) + render_markdown(doc.body)
        target = out_dir / f"{doc.stem}.html"
        target.write_text(
            '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
            f"<title>{html.escape(doc.title)}</title><style>{PAGE_CSS}</style></head>"
            f'<body class="bare"><div class="doc">{body_html}</div>'
            f"{script}<script>{RUNTIME_JS}</script></body></html>",
            encoding="utf-8",
        )
        written.append(target)
        index_items.append(f'<li><a href="{doc.stem}.html">{html.escape(doc.title)}</a></li>')
    index_path = out_dir / "index.html"
    index_path.write_text(
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
        "<title>NeoBot 全链路流程图</title>"
        f"<style>{PAGE_CSS}</style></head><body><div class=\"main\"><div class=\"doc\">"
        "<h1>NeoBot 全链路流程图</h1><ul>"
        + "".join(index_items)
        + "</ul></div></div></body></html>",
        encoding="utf-8",
    )
    written.append(index_path)
    return written


# ────────────────────────────── 入口 ──────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="docs/flow 可视化查看器（spec(13) R4）")
    parser.add_argument("--root", default=None, help="仓库根（默认自动向上查找）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 = 自动挑选空闲端口")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--verbose", action="store_true", help="打印访问日志")
    parser.add_argument(
        "--export",
        nargs="?",
        const=DEFAULT_EXPORT_DIR,
        default=None,
        help=f"导出静态 HTML 到目录（默认 {DEFAULT_EXPORT_DIR}）后退出",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        root = Path(args.root).resolve() if args.root else find_repo_root()
    except ViewError as exc:
        print(f"[flow-view] {exc}", file=sys.stderr)
        return 2

    if args.export is not None:
        out_dir = Path(args.export)
        if not out_dir.is_absolute():
            out_dir = root / out_dir
        try:
            written = export_static(root, out_dir)
        except ViewError as exc:
            print(f"[flow-view] {exc}", file=sys.stderr)
            return 2
        print(f"[flow-view] 已导出 {len(written)} 个文件到 {out_dir}")
        for path in written[:8]:
            print(f"  - {path.relative_to(root).as_posix()}")
        if len(written) > 8:
            print(f"  … 其余 {len(written) - 8} 个")
        return 0

    try:
        server = create_server(root, host=args.host, port=args.port, verbose=args.verbose)
    except ViewError as exc:
        print(f"[flow-view] {exc}", file=sys.stderr)
        return 2

    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"[flow-view] 已启动：{url}")
    print(f"[flow-view] 共 {len(server.docs)} 张图；Ctrl+C 退出")  # type: ignore[attr-defined]
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[flow-view] 已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

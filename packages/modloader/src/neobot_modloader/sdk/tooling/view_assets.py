"""只验证页面源码中明确的字面资源引用，不推测动态业务地址。"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from neobot_modloader.sdk.views import resolve_view_file

from .models import ToolingError

_CSS_URL = re.compile(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", re.I)
_CSS_IMPORT = re.compile(r"@import\s+['\"]([^'\"]+)['\"]", re.I)
_JS_IMPORT = re.compile(r"\b(?:import|export)\s*(?:[^;\n'\"]*?\bfrom\s*)?['\"]([^'\"]+)['\"]")
_JS_DYNAMIC = re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_JS_URL = re.compile(r"\bnew\s+URL\(\s*['\"]([^'\"]+)['\"]\s*,\s*import\.meta\.url\s*\)")


def _css(text: str) -> list[str]:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return _CSS_URL.findall(text) + _CSS_IMPORT.findall(text)


def _javascript(text: str) -> list[str]:
    imports = _JS_IMPORT.findall(text) + _JS_DYNAMIC.findall(text)
    return [value for value in imports if value.startswith(("./", "../"))] + _JS_URL.findall(text)


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self.inline = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is None:
                continue
            if name in {"src", "href", "poster"}:
                self.references.append(value)
            elif name == "style":
                self.references.extend(_css(value))
            elif name == "srcset" and not value.lstrip().startswith("data:"):
                self.references.extend(item.strip().split()[0] for item in value.split(",") if item.strip())
        if tag in {"style", "script"}:
            self.inline = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self.inline:
            self.inline = ""

    def handle_data(self, data: str) -> None:
        if self.inline == "style":
            self.references.extend(_css(data))
        elif self.inline == "script":
            self.references.extend(_javascript(data))


def _source_references(source: Path) -> list[str]:
    text = source.read_text(encoding="utf-8-sig")
    if source.suffix.lower() in {".html", ".htm"}:
        page = _Page()
        page.feed(text)
        return page.references
    if source.suffix.lower() == ".css":
        return _css(text)
    return _javascript(text)


def _referenced_assets(
    root: Path,
    entry: str,
    directory: Path,
    source: Path,
    distributed: set[Path],
) -> Iterable[Path]:
    """逐项解析本地引用，并保留引用来源及包内文件边界的错误上下文。"""
    for reference in _source_references(source):
        parts = urlsplit(reference.strip())
        external_or_empty = parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/")
        if external_or_empty:
            continue
        path = unquote(parts.path, errors="strict")
        parent = source.relative_to(directory).parent.as_posix()
        relative = posixpath.normpath(posixpath.join(parent, path))
        if relative in {"_sdk.js", "_ui.css"}:
            continue
        try:
            target = resolve_view_file(root, entry, relative)
            if target not in distributed:
                raise ValueError("资源未包含在分发文件中")
        except (OSError, ValueError) as exc:
            raise ToolingError(f"{source.relative_to(root).as_posix()} 引用 {reference}: {exc}") from None
        yield target


def check_view_assets(root: Path, entry: str, distributed: set[Path]) -> None:
    """相对路径按引用文件目录解析；宿主提供页面根下的桥接与公共样式。"""
    first = resolve_view_file(root, entry)
    directory = first.parent
    pending = [first]
    seen = set()
    while pending:
        source = pending.pop()
        if source in seen:
            continue
        seen.add(source)
        if source.suffix.lower() not in {".html", ".htm", ".css", ".js", ".mjs"}:
            continue
        pending.extend(_referenced_assets(root, entry, directory, source, distributed))

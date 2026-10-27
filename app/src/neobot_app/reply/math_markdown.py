"""Safe Markdown with bounded, code-aware TeX protection.

TeX is data, never executable HTML. The browser consumer must use KaTeX with
``trust=False``, ``maxExpand`` and ``maxSize`` limits. No TeX is sent to pillowlatex.
"""

import html
import re
import secrets
from collections.abc import Callable

from markdown_it import MarkdownIt

_MAX_FORMULA = 8192
_MAX_INPUT = 100_000


def _protect(text: str, replace: Callable[[str, bool, str], str]) -> str:
    """Scan without recursion; delimiter searches have a fixed upper bound."""
    output: list[str] = []
    pos = 0
    # Let CommonMark identify code blocks, including nested list/quote fences.
    # Their original source ranges must survive the pre-protection unchanged.
    offsets = [0, *(match.end() for match in re.finditer(r"\r\n?|\n", text)), len(text)]
    code_ranges = [
        (offsets[token.map[0]], offsets[token.map[1]])
        for token in MarkdownIt("commonmark", {"html": False}).parse(text)
        if token.type in {"fence", "code_block"} and token.map is not None
    ]
    code_index = 0
    while pos < len(text):
        while code_index < len(code_ranges) and pos >= code_ranges[code_index][1]:
            code_index += 1
        boundary = code_ranges[code_index][0] if code_index < len(code_ranges) else len(text)
        if pos >= boundary:
            end = code_ranges[code_index][1]
            output.append(text[pos:end])
            pos = end
            continue
        if text[pos] == "`":
            end = pos + 1
            while end < len(text) and text[end] == "`":
                end += 1
            run = text[pos:end]
            closing = text.find(run, end, boundary)
            while closing >= 0 and (
                text[closing - 1] == "`" or (closing + len(run) < len(text) and text[closing + len(run)] == "`")
            ):
                closing = text.find(run, closing + len(run), boundary)
            if closing >= 0:
                end = closing + len(run)
            output.append(text[pos:end])
            pos = end
            continue
        opening = next((x for x in ("$$", r"\[", r"\(", "$") if text.startswith(x, pos)), None)
        if opening:
            closing = {"$$": "$$", r"\[": r"\]", r"\(": r"\)", "$": "$"}[opening]
            start = pos + len(opening)
            stop = min(boundary, start + _MAX_FORMULA + len(closing))
            end = text.find(closing, start, stop)
            while end >= 0 and text[end - 1] == "\\":
                end = text.find(closing, end + len(closing), stop)
            source = text[start:end] if end >= 0 else ""
            # Single dollars do not claim prices, whitespace, or paragraphs.
            valid = bool(source.strip())
            if opening == "$":
                valid = valid and not source[0].isspace() and not source[-1].isspace()
                valid = valid and not re.fullmatch(r"[\d,.]+", source) and "\n" not in source
                valid = valid and not (end + 1 < len(text) and text[end + 1].isdigit())
                if source and source[0].isdigit():
                    valid = valid and any(char in source for char in "^_+-=*/<>\\{}")
            if end >= 0 and valid:
                output.append(replace(source, opening in ("$$", r"\["), text[pos : end + len(closing)]))
                pos = end + len(closing)
                continue
        if text[pos] == "\\" and pos + 1 < len(text):
            output.append(text[pos : pos + 2])
            pos += 2
        else:
            output.append(text[pos])
            pos += 1
    return "".join(output)


def render_markdown(text: str) -> str:
    """Render safe HTML; math spans expose escaped ``data-tex`` and display mode.

    Raw HTML is displayed literally. Only text tokens can become math spans, so
    placeholders inside link/image attributes cannot inject generated HTML.
    Oversized input is returned as escaped preformatted text.
    """
    if len(text) > _MAX_INPUT:
        return "<pre>" + html.escape(text) + "</pre>"
    prefix = "NEOBOTMATH" + secrets.token_hex(16).upper()
    nodes: dict[str, str] = {}
    originals: dict[str, str] = {}

    def replace(source: str, display: bool, original: str) -> str:
        key = f"{prefix}N{len(nodes)}END"
        originals[key] = original
        nodes[key] = (
            f'<span class="neobot-math" data-display="{str(display).lower()}" '
            f'data-tex="{html.escape(source, quote=True)}">{html.escape(source)}</span>'
        )
        return key

    protected = _protect(text, replace)
    parser = MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")
    pattern = re.compile(re.escape(prefix) + r"N\d+END")

    def render_text(tokens, index, options, env):
        content = tokens[index].content
        pieces = []
        start = 0
        for match in pattern.finditer(content):
            pieces.append(html.escape(content[start : match.start()]))
            pieces.append(nodes.get(match[0], html.escape(match[0])))
            start = match.end()
        pieces.append(html.escape(content[start:]))
        return "".join(pieces)

    parser.renderer.rules["text"] = render_text
    # A screenshot renderer must not fetch user-controlled URLs or local files.
    parser.renderer.rules["image"] = lambda tokens, index, options, env: html.escape(tokens[index].content)
    rendered = parser.render(protected)
    # Markdown decides the context: placeholders in code, URLs, titles, and alt
    # text remain literal source. Escape again because these can be attributes.
    return pattern.sub(lambda match: html.escape(originals.get(match[0], match[0]), quote=True), rendered)


def pillowmd_source(text: str) -> str:
    """Keep all TeX literal; the fallback deliberately supports no TeX execution.

    Also neutralize unpaired/currency dollars outside recognized math: pillowmd
    has its own dollar parser and must never receive an unchecked expression.
    """

    def literal(source: str, display: bool, original: str) -> str:
        runs = re.findall(r"`+", source)
        if "\n" in source:
            fence = "`" * max(3, max(map(len, runs), default=0) + 1)
            return f"\n\n{fence}tex\n{source}\n{fence}\n\n"
        ticks = "`" * (max(map(len, runs), default=0) + 1)
        padding = " " if source.startswith("`") or source.endswith("`") else ""
        return f"{ticks}{padding}{source}{padding}{ticks}"

    if len(text) > _MAX_INPUT:
        raise ValueError(f"Markdown source exceeds {_MAX_INPUT} characters")
    return re.sub(r"(?<!\\)\$", r"\\$", _protect(text, literal))

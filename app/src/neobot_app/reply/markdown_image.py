"""Markdown 转图片转换器 —— 优先浏览器渲染，失败时回退到 pillowmd。

浏览器渲染的画布按**内容元素（article.markdown-body）自身高度**裁剪：
直接取 documentElement.scrollHeight 会被当前视口高度托底，短内容也会出成
「整屏高、下方大片空白」的图（同类缺陷与修法见 runtime/html_card.py 的卡片裁剪）。
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import pillowmd

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.screenshot import RenderOptions, ScreenshotOptions, ScreenshotPort

from neobot_app.reply.math_markdown import pillowmd_source, render_markdown

_MD_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  {css}
</style>
</head>
<body>
<article class="markdown-body">
{content}
</article>
<script>{katex_js}</script>
</body>
</html>"""

_MD_CSS = """\
html, body { margin: 0; padding: 0; background: #ffffff; }
.markdown-body {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 24px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  font-size: 15px;
  line-height: 1.6;
  color: #24292f;
  background-color: #ffffff;
  word-wrap: break-word;
}
.markdown-body h1 { font-size: 1.8em; border-bottom: 1px solid #d0d7de; padding-bottom: 0.3em; margin: 0.67em 0; }
.markdown-body h2 { font-size: 1.5em; border-bottom: 1px solid #d0d7de; padding-bottom: 0.3em; margin: 0.83em 0; }
.markdown-body h3 { font-size: 1.25em; margin: 1em 0; }
.markdown-body h4 { font-size: 1em; margin: 1.33em 0; }
.markdown-body p { margin: 0 0 16px; }
.markdown-body ul, .markdown-body ol { padding-left: 2em; margin: 0 0 16px; }
.markdown-body li { margin: 0.25em 0; }
.markdown-body blockquote {
  margin: 0 0 16px;
  padding: 0 1em;
  color: #57606a;
  border-left: 0.25em solid #d0d7de;
}
.markdown-body pre {
  background: #f6f8fa;
  border-radius: 6px;
  padding: 16px;
  overflow-x: auto;
  font-size: 85%;
  line-height: 1.45;
}
.markdown-body code {
  background: #f6f8fa;
  border-radius: 4px;
  padding: 0.2em 0.4em;
  font-family: "SF Mono", "Fira Code", "Fira Mono", "Menlo", Consolas, monospace;
  font-size: 85%;
}
.markdown-body pre code {
  background: none;
  padding: 0;
  border-radius: 0;
}
.markdown-body table {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 16px;
}
.markdown-body th, .markdown-body td {
  border: 1px solid #d0d7de;
  padding: 6px 13px;
  text-align: left;
}
.markdown-body th { background: #f6f8fa; font-weight: 600; }
.markdown-body tr:nth-child(even) { background: #f6f8fa; }
.markdown-body img { max-width: 100%; }
.markdown-body hr { border: none; border-top: 1px solid #d0d7de; margin: 24px 0; }
.markdown-body a { color: #0969da; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body { box-sizing: border-box; min-height: 200px; }
.neobot-math[data-display="true"] { display: block; margin: 1em 0; }
.markdown-body .katex-display { overflow: visible; }
.markdown-body pre { overflow: visible; white-space: pre-wrap; }
"""


@lru_cache(maxsize=1)
def _katex_resources() -> tuple[str, str]:
    """Embed vendored resources once; never fetch a network or file URL."""
    root = Path(__file__).parent / "assets" / "katex"
    css = (root / "katex.min.css").read_text(encoding="utf-8")

    def embed(match: re.Match[str]) -> str:
        name = match[1]
        suffix = Path(name).suffix[1:]
        mime = {"woff2": "font/woff2", "woff": "font/woff", "ttf": "font/ttf"}[suffix]
        data = base64.b64encode((root / name).read_bytes()).decode("ascii")
        return f"url(data:{mime};base64,{data})"

    css = re.sub(r"url\((fonts/[^)]+)\)", embed, css)
    return css, (root / "katex.min.js").read_text(encoding="utf-8")


# Application-authored code only. TeX comes from textContent, never JS interpolation.
_MATH_READY_SCRIPT = r"""
return (async () => {
  if (!window.katex) throw new Error('local KaTeX resources unavailable');
  const article = document.querySelector('article.markdown-body');
  for (const node of article.querySelectorAll('.neobot-math')) {
    const source = node.textContent;
    try {
      katex.render(source, node, {displayMode: node.dataset.display === 'true',
        trust: false, throwOnError: false, maxExpand: 1000, maxSize: 20,
        strict: 'error'});
    } catch (_) { node.textContent = source; }
  }
  await document.fonts.ready;
  const failed = Array.from(document.fonts).some(font => font.status === 'error');
  if (failed) throw new Error('local math font failed to load');
  // Expand the captured article to include unbreakable formulas, code and tables.
  let width = Math.max(article.getBoundingClientRect().width, article.scrollWidth);
  // KaTeX radicals use deliberately huge SVGs clipped inside narrow wrappers.
  // Only formula layout boxes count; measuring every descendant expands normal
  // square roots to thousands of pixels even though their visible ink is small.
  for (const child of article.querySelectorAll('.katex-html > .katex-base, .katex-html > .base, pre, table')) {
    width = Math.max(width, child.getBoundingClientRect().width + 48);
  }
  article.style.maxWidth = 'none';
  article.style.width = Math.ceil(width) + 'px';
  article.style.margin = '0';
  const box = article.getBoundingClientRect();
  if (box.width > 8192 || box.height > 8192 || box.width * box.height > 16000000)
    throw new Error('Markdown image dimensions exceed limit');
  return true;
})();
"""


#: 内容容器选择器：_MD_HTML_TEMPLATE 固定输出 <article class="markdown-body">
_CONTENT_SELECTOR = "article.markdown-body"
#: 量内容高度前先用的「探针视口高度」。
#:
#: 不能直接读 document.documentElement.scrollHeight：按 CSS 语义它**不会小于视口高度**
#: （scrollHeight ≥ clientHeight），浏览器窗口是 1280x800 时短内容也会量出 ~800px，
#: 出图于是变成「上面几行正文 + 下面一大片空白」，且文件体积翻倍
#: （同类缺陷见 commit a333286「卡片截图裁剪到元素盒」）。
#: 先把视口压到一个小高度再量内容元素自身，就绕开了这层托底。
_PROBE_VIEWPORT_HEIGHT = 320
#: 视口宽度相对内容宽度的余量（沿用既有 40px 语义）
_VIEWPORT_WIDTH_PADDING = 40


class MarkdownImageError(Exception):
    """Markdown 转图片失败。"""


class MarkdownImageConverter:
    """将 Markdown 文本渲染为 PNG 图片。

    支持两种渲染方式：
    1. 浏览器渲染（本地 KaTeX 数学排版）- 主方案
    2. pillowmd 渲染（无需浏览器）- 降级方案

    自动选择可用方案。
    """

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60  # 每 6 小时清理一次
    _TMP_MAX_AGE_SECONDS = 24 * 60 * 60  # 超过 24 小时的文件视为过期
    _CLEANUP_ALL_ON_STOP = True  # 关闭时删除所有文件
    _RENDER_TIMEOUT_SECONDS = 60  # 渲染总超时（防浏览器卡死挂起回复管线）

    def __init__(
        self,
        *,
        output_dir: Path,
        width: int = 800,
        browser_instance: Any = None,
        screenshots: ScreenshotPort | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._width = width
        if screenshots is None and browser_instance is not None:
            from neobot_app.browser import BrowserScreenshotBackend
            from neobot_app.screenshot import ScreenshotService

            screenshots = ScreenshotService(BrowserScreenshotBackend(browser_instance))
        self._screenshots = screenshots
        self._browser_available = screenshots is not None
        self._logger = logger or NullLogger()
        self._started = False
        self._style: pillowmd.MdStyle | None = None
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._style = pillowmd.MdStyle()
        self._style.xSizeMax = self._width
        self._started = True
        self._start_cleanup_task()
        mode = "浏览器 + pillowmd 降级" if self._browser_available else "pillowmd"
        self._logger.info(f"MarkdownImageConverter 已就绪（{mode} 渲染 + 定时清理）")

    async def stop(self) -> None:
        self._started = False
        await self._stop_cleanup_task()
        if self._CLEANUP_ALL_ON_STOP:
            self._cleanup_all()
        self._logger.info("MarkdownImageConverter 已停止")

    async def convert(
        self,
        markdown_text: str,
        *,
        filename: str | None = None,
        force_pillowmd: bool = False,
    ) -> Path:
        """将 markdown 文本转为图片并保存。返回图片 Path。

        Args:
            markdown_text: markdown 文本内容
            filename: 输出文件名（不含扩展名），默认使用内容哈希
            force_pillowmd: 强制使用 pillowmd 渲染，跳过浏览器
        """
        if not markdown_text.strip():
            raise MarkdownImageError("markdown 内容不能为空")

        if filename is None:
            content_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()[:16]
            filename = f"md_{content_hash}"

        if len(markdown_text) > 100000:
            raise MarkdownImageError("Markdown input exceeds limit (100000 characters)")
        html = render_markdown(markdown_text)
        if html.count('class="neobot-math"') > 512:
            raise MarkdownImageError("Markdown formula count exceeds limit (512)")
        async with asyncio.timeout(self._RENDER_TIMEOUT_SECONDS):
            if self._browser_available and not force_pillowmd:
                try:
                    return await self._render_with_browser(markdown_text, filename)
                except (TimeoutError, MarkdownImageError):
                    raise
                except Exception as exc:
                    self._logger.warning("浏览器渲染失败，降级到 pillowmd", error=str(exc))
            return await self._render_with_pillowmd(markdown_text, filename)

    # ── 浏览器渲染 ──

    async def _render_with_browser(self, markdown_text: str, filename: str) -> Path:
        """使用浏览器渲染 markdown → HTML → 截图。"""
        css, script = _katex_resources()
        full_html = _MD_HTML_TEMPLATE.format(
            css=_MD_CSS + css,
            content=render_markdown(markdown_text),
            katex_js=script,
        )
        target = self._output_dir / f"{filename}.png"
        assert self._screenshots is not None
        result = await self._screenshots.save(
            html=full_html,
            path=target,
            options=RenderOptions(
                screenshot=ScreenshotOptions(
                    mode="element",
                    selector=_CONTENT_SELECTOR,
                    width=self._width + _VIEWPORT_WIDTH_PADDING,
                    height=_PROBE_VIEWPORT_HEIGHT,
                    format="png",
                ),
                ready_script=_MATH_READY_SCRIPT,
                timeout=self._RENDER_TIMEOUT_SECONDS,
            ),
        )
        if result is not None and (
            result.width > 8192 or result.height > 8192 or result.width * result.height > 16000000
        ):
            target.unlink(missing_ok=True)
            raise MarkdownImageError("Markdown image dimensions exceed limit")
        return target

    # ── pillowmd 渲染 ──

    async def _render_with_pillowmd(self, markdown_text: str, filename: str) -> Path:
        """使用 pillowmd 渲染 markdown 为图片。"""
        # Bound the fallback before Pillow allocates a potentially enormous canvas.
        # Conservative wrapping estimate includes CJK and large heading glyphs.
        columns = max(1, self._width // 32)
        lines = sum(max(1, math.ceil(len(line) / columns)) for line in markdown_text.splitlines())
        if len(markdown_text) > 10000 or lines > 180:
            raise MarkdownImageError("Markdown fallback exceeds input/layout limit")
        # pillowmd resolves local image paths independently of its URL switch.
        # Its scanner differs from MarkdownIt; reject even ambiguous/code images
        # rather than letting a second parser read user-selected files.
        if "![" in markdown_text:
            raise MarkdownImageError("Markdown fallback does not support image sources")
        result = await pillowmd.MdToImage(
            text=pillowmd_source(markdown_text),
            style=self._style or pillowmd.MdStyle(),
        )

        output_path = self._output_dir / f"{filename}.png"
        try:
            width, height = result.image.size
            if width > 8192 or height > 8192 or width * height > 16000000:
                raise MarkdownImageError("Markdown image dimensions exceed limit")
            result.image.save(str(output_path), "PNG")
        finally:
            result.image.close()
        self._logger.info("Markdown pillowmd 渲染完成", path=str(output_path))
        return output_path

    # ----------------------------------------------------------------
    # cleanup
    # ----------------------------------------------------------------

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._CLEANUP_INTERVAL_SECONDS)
                self._cleanup_expired()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.warning("markdown 图片定时清理失败", error=str(exc))

    def _start_cleanup_task(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _stop_cleanup_task(self) -> None:
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

    def _cleanup_expired(self) -> None:
        """删除超过 _TMP_MAX_AGE_SECONDS 秒的图片文件。"""
        if not self._output_dir.exists():
            return
        cutoff = time.time() - self._TMP_MAX_AGE_SECONDS
        deleted = 0
        for child in self._output_dir.iterdir():
            if not child.is_file():
                continue
            if child.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".html"):
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                mtime = 0.0
            if mtime > cutoff:
                continue
            try:
                child.unlink()
                deleted += 1
            except OSError:
                pass
        if deleted:
            self._logger.info(
                "Markdown 图片过期清理完成",
                deleted=deleted,
                max_age_hours=self._TMP_MAX_AGE_SECONDS // 3600,
            )

    def _cleanup_all(self) -> None:
        """删除 output_dir 中所有图片/HTML 文件（关闭时调用）。"""
        if not self._output_dir.exists():
            return
        deleted = 0
        for child in self._output_dir.iterdir():
            if not child.is_file():
                continue
            try:
                child.unlink()
                deleted += 1
            except OSError:
                pass
        if deleted:
            self._logger.info("Markdown 图片全部清理完成", deleted=deleted)

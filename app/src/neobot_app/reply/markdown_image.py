"""Markdown to image converter - browser rendering with pillowmd fallback."""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import markdown as md_lib
import pillowmd

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    pass


_MD_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  {css}
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
</head>
<body>
<article class="markdown-body">
{content}
</article>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script>hljs.highlightAll();</script>
</body>
</html>"""

_MD_CSS = """\
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
"""


class MarkdownImageError(Exception):
    """Markdown 转图片失败。"""


class MarkdownImageConverter:
    """将 Markdown 文本渲染为 PNG 图片。

    支持两种渲染方式：
    1. 浏览器渲染（质量更高，支持代码高亮）- 主方案
    2. pillowmd 渲染（无需浏览器）- 降级方案

    自动选择可用方案。
    """

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60   # 每 6 小时清理一次
    _TMP_MAX_AGE_SECONDS = 24 * 60 * 60       # 超过 24 小时的文件视为过期
    _CLEANUP_ALL_ON_STOP = True                # 关闭时删除所有文件

    def __init__(
        self,
        *,
        output_dir: Path,
        width: int = 800,
        browser_instance: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._width = width
        self._browser = browser_instance
        self._browser_available = browser_instance is not None
        self._logger = logger or NullLogger()
        self._started = False
        self._style: pillowmd.MdStyle | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._render_lock = asyncio.Lock()

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

        if self._browser_available and not force_pillowmd:
            try:
                return await self._render_with_browser(markdown_text, filename)
            except Exception as exc:
                self._logger.warning("浏览器渲染失败，降级到 pillowmd", error=str(exc))

        return await self._render_with_pillowmd(markdown_text, filename)

    # ── 浏览器渲染 ──

    async def _render_with_browser(self, markdown_text: str, filename: str) -> Path:
        """使用浏览器渲染 markdown → HTML → 截图。"""
        html = md_lib.markdown(
            markdown_text,
            extensions=["fenced_code", "codehilite", "tables", "nl2br"],
        )

        full_html = _MD_HTML_TEMPLATE.format(css=_MD_CSS, content=html)
        html_path = self._output_dir / f"{filename}.html"
        html_path.write_text(full_html, encoding="utf-8")

        browser = self._browser
        async with self._render_lock:
            await browser.navigate(f"file:///{html_path.as_posix()}")
            await asyncio.sleep(0.3)

            # 获取页面内容高度，设置 viewport 以截取完整内容
            js_result = await browser.execute_js(
                "return Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, 200)"
            )
            height = 200
            if isinstance(js_result, dict):
                raw = js_result.get("result", js_result.get("data", 800))
                try:
                    height = int(float(str(raw)))
                except (ValueError, TypeError):
                    height = 800
            else:
                try:
                    height = int(float(str(js_result)))
                except (ValueError, TypeError):
                    height = 800

            height = min(max(height, 200), 8192)
            await browser.set_viewport(width=self._width + 40, height=height)

            result = await browser.shot(name=filename)
            if not isinstance(result, dict) or not result.get("success"):
                err = ""
                if isinstance(result, dict):
                    err = result.get("error", "")
                raise MarkdownImageError(f"浏览器截图失败: {err}")

            image_path_str = result.get("path", "")
            if not image_path_str:
                raise MarkdownImageError("浏览器截图未返回路径")
            image_path = Path(image_path_str)

            # 复制到标准输出目录
            target = self._output_dir / f"{filename}.png"
            if image_path != target:
                import shutil
                shutil.copy2(str(image_path), str(target))
                image_path = target

            self._logger.info("Markdown 浏览器渲染完成", path=str(image_path), height=height)
            return image_path

    # ── pillowmd 渲染 ──

    async def _render_with_pillowmd(self, markdown_text: str, filename: str) -> Path:
        """使用 pillowmd 渲染 markdown 为图片。"""
        result = await pillowmd.MdToImage(
            text=markdown_text,
            style=self._style,
        )

        output_path = self._output_dir / f"{filename}.png"
        result.image.save(str(output_path), "PNG")
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
            if not child.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".html"):
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

"""Markdown to image converter using Playwright for HTML rendering."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    from playwright.async_api import Browser


class MarkdownImageError(Exception):
    """Markdown 转图片失败。"""


class MarkdownImageConverter:
    """将 Markdown 文本渲染为 PNG 图片。

    采用两阶段转换: Markdown -> HTML -> 图片。
    """

    def __init__(
        self,
        *,
        output_dir: Path,
        width: int = 800,
        device_scale_factor: float = 2.0,
        logger: Logger | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._width = width
        self._device_scale_factor = device_scale_factor
        self._logger = logger or NullLogger()
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._started = False

    async def start(self) -> None:
        """启动 Playwright 浏览器实例。缺失时自动安装，失败时优雅降级。"""
        if self._started:
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self._logger.warning(
                "playwright 未安装，Markdown 转图片功能不可用。"
                "请运行: pip install playwright && playwright install chromium"
            )
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        try:
            exec_path = self._playwright.chromium.executable_path
            if exec_path and not Path(exec_path).exists():
                self._logger.info(
                    f"Chromium 浏览器不存在 ({exec_path})，尝试自动安装..."
                )
                if not await self._try_install_browser():
                    self._logger.warning(
                        "Chromium 自动安装失败，Markdown 转图片功能不可用"
                    )
                    return
            self._browser = await self._playwright.chromium.launch()
            self._started = True
            self._logger.info("MarkdownImageConverter 浏览器已启动")
        except Exception as exc:
            self._logger.warning(
                f"Chromium 浏览器启动失败，Markdown 转图片功能不可用: {exc}"
            )
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def _try_install_browser(self) -> bool:
        """尝试通过 playwright CLI 自动安装 Chromium。"""
        import subprocess
        import sys
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                timeout=300,  # 首次下载可能较慢，给 5 分钟
            )
            if result.returncode == 0:
                self._logger.info("Chromium 浏览器自动安装成功")
                return True
            else:
                stderr_text = result.stderr.decode(errors="replace")[:500] if result.stderr else ""
                self._logger.warning(
                    f"playwright install chromium 返回非零退出码 {result.returncode}: "
                    f"{stderr_text}"
                )
                return False
        except Exception as exc:
            self._logger.warning(f"自动安装 Chromium 失败: {exc}")
            return False

    async def stop(self) -> None:
        """关闭浏览器实例。"""
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._started = False
        self._logger.info("MarkdownImageConverter 已关闭")

    async def convert(
        self,
        markdown_text: str,
        *,
        filename: str | None = None,
    ) -> Path:
        """将 markdown 文本转为图片并保存。返回图片的 Path 对象。"""
        if not self._started or self._browser is None:
            raise MarkdownImageError("MarkdownImageConverter 未启动，请先调用 start()")

        if not markdown_text.strip():
            raise MarkdownImageError("markdown 内容不能为空")

        html = self._markdown_to_html(markdown_text)
        full_html = self._build_html_template(html)

        if filename is None:
            content_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()[:16]
            filename = f"md_{content_hash}"

        output_path = self._output_dir / f"{filename}.png"

        page = await self._browser.new_page(
            viewport={"width": self._width, "height": 600},
            device_scale_factor=self._device_scale_factor,
        )
        try:
            await page.set_content(full_html, wait_until="networkidle")
            # 获取内容实际高度用于截图
            body_height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({
                "width": self._width,
                "height": max(body_height, 600),
            })
            await page.screenshot(
                path=str(output_path),
                full_page=True,
                type="png",
            )
        finally:
            await page.close()

        self._logger.info("Markdown 转图片完成", path=str(output_path))
        return output_path

    async def convert_to_data_uri(self, markdown_text: str) -> str:
        """将 markdown 转为图片并返回 base64 data URI。"""
        import base64
        path = await self.convert(markdown_text)
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/png;base64,{b64}"

    def _markdown_to_html(self, text: str) -> str:
        try:
            import markdown as md_lib
            return md_lib.markdown(
                text,
                extensions=["fenced_code", "codehilite", "tables", "toc"],
            )
        except ImportError:
            raise MarkdownImageError(
                "markdown 库未安装，请运行: pip install markdown pygments"
            )

    def _build_html_template(self, body_html: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif;
    font-size: 16px;
    line-height: 1.7;
    color: #1a1a1a;
    background: #ffffff;
    padding: 32px 40px;
    max-width: {self._width}px;
    word-wrap: break-word;
  }}
  h1 {{ font-size: 1.8em; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid #e8e8e8; padding-bottom: 6px; }}
  h3 {{ font-size: 1.3em; }}
  h4 {{ font-size: 1.1em; }}
  code {{
    background: #f5f5f5;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 0.9em;
  }}
  pre {{
    background: #f8f8f8;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 16px;
    overflow-x: auto;
    line-height: 1.5;
  }}
  pre code {{
    background: none;
    padding: 0;
    font-size: 0.85em;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
  }}
  th, td {{
    border: 1px solid #d0d0d0;
    padding: 8px 12px;
    text-align: left;
  }}
  th {{
    background: #f0f0f0;
    font-weight: 600;
  }}
  blockquote {{
    border-left: 4px solid #c0c0c0;
    padding-left: 16px;
    margin-left: 0;
    color: #555;
  }}
  img {{ max-width: 100%; }}
  ul, ol {{ padding-left: 24px; }}
  li {{ margin: 4px 0; }}
  hr {{ border: none; border-top: 1px solid #e0e0e0; margin: 20px 0; }}
  a {{ color: #1a6fb5; }}
  .codehilite .hll {{ background-color: #ffffcc }}
  .codehilite .c {{ color: #888888 }}
  .codehilite .k {{ color: #008800; font-weight: bold }}
  .codehilite .s {{ color: #dd2200 }}
  .codehilite .n {{ color: #333333 }}
  .codehilite .o {{ color: #333333 }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""

"""HTML screenshot rendering using NeoBot's existing Chromium browser.

公共 DTO / 错误 / Port 契约定义在 neobot_contracts.ports.screenshot，
本模块负责再导出（保持向后兼容）并持有实现（校验、HTML 准备、
ScreenshotService / 不可用占位实现）。
"""

from __future__ import annotations

import asyncio
import base64
import html as html_module
import os
import re
import sys
import tempfile
from dataclasses import replace
from numbers import Real
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from neobot_contracts.ports.screenshot import (
    FontFace,
    FontFormat,
    FontLoadError,
    ImageFormat,
    InvalidScreenshotOptions,
    RenderOptions,
    ScreenshotError,
    ScreenshotMode,
    ScreenshotOptions,
    ScreenshotPort,
    ScreenshotResult,
    ScreenshotTargetNotFound,
    ScreenshotTimeout,
    ScreenshotUnavailable,
    _FONT_FORMATS,
    validate_screenshot_options,
)

if TYPE_CHECKING:
    from neobot_app.browser.agent_browser.manager import BrowserManager

__all__ = [
    "FontFace",
    "FontFormat",
    "FontLoadError",
    "ImageFormat",
    "InvalidScreenshotOptions",
    "RenderOptions",
    "ScreenshotError",
    "ScreenshotMode",
    "ScreenshotOptions",
    "ScreenshotPort",
    "ScreenshotResult",
    "ScreenshotService",
    "ScreenshotTargetNotFound",
    "ScreenshotTimeout",
    "ScreenshotUnavailable",
    "UnavailableScreenshots",
    "validate_screenshot_options",
]

_EXTENSIONS = {"png": {".png"}, "jpeg": {".jpg", ".jpeg"}, "webp": {".webp"}}
_FONT_MIME_TYPES = {
    "woff2": "font/woff2",
    "woff": "font/woff",
    "truetype": "font/ttf",
    "opentype": "font/otf",
}
_FONT_WEIGHT = re.compile(
    r"(?:normal|bold|(?:[1-9]\d{0,2}|1000)(?:\s+(?:[1-9]\d{0,2}|1000))?)"
)


class _ScreenshotBackend(Protocol):
    """ScreenshotService 内部后端：懒解析具体 BrowserManager 并提供共享锁。

    实现位于 neobot_app.browser（BrowserScreenshotBackend），
    测试可直接用 _DirectManagerBackend 包装一个 BrowserManager。
    """

    @property
    def operation_lock(self) -> asyncio.Lock: ...

    async def get_manager(self) -> "BrowserManager": ...


class _DirectManagerBackend:
    """内部适配：直接包装一个 BrowserManager（复用其私有 operation_lock）。"""

    def __init__(self, manager: "BrowserManager") -> None:
        self._manager = manager

    @property
    def operation_lock(self) -> asyncio.Lock:
        return self._manager._operation_lock

    async def get_manager(self) -> "BrowserManager":
        return self._manager


def _looks_like_browser_startup_failure(exc: BaseException) -> bool:
    """判断异常是否属于"浏览器不可用/启动失败"（用于映射为 ScreenshotUnavailable）。"""
    message = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "browserconnect",
        "pageunreachable",
        "disconnected",
        "nosuchfile",
        "filenotfound",
        "connectionrefused",
        "not installed",
        "not found",
        "找不到",
        "未安装",
        "无法启动",
        "启动失败",
        "连接失败",
        "chrome",
        "chromium",
        "playwright",
        "executable",
        "binary",
    )
    return any(marker in message for marker in markers)


def _css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _font_css(fonts: tuple[FontFace, ...], default_font: str | None) -> tuple[str, tuple[str, ...]]:
    if default_font is not None and (
        not isinstance(default_font, str) or not default_font.strip()
    ):
        raise InvalidScreenshotOptions("default_font must not be empty")
    rules: list[str] = []
    families: list[str] = []
    for font in fonts:
        if not isinstance(font.family, str):
            raise FontLoadError("font family must be a string")
        family = font.family.strip()
        if not family:
            raise FontLoadError("font family must not be empty")
        if not isinstance(font.format, str) or font.format not in _FONT_FORMATS:
            raise FontLoadError(f"unsupported font format: {font.format}")
        if not isinstance(font.weight, str) or not _FONT_WEIGHT.fullmatch(font.weight):
            raise FontLoadError(f"invalid font weight for {family!r}: {font.weight!r}")
        weight_parts = font.weight.split()
        if len(weight_parts) == 2 and int(weight_parts[0]) > int(weight_parts[1]):
            raise FontLoadError(f"invalid font weight range for {family!r}: {font.weight!r}")
        if not isinstance(font.style, str) or font.style not in {"normal", "italic", "oblique"}:
            raise FontLoadError(f"invalid font style for {family!r}: {font.style!r}")
        if isinstance(font.source, Path):
            try:
                data = font.source.read_bytes()
            except OSError as exc:
                raise FontLoadError(f"could not read font: {font.source}") from exc
        elif isinstance(font.source, bytes):
            data = font.source
        else:
            raise FontLoadError("font source must be a Path or bytes")
        if not data:
            raise FontLoadError(f"font source for {family!r} is empty")
        encoded = base64.b64encode(data).decode("ascii")
        rules.append(
            "@font-face{"
            f"font-family:{_css_string(family)};"
            f"src:url(data:{_FONT_MIME_TYPES[font.format]};base64,{encoded}) "
            f"format({_css_string(font.format)});"
            f"font-weight:{font.weight};font-style:{font.style};"
            "}"
        )
        families.append(family)
    if default_font is not None:
        rules.append(f"html,body{{font-family:{_css_string(default_font.strip())};}}")
    return "".join(rules), tuple(families)


def _prepare_html(source: str, css: str, base_url: str | None) -> str:
    additions = ""
    if base_url is not None:
        additions += f'<base href="{html_module.escape(base_url, quote=True)}">'
    if css:
        additions += f"<style>{css}</style>"
    head = re.search(r"<head(?:\s[^>]*)?>", source, flags=re.IGNORECASE)
    if head:
        return source[: head.end()] + additions + source[head.end() :]
    return f"<head>{additions}</head>{source}"


class ScreenshotService:
    """渲染 HTML 到由后端懒解析的 BrowserManager 所拥有的隔离标签页。

    公共截图 façade（application.screenshots / ctx.screenshots 的实现）。
    整个 open/render/capture/restore/close 序列持有共享 operation_lock，
    与浏览器技能调用串行化。
    """

    def __init__(self, backend: _ScreenshotBackend) -> None:
        self._backend = backend

    async def render(
        self,
        *,
        html: str,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult:
        validate_screenshot_options(options.screenshot)
        if (
            isinstance(options.timeout, bool)
            or not isinstance(options.timeout, Real)
            or options.timeout <= 0
        ):
            raise InvalidScreenshotOptions("timeout must be greater than zero")
        async with self._backend.operation_lock:
            return await self._render_locked(
                html=html, options=options, base_url=base_url
            )

    async def _render_locked(
        self,
        *,
        html: str,
        options: RenderOptions,
        base_url: str | None,
    ) -> ScreenshotResult:
        browser = await self._acquire_browser()
        css, _ = _font_css(options.fonts, options.default_font)
        document = _prepare_html(html, css, base_url)
        original = temporary = None
        metrics_state = None
        try:
            async with asyncio.timeout(options.timeout):
                original, temporary = await browser._open_temporary_page()
                metrics_state = await browser._apply_temporary_capture_metrics(
                    options.screenshot
                )
                frame_tree = await asyncio.to_thread(
                    temporary.run_cdp, "Page.getFrameTree"
                )
                frame_id = frame_tree["frameTree"]["frame"]["id"]
                await asyncio.to_thread(
                    temporary.run_cdp,
                    "Page.setDocumentContent",
                    frameId=frame_id,
                    html=document,
                )
                verified_fonts = await self._wait_for_resources(temporary, options)
                result = await browser.capture(options.screenshot)
                return replace(result, fonts=verified_fonts)
        except TimeoutError as exc:
            raise ScreenshotTimeout(
                f"screenshot rendering timed out after {options.timeout:g} seconds"
            ) from exc
        except ScreenshotError:
            raise
        except Exception as exc:
            raise ScreenshotError("failed to render screenshot") from exc
        finally:
            cleanup_error: Exception | None = None
            if metrics_state is not None:
                try:
                    await browser._restore_temporary_capture_metrics(metrics_state)
                except Exception as exc:
                    cleanup_error = exc
            if temporary is not None:
                try:
                    await browser._close_temporary_page(temporary, original)
                except Exception as exc:
                    if cleanup_error is None:
                        cleanup_error = exc
            if cleanup_error is not None and sys.exc_info()[0] is None:
                raise ScreenshotError(
                    "failed to close the screenshot tab and restore browser state"
                ) from cleanup_error

    async def _acquire_browser(self) -> "BrowserManager":
        """获取 BrowserManager，将启动/不可用异常翻译为 Port 错误。

        浏览器获取与启动可能抛出裸的 DrissionPage / 文件系统异常，
        这里统一收敛为 ScreenshotUnavailable（启动失败类）或
        ScreenshotError（其他），绝不向调用方泄漏原始异常。
        """
        try:
            return await self._backend.get_manager()
        except ScreenshotError:
            raise
        except Exception as exc:
            if _looks_like_browser_startup_failure(exc):
                raise ScreenshotUnavailable(
                    f"browser is not available: {exc}"
                ) from exc
            raise ScreenshotError(
                "failed to acquire browser for screenshot"
            ) from exc

    async def _wait_for_resources(
        self, page: object, options: RenderOptions
    ) -> tuple[str, ...]:
        verified_fonts: tuple[str, ...] = ()
        if options.wait_for_fonts:
            try:
                await asyncio.to_thread(
                    page.run_js,
                    "return document.fonts.ready.then(() => true)",
                )
                font_specs = [
                    f"{font.style} {font.weight.split()[0]} 16px "
                    f"{_css_string(font.family.strip())}"
                    for font in options.fonts
                ]
                loaded = []
                for spec in font_specs:
                    is_loaded = await asyncio.to_thread(
                        page.run_js,
                        """const spec = arguments[0];
                        return document.fonts.load(spec)
                            .then(() => document.fonts.check(spec))
                            .catch(() => false)""",
                        spec,
                    )
                    loaded.append(bool(is_loaded))
            except Exception as exc:
                raise FontLoadError("failed while waiting for document fonts") from exc
            failed = [
                font.family.strip()
                for font, is_loaded in zip(options.fonts, loaded, strict=False)
                if not is_loaded
            ]
            if len(loaded) != len(options.fonts):
                failed.extend(
                    font.family.strip() for font in options.fonts[len(loaded) :]
                )
            if failed:
                raise FontLoadError(
                    "caller-provided fonts failed to load: " + ", ".join(failed)
                )
            verified_fonts = tuple(font.family.strip() for font in options.fonts)
        if options.wait_for_images:
            await asyncio.to_thread(
                page.run_js,
                """return Promise.all(Array.from(document.images, image => {
                    if (image.complete) return true;
                    return new Promise(resolve => {
                        image.addEventListener('load', () => resolve(true), {once:true});
                        image.addEventListener('error', () => resolve(false), {once:true});
                    });
                })).then(() => true)""",
            )
        return verified_fonts

    async def save(
        self,
        *,
        html: str,
        path: str | Path,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult:
        validate_screenshot_options(options.screenshot)
        target = Path(path)
        expected = _EXTENSIONS.get(options.screenshot.format, set())
        if target.suffix.lower() not in expected:
            allowed = ", ".join(sorted(expected))
            raise InvalidScreenshotOptions(
                f"{options.screenshot.format} output path must use: {allowed}"
            )
        result = await self.render(html=html, options=options, base_url=base_url)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temporary_path = Path(output.name)
                output.write(result.data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return replace(result, path=target)


class UnavailableScreenshots:
    """浏览器未启用 / Chromium 不可用时的截图占位实现。

    属性始终存在（application.screenshots / ctx.screenshots 永不为 None），
    调用 render/save 时抛出 ScreenshotUnavailable。
    """

    _MESSAGE = "浏览器未启用或 Chromium 不可用，无法截图"

    async def render(
        self,
        *,
        html: str,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult:
        raise ScreenshotUnavailable(self._MESSAGE)

    async def save(
        self,
        *,
        html: str,
        path: str | Path,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult:
        raise ScreenshotUnavailable(self._MESSAGE)

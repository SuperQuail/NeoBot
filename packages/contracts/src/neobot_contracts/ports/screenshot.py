"""Screenshot Ports — 截图公共契约（DTO / 错误 / Port 接口）。

本模块只包含契约，不依赖任何浏览器实现：
- 应用代码可通过 application.screenshots 使用
- 插件可通过 ctx.screenshots / neobot_modloader 的再导出使用
"""

from __future__ import annotations

from numbers import Real
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from dataclasses import dataclass

ScreenshotMode = Literal["viewport", "full_page", "element"]
ImageFormat = Literal["png", "jpeg", "webp"]
FontFormat = Literal["woff2", "woff", "truetype", "opentype"]

# 允许值集合从 Literal 别名派生，避免与 DTO 定义漂移。
_MODES = set(ScreenshotMode.__args__)
_IMAGE_FORMATS = set(ImageFormat.__args__)
_FONT_FORMATS = set(FontFormat.__args__)


class ScreenshotError(Exception):
    """截图操作的基础错误。"""


class ScreenshotUnavailable(ScreenshotError):
    """浏览器未启用或 Chromium 不可用，截图功能不可用。"""


class InvalidScreenshotOptions(ScreenshotError, ValueError):
    """截图或渲染选项无效。"""


class ScreenshotTargetNotFound(ScreenshotError):
    """请求截图的元素不存在或没有可见区域。"""


class ScreenshotTimeout(ScreenshotError, TimeoutError):
    """渲染未在配置的超时时间内完成。"""


class FontLoadError(ScreenshotError):
    """调用方提供的字体无法读取或加载。"""


@dataclass(frozen=True, slots=True)
class FontFace:
    family: str
    source: Path | bytes
    format: FontFormat = "woff2"
    weight: str = "400"
    style: str = "normal"


@dataclass(frozen=True, slots=True)
class ScreenshotOptions:
    mode: ScreenshotMode = "viewport"
    selector: str | None = None
    width: int | None = None
    height: int | None = None
    scale: float = 1.0
    format: ImageFormat = "png"
    quality: int = 90
    transparent: bool = False


@dataclass(frozen=True, slots=True)
class RenderOptions:
    screenshot: ScreenshotOptions
    fonts: tuple[FontFace, ...] = ()
    default_font: str | None = None
    wait_for_fonts: bool = True
    wait_for_images: bool = True
    timeout: float = 30.0


@dataclass(frozen=True, slots=True)
class ScreenshotResult:
    data: bytes
    format: ImageFormat
    width: int
    height: int
    css_width: float
    css_height: float
    scale: float
    path: Path | None = None
    fonts: tuple[str, ...] = ()


def validate_screenshot_options(options: ScreenshotOptions) -> None:
    """校验 ScreenshotOptions，非法时抛出 InvalidScreenshotOptions。"""
    if not isinstance(options.mode, str) or options.mode not in _MODES:
        raise InvalidScreenshotOptions(f"unsupported screenshot mode: {options.mode}")
    if not isinstance(options.format, str) or options.format not in _IMAGE_FORMATS:
        raise InvalidScreenshotOptions(f"unsupported image format: {options.format}")
    if options.mode == "element":
        if not isinstance(options.selector, str) or not options.selector.strip():
            raise InvalidScreenshotOptions("element mode requires a non-empty selector")
    elif options.selector is not None:
        raise InvalidScreenshotOptions("selector is only valid in element mode")
    if (options.width is None) != (options.height is None):
        raise InvalidScreenshotOptions("width and height must be provided together")
    for name, value in (("width", options.width), ("height", options.height)):
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 16384
        ):
            raise InvalidScreenshotOptions(f"{name} must be between 1 and 16384")
    if (
        isinstance(options.scale, bool)
        or not isinstance(options.scale, Real)
        or not 0.25 <= options.scale <= 4
    ):
        raise InvalidScreenshotOptions("scale must be between 0.25 and 4")
    if (
        isinstance(options.quality, bool)
        or not isinstance(options.quality, int)
        or not 1 <= options.quality <= 100
    ):
        raise InvalidScreenshotOptions("quality must be between 1 and 100")
    if not isinstance(options.transparent, bool):
        raise InvalidScreenshotOptions("transparent must be a boolean")
    if options.transparent and options.format == "jpeg":
        raise InvalidScreenshotOptions("transparent screenshots cannot use JPEG")


@runtime_checkable
class ScreenshotPort(Protocol):
    """截图功能对外暴露的 Port 接口。"""

    async def render(
        self,
        *,
        html: str,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult: ...

    async def save(
        self,
        *,
        html: str,
        path: str | Path,
        options: RenderOptions,
        base_url: str | None = None,
    ) -> ScreenshotResult: ...


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
    "ScreenshotTargetNotFound",
    "ScreenshotTimeout",
    "ScreenshotUnavailable",
    "validate_screenshot_options",
]

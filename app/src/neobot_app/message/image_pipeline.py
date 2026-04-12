"""Utilities for preparing images before prompt assembly."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import math
import mimetypes
from pathlib import Path
from typing import Optional

from PIL import Image, UnidentifiedImageError

from neobot_contracts.models.memory import ImageAnalysis
from neobot_memory import ImageAnalysisService

DEFAULT_MAX_IMAGE_PIXELS = 1024 * 1024


class ImagePreparationError(ValueError):
    """Raised when a local image cannot be prepared."""


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """Prepared image payload ready for a future vision-model request."""

    source_path: Path
    file_hash: str
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    mime_type: str
    format_name: str
    image_bytes: bytes
    was_resized: bool


@dataclass(frozen=True, slots=True)
class ImagePromptResolution:
    """Result of resolving a local image against the cache."""

    prepared: PreparedImage
    cached_analysis: Optional[ImageAnalysis]

    @property
    def cache_hit(self) -> bool:
        return self.cached_analysis is not None and bool(self.cached_analysis.analysis_text)

    @property
    def prompt_text(self) -> Optional[str]:
        if self.cached_analysis is None:
            return None
        return self.cached_analysis.analysis_text


class ImagePromptPreparer:
    """Prepare local images and reuse cached analysis results when available."""

    def __init__(
        self,
        image_analysis_service: ImageAnalysisService,
        *,
        max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> None:
        if max_pixels <= 0:
            raise ValueError("max_pixels must be greater than 0")
        self._image_analysis_service = image_analysis_service
        self._max_pixels = max_pixels

    async def resolve_local_image(self, image_path: str | Path) -> ImagePromptResolution:
        prepared = prepare_local_image(image_path, max_pixels=self._max_pixels)
        cached = await self._image_analysis_service.get(prepared.file_hash)
        return ImagePromptResolution(prepared=prepared, cached_analysis=cached)

    async def save_analysis(self, prepared: PreparedImage, analysis_text: str) -> ImageAnalysis:
        return await self._image_analysis_service.set(
            prepared.file_hash,
            source=str(prepared.source_path),
            mime_type=prepared.mime_type,
            original_width=prepared.original_width,
            original_height=prepared.original_height,
            processed_width=prepared.processed_width,
            processed_height=prepared.processed_height,
            analysis_text=analysis_text,
        )


def prepare_local_image(image_path: str | Path, *, max_pixels: int = DEFAULT_MAX_IMAGE_PIXELS) -> PreparedImage:
    """Read a local image, hash it, and downscale proportionally if needed."""
    if max_pixels <= 0:
        raise ValueError("max_pixels must be greater than 0")

    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise ImagePreparationError(f"image does not exist: {path}")
    if not path.is_file():
        raise ImagePreparationError(f"image path is not a file: {path}")

    raw_bytes = path.read_bytes()
    file_hash = hashlib.sha256(raw_bytes).hexdigest()

    try:
        with Image.open(path) as image:
            image.load()
            format_name = (image.format or "PNG").upper()
            original_width, original_height = image.size
            processed_width, processed_height = _scaled_dimensions(
                original_width,
                original_height,
                max_pixels=max_pixels,
            )
            was_resized = (processed_width, processed_height) != (original_width, original_height)

            if was_resized:
                image = image.resize((processed_width, processed_height), Image.Resampling.LANCZOS)

            save_format = _normalized_output_format(format_name)
            if save_format == "JPEG" and image.mode not in ("RGB", "L"):
                image = image.convert("RGB")

            buffer = BytesIO()
            save_kwargs = {"format": save_format}
            if save_format == "JPEG":
                save_kwargs["quality"] = 95
                save_kwargs["optimize"] = True
            image.save(buffer, **save_kwargs)

    except UnidentifiedImageError as exc:
        raise ImagePreparationError(f"unsupported image file: {path}") from exc

    mime_type = Image.MIME.get(save_format) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return PreparedImage(
        source_path=path,
        file_hash=file_hash,
        original_width=original_width,
        original_height=original_height,
        processed_width=processed_width,
        processed_height=processed_height,
        mime_type=mime_type,
        format_name=save_format,
        image_bytes=buffer.getvalue(),
        was_resized=was_resized,
    )


def _scaled_dimensions(width: int, height: int, *, max_pixels: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ImagePreparationError("image dimensions must be positive")

    total_pixels = width * height
    if total_pixels <= max_pixels:
        return width, height

    scale = math.sqrt(max_pixels / total_pixels)
    scaled_width = max(1, int(width * scale))
    scaled_height = max(1, int(height * scale))

    while scaled_width * scaled_height > max_pixels:
        if scaled_width >= scaled_height and scaled_width > 1:
            scaled_width -= 1
        elif scaled_height > 1:
            scaled_height -= 1
        else:
            break

    return scaled_width, scaled_height


def _normalized_output_format(format_name: str) -> str:
    normalized = format_name.upper()
    if normalized in {"JPEG", "PNG", "WEBP", "GIF", "BMP"}:
        return normalized
    if normalized == "JPG":
        return "JPEG"
    return "PNG"

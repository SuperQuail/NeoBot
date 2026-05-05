"""Markdown to image converter using pillowmd."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pillowmd

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    pass


class MarkdownImageError(Exception):
    """Markdown 转图片失败。"""


class MarkdownImageConverter:
    """将 Markdown 文本渲染为 PNG 图片（基于 pillowmd）。"""

    def __init__(
        self,
        *,
        output_dir: Path,
        width: int = 800,
        logger: Logger | None = None,
    ) -> None:
        self._output_dir = output_dir
        self._width = width
        self._logger = logger or NullLogger()
        self._started = False
        self._style: pillowmd.MdStyle | None = None

    async def start(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._style = pillowmd.MdStyle()
        self._style.xSizeMax = self._width
        self._started = True
        self._logger.info("MarkdownImageConverter 已就绪（pillowmd 渲染）")

    async def stop(self) -> None:
        self._started = False

    async def convert(
        self,
        markdown_text: str,
        *,
        filename: str | None = None,
    ) -> Path:
        """将 markdown 文本转为图片并保存。返回图片 Path。"""
        if not markdown_text.strip():
            raise MarkdownImageError("markdown 内容不能为空")

        result = await pillowmd.MdToImage(
            text=markdown_text,
            style=self._style,
        )

        if filename is None:
            content_hash = hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()[:16]
            filename = f"md_{content_hash}"

        output_path = self._output_dir / f"{filename}.png"
        result.image.save(str(output_path), "PNG")
        self._logger.info("Markdown 转图片完成", path=str(output_path))
        return output_path

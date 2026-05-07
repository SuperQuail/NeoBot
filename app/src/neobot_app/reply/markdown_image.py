"""Markdown to image converter using pillowmd."""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pillowmd

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    pass


class MarkdownImageError(Exception):
    """Markdown 转图片失败。"""


class MarkdownImageConverter:
    """将 Markdown 文本渲染为 PNG 图片（基于 pillowmd）。

    生成的图片为临时文件，启动时自动清理过期文件（>24h），
    关闭时删除所有已生成的图片。
    """

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60   # 每 6 小时清理一次
    _TMP_MAX_AGE_SECONDS = 24 * 60 * 60       # 超过 24 小时的文件视为过期
    _CLEANUP_ALL_ON_STOP = True                # 关闭时删除所有文件

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
        self._cleanup_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._style = pillowmd.MdStyle()
        self._style.xSizeMax = self._width
        self._started = True
        self._start_cleanup_task()
        self._logger.info("MarkdownImageConverter 已就绪（pillowmd 渲染 + 定时清理）")

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
            if not child.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
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
                "markdown 图片过期清理完成",
                deleted=deleted,
                max_age_hours=self._TMP_MAX_AGE_SECONDS // 3600,
            )

    def _cleanup_all(self) -> None:
        """删除 output_dir 中所有图片文件（关闭时调用）。"""
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
            self._logger.info("markdown 图片全部清理完成", deleted=deleted)

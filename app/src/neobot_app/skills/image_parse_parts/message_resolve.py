"""按消息 ID 解析图片（单张/多张）。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS

class MessageResolveMixin:

    # ── 图片来源解析 ──

    async def _fetch_segments_by_message_id(self, message_id: int) -> list | None:
        """通过消息 ID 拉取消息并返回其 message segments（供多图复用避免多次请求 API）。"""
        if self._adapter is None:
            return None
        try:
            response = await asyncio.wait_for(
                self._adapter.get_msg(message_id), timeout=10,
            )
            data = getattr(response, "data", None)
        except Exception:
            try:
                result = await self._adapter.call_api("get_msg", {"message_id": message_id})
                if not result:
                    return None
                data = result.get("data", {}) if isinstance(result, dict) else None
            except Exception:
                return None

        if data is None:
            return None

        if hasattr(data, "message"):
            return data.message
        if isinstance(data, dict):
            return data.get("message")
        return None

    @staticmethod
    def _segment_type(segment: Any) -> str:
        """统一读取 dict / Pydantic / Enum 消息段类型。"""
        value = (
            segment.get("type")
            if isinstance(segment, dict)
            else getattr(segment, "type", None)
        )
        value = getattr(value, "value", value)
        return str(value or "")

    @classmethod
    def _image_count(cls, segments: list | None) -> int:
        return sum(
            1
            for segment in segments or []
            if cls._segment_type(segment) in ("image", "cardimage")
        )

    @classmethod
    def _may_be_auto_parsed_image(cls, segments: list | None) -> bool:
        """识别已被自动解析服务替换成描述文本的图片段。"""
        for segment in segments or []:
            if cls._segment_type(segment) != "text":
                continue
            data = (
                segment.get("data", {})
                if isinstance(segment, dict)
                else getattr(segment, "data", None)
            )
            text = str(cls._seg_data_to_dict(data).get("text") or "")
            if text.startswith("[图片"):
                return True
        return False

    async def _resolve_by_message_id_with_error(
        self,
        message_id: int,
        image_index: int = 0,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> tuple[bytes | None, str | None]:
        """通过 Adapter 回源消息，并返回第 N 张图片及具体失败原因。"""
        segments = await self._fetch_segments_by_message_id(message_id)
        if segments is None:
            return None, f"Adapter 无法获取消息 {message_id}"
        if not segments:
            return None, f"消息 {message_id} 没有可解析的内容段"
        return await self._download_from_segments_with_error(
            segments,
            image_index,
            timeout=timeout,
        )

    async def _resolve_by_message_id(
        self,
        message_id: int,
        image_index: int = 0,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> bytes | None:
        """通过消息 ID 获取第 N 张图片的字节。"""
        result, _ = await self._resolve_by_message_id_with_error(
            message_id,
            image_index,
            timeout=timeout,
        )
        return result

    async def _resolve_many_by_message_id_with_errors(
        self,
        message_id: int,
        image_indices: list[int],
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> list[tuple[bytes | None, str | None]]:
        """通过消息 ID 一次回源多张图片，并保留每张图的失败原因。"""
        segments = await self._fetch_segments_by_message_id(message_id)
        if segments is None:
            reason = f"Adapter 无法获取消息 {message_id}"
            return [(None, reason) for _ in image_indices]
        if not segments:
            reason = f"消息 {message_id} 没有可解析的内容段"
            return [(None, reason) for _ in image_indices]
        return [
            await self._download_from_segments_with_error(
                segments,
                index,
                timeout=timeout,
            )
            for index in image_indices
        ]

    async def _resolve_many_by_message_id(
        self,
        message_id: int,
        image_indices: list[int],
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> list[bytes | None]:
        """通过消息 ID 一次性获取多张图片字节（一次 API 调用，多次下载）。"""
        results = await self._resolve_many_by_message_id_with_errors(
            message_id,
            image_indices,
            timeout=timeout,
        )
        return [result for result, _ in results]

    async def _download_from_segments_with_error(
        self,
        segments: list,
        image_index: int = 0,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> tuple[bytes | None, str | None]:
        """从 segments 中下载指定图片，并返回可用于诊断的错误。"""
        if image_index < 0:
            return None, f"图片编号不能为负数: {image_index}"
        if not segments:
            return None, "消息中没有可解析的内容段"

        image_segments = [
            segment
            for segment in segments
            if self._segment_type(segment) in ("image", "cardimage")
        ]
        if image_index >= len(image_segments):
            return (
                None,
                f"消息中找不到第 {image_index} 张图片"
                f"（图片总数 {len(image_segments)}）",
            )

        segment = image_segments[image_index]
        data = (
            segment.get("data", {})
            if isinstance(segment, dict)
            else getattr(segment, "data", None)
        )
        return await self._download_image_segment(
            self._seg_data_to_dict(data),
            timeout=timeout,
        )

    async def _download_from_segments(
        self,
        segments: list,
        image_index: int = 0,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> bytes | None:
        """从 segments 列表中找第 image_index 张图片并下载。"""
        result, _ = await self._download_from_segments_with_error(
            segments,
            image_index,
            timeout=timeout,
        )
        return result

"""消息 segment 的规整与取图。"""

from __future__ import annotations

from typing import Any

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS

class SegmentMixin:

    @staticmethod
    def _seg_data_to_dict(seg_data: Any) -> dict:
        """将 segment.data 转为 dict，兼容 dict / pydantic 模型。"""
        if isinstance(seg_data, dict):
            return seg_data
        if hasattr(seg_data, "model_dump"):
            return seg_data.model_dump(exclude_none=True) or {}
        return {}

    async def _extract_image_from_message(self, message: Any, image_index: int = 0, timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS) -> tuple[bytes | None, str | None]:
        """从消息对象中提取第 image_index 张图片的字节。"""
        segments = getattr(message, "message", None)
        if not segments:
            return None, "消息中没有可解析的内容段"

        img_idx = 0
        for seg in segments:
            if self._segment_type(seg) not in ("image", "cardimage"):
                continue
            if img_idx != image_index:
                img_idx += 1
                continue
            if isinstance(seg, dict):
                seg_data = seg.get("data", {}) or {}
            else:
                seg_data = getattr(seg, "data", None)
            seg_data = self._seg_data_to_dict(seg_data)
            return await self._download_image_segment(seg_data, timeout=timeout)

        return None, f"消息中找不到第 {image_index} 张图片（图片总数不足）"

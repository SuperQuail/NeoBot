"""ImageParseService — 下载图片、计算哈希、查询缓存、调用视觉模型获取描述"""

from __future__ import annotations

import asyncio
import hashlib
import math
from io import BytesIO
from typing import TYPE_CHECKING

import httpx
from PIL import Image

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_chat.providers.base import Provider
    from neobot_memory import ImageAnalysisService

ChatMessage = "PrivateMessage | GroupMessage"


class ImageParseService:
    """图片解析服务：下载 → 哈希 → 缓存查询 → 视觉模型 → 存储 → 替换消息段"""

    _PARSE_PROMPT = (
        "请用中文描述这张图片的内容。如果有文字，请把文字都描述出来。"
        "并尝试猜测这个图片的含义。最多100个字。"
    )

    def __init__(
        self,
        *,
        vision_provider: Provider | None = None,
        image_analysis_service: ImageAnalysisService | None = None,
        adapter: OneBotAdapter | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._vision_provider = vision_provider
        self._analysis = image_analysis_service
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._pending: dict[str, set[asyncio.Task[None]]] = {}

    async def parse_message_images(
        self,
        message: ChatMessage,
        queue_key: str,
    ) -> None:
        """异步解析消息中的所有图片，完成后用描述文本替换原图片段"""
        segments = getattr(message, "message", None)
        if not segments:
            return

        image_indices = []
        for i, seg in enumerate(segments):
            seg_type = _segment_type(seg)
            if seg_type in ("image", "cardimage"):
                image_indices.append(i)

        if not image_indices:
            return

        task = asyncio.create_task(
            self._parse_and_replace(message, image_indices)
        )
        self._pending.setdefault(queue_key, set()).add(task)
        task.add_done_callback(lambda t: self._pending.get(queue_key, set()).discard(t))

    async def wait_for_queue(self, queue_key: str) -> None:
        """等待指定队列的所有待处理图片解析完成"""
        tasks = self._pending.pop(queue_key, set())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _parse_and_replace(self, message, indices: list[int]) -> None:
        segments = getattr(message, "message", None)
        if not segments:
            return

        for i in indices:
            if i >= len(segments):
                continue
            seg = segments[i]
            seg_type = _segment_type(seg)
            if seg_type not in ("image", "cardimage"):
                continue
            try:
                description = await self._parse_single_image(seg)
            except Exception as exc:
                self._logger.error("图片解析失败", error=str(exc))
                description = "[图片解析失败]"
            # 替换为解析后的文本段
            segments[i] = _make_text_segment(description)

    async def _parse_single_image(self, segment) -> str:
        image_bytes = await self._download_image(segment)
        if image_bytes is None:
            return "[图片解析失败]"

        image_bytes = _resize_image_if_too_small(image_bytes, logger=self._logger)
        if image_bytes is None:
            return "[图片:特殊尺寸无法解析]"

        file_hash = hashlib.md5(image_bytes).hexdigest()

        # 检查数据库缓存
        if self._analysis is not None:
            try:
                cached = await self._analysis.get(file_hash)
                if cached and cached.analysis_text:
                    self._logger.debug("图片描述命中缓存", hash=file_hash[:8])
                    return f"[图片：{cached.analysis_text}]"
            except Exception:
                pass

        # 调用视觉模型
        if self._vision_provider is None:
            return "[图片解析失败：未配置视觉模型]"

        description = await self._call_vision_model(image_bytes)
        if description is None:
            return "[图片解析失败]"

        # 存入数据库
        if self._analysis is not None:
            try:
                await self._analysis.set(
                    file_hash,
                    source="chat_image",
                    mime_type=_detect_image_mime(image_bytes),
                    analysis_text=description,
                )
            except Exception as exc:
                self._logger.warning("保存图片描述到数据库失败", error=str(exc))

        return f"[图片：{description}]"

    async def _download_image(self, segment) -> bytes | None:
        """从消息段下载图片数据"""
        data = _segment_data(segment)
        url = data.get("url")
        file_name = data.get("file")

        if url:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(str(url))
                    resp.raise_for_status()
                    content = resp.content
                    if _is_valid_image(content):
                        return content
                    self._logger.warning(
                        "从URL下载的内容不是有效图片",
                        url=str(url)[:80],
                        content_type=resp.headers.get("content-type", ""),
                        content_len=len(content),
                    )
            except Exception as exc:
                self._logger.warning("从URL下载图片失败", url=str(url)[:80], error=str(exc))

        if file_name:
            try:
                from neobot_adapter.request.message import get_image
                result = await get_image(str(file_name))
                img_data = result.get("data", {})
                if isinstance(img_data, dict):
                    img_file = img_data.get("file") or img_data.get("url")
                    if img_file:
                        if str(img_file).startswith("base64://"):
                            import base64
                            content = base64.b64decode(str(img_file)[9:])
                            if _is_valid_image(content):
                                return content
                            self._logger.warning("get_image base64 内容不是有效图片", file=str(file_name)[:60])
                            return None
                        async with httpx.AsyncClient(timeout=30.0) as client:
                            resp = await client.get(str(img_file))
                            resp.raise_for_status()
                            content = resp.content
                            if _is_valid_image(content):
                                return content
                            self._logger.warning(
                                "get_image URL 内容不是有效图片",
                                file=str(file_name)[:60],
                                content_type=resp.headers.get("content-type", ""),
                                content_len=len(content),
                            )
            except Exception as exc:
                self._logger.warning("通过get_image下载失败", file=str(file_name)[:60], error=str(exc))

        return None

    async def _call_vision_model(self, image_bytes: bytes) -> str | None:
        """调用视觉模型获取图片描述"""
        import base64

        mime_type = _detect_image_mime(image_bytes)
        base64_data = base64.b64encode(image_bytes).decode("utf-8")
        image_url = f"data:{mime_type};base64,{base64_data}"

        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self._PARSE_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]

        try:
            response = await self._vision_provider.chat(messages)
            content = response.get("content", "")
            text = content.strip() if isinstance(content, str) else str(content)
            return text if text else None
        except Exception as exc:
            resp_body = ""
            if hasattr(exc, "response") and hasattr(exc.response, "text"):
                try:
                    resp_body = exc.response.text[:500]
                except Exception:
                    pass
            self._logger.error(
                "视觉模型调用失败",
                error=str(exc),
                mime=mime_type,
                image_bytes_len=len(image_bytes),
                api_response=resp_body,
            )
            return None


def _segment_type(segment) -> str:
    """获取消息段的类型字符串"""
    seg_type = getattr(segment, "type", None)
    if hasattr(seg_type, "value"):
        return seg_type.value
    if isinstance(segment, dict):
        return segment.get("type", "")
    return str(seg_type or "")


def _segment_data(segment) -> dict:
    """获取消息段的 data 字典"""
    raw_data = getattr(segment, "data", None)
    if raw_data is None and isinstance(segment, dict):
        raw_data = segment.get("data")
    if isinstance(raw_data, dict):
        return raw_data
    if hasattr(raw_data, "model_dump"):
        return raw_data.model_dump(exclude_none=True)
    return {}


_MIN_IMAGE_DIMENSION = 29       # Qwen VL models require width and height > 28
_MAX_IMAGE_PIXELS = 1024 * 1024


def _resize_image_if_too_small(image_bytes: bytes, logger: Logger | None = None) -> bytes | None:
    """若图片任一边未超过 28 则等比放大；放大后超最大像素则返回 None。"""
    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception:
        return image_bytes  # 无法解析则原样返回，让 API 自行判断

    w, h = img.size
    if w >= _MIN_IMAGE_DIMENSION and h >= _MIN_IMAGE_DIMENSION:
        return image_bytes

    scale = _MIN_IMAGE_DIMENSION / min(w, h)
    new_w = max(1, math.ceil(w * scale))
    new_h = max(1, math.ceil(h * scale))

    if new_w * new_h > _MAX_IMAGE_PIXELS:
        if logger:
            logger.warning(
                "图片尺寸过小且放大后将超过最大像素限制",
                original=f"{w}x{h}",
                scaled=f"{new_w}x{new_h}",
                max_pixels=_MAX_IMAGE_PIXELS,
            )
        return None

    if logger:
        logger.debug("图片尺寸过小，已等比放大", original=f"{w}x{h}", scaled=f"{new_w}x{new_h}")

    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    save_format = img.format or "PNG"
    if save_format == "JPEG" and resized.mode not in ("RGB", "L"):
        resized = resized.convert("RGB")

    out = BytesIO()
    resized.save(out, format=save_format)
    return out.getvalue()


_VALID_IMAGE_MAGIC = (
    b"\xff\xd8\xff",       # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"RIFF",               # WebP (need further check)
    b"GIF87a",             # GIF
    b"GIF89a",             # GIF
    b"BM",                 # BMP
)


def _is_valid_image(content: bytes) -> bool:
    """检查字节内容是否是有效的图片格式"""
    if len(content) < 16:
        return False
    for magic in _VALID_IMAGE_MAGIC:
        if content.startswith(magic):
            if magic == b"RIFF":
                return len(content) >= 12 and content[8:12] == b"WEBP"
            return True
    return False


def _detect_image_mime(image_bytes: bytes) -> str:
    """通过文件头魔数检测图片 MIME 类型"""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    return "image/jpeg"


def _make_text_segment(text: str):
    """创建一个文本类型的消息段"""
    from neobot_adapter.model.message import MessageSegment
    return MessageSegment(type="text", data={"text": text})

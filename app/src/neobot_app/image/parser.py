"""ImageParseService — 下载图片、计算哈希、查询缓存、调用视觉模型获取描述"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS
from neobot_app.image.unavailable import (
    REGISTRY,
    describe,
    expired_inline_text,
    image_ref_key,
    is_expiry_failure,
    ref_digest,
)
from neobot_app.utils.http import image_http_client
from neobot_app.utils.image_bytes import IMAGE_MAGIC_PREFIXES, looks_like_image

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_chat.providers.base import Provider
    from neobot_memory import ImageAnalysisService

    ChatMessage = PrivateMessage | GroupMessage
else:
    ChatMessage = Any


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
        native_vision_provider: Any = None,
    ) -> None:
        self._native_vision_provider = native_vision_provider
        self._vision_provider = vision_provider
        self._analysis = image_analysis_service
        self._adapter = adapter
        self._logger = logger or NullLogger()
        self._pending: dict[str, set[asyncio.Task[None]]] = {}

    def install_providers(
        self,
        *,
        vision_provider: Any = None,
        native_vision_provider: Any = None,
    ) -> tuple[Any, Any]:
        """换用新的视觉/原生视觉 provider，返回被替换下来的旧 (vision, native)。

        只换引用、不关闭旧 provider：由调用方在替换成功后统一清理，避免替换
        失败时旧 provider 已被关闭。
        """
        previous = (self._vision_provider, self._native_vision_provider)
        self._vision_provider = vision_provider
        self._native_vision_provider = native_vision_provider
        return previous

    async def parse_message_images(
        self,
        message: ChatMessage,
        queue_key: str,
    ) -> None:
        """原生视觉保留原图；否则异步解析并替换为描述文本。"""
        if getattr(self._native_vision_provider, "native_vision", False) is True:
            return
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
        task.add_done_callback(lambda t: self._cleanup_pending_task(queue_key, t))

    def _cleanup_pending_task(self, queue_key: str, task: asyncio.Task[None]) -> None:
        """任务完成后从集合移除；集合变空时删除 key，避免无界增长。"""
        tasks = self._pending.get(queue_key)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            del self._pending[queue_key]

    async def wait_for_queue(self, queue_key: str, timeout: float | None = None) -> None:
        """等待指定队列的所有待处理图片解析完成"""
        tasks = self._pending.pop(queue_key, set())
        if tasks:
            try:
                if timeout is not None and timeout > 0:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=timeout,
                    )
                else:
                    await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.TimeoutError:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self._logger.warning(
                    "图片解析等待超时",
                    queue_key=queue_key,
                    timeout_seconds=timeout,
                    task_count=len(tasks),
                )

    async def _parse_and_replace(self, message, indices: list[int]) -> None:
        segments = getattr(message, "message", None)
        if not segments:
            return

        async def parse_one(index: int) -> None:
            if index >= len(segments):
                return
            seg = segments[index]
            seg_type = _segment_type(seg)
            if seg_type not in ("image", "cardimage"):
                return
            try:
                description = await self._parse_single_image(seg)
            except Exception as exc:
                self._logger.error("图片解析失败", error=str(exc))
                description = "[图片解析失败]"
            # 替换为解析后的文本段
            segments[index] = _make_text_segment(description)

        # 一条消息里的多张图并发解析：串行时每张各自付一次下载超时（转发多条图片时
        # 会等比放大等待），并发后最坏只等一次超时。每张各写各的下标，互不干扰。
        await asyncio.gather(
            *(parse_one(index) for index in indices),
            return_exceptions=True,
        )

    async def _parse_single_image(self, segment) -> str:
        image_bytes, expired_key = await self._download_image_with_reason(segment)
        if image_bytes is None:
            if expired_key is not None:
                # 拉不到的图不再笼统报「解析失败」：说清是过期，并把以前留过的描述带上，
                # 让模型知道这张图大概是什么内容（见 image/unavailable.py）。
                return f"[图片：{expired_inline_text(await describe(expired_key))}]"
            return "[图片解析失败]"

        image_bytes = _resize_image_if_too_small(image_bytes, logger=self._logger)
        if image_bytes is None:
            return "[图片:特殊尺寸无法解析]"

        file_hash = hashlib.md5(image_bytes).hexdigest()
        # 引用索引：拉不到这张图时靠它回显描述（临时 URL / file id 只以摘要落库）
        ref = ref_digest(image_ref_key(_segment_data(segment)))

        # 检查数据库缓存
        if self._analysis is not None:
            try:
                cached = await self._analysis.get(file_hash)
                if cached and cached.analysis_text:
                    self._logger.debug("图片描述命中缓存", hash=file_hash[:8])
                    await self._remember_ref(ref, cached.analysis_text)
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
                await self._remember_ref(ref, description)
            except Exception as exc:
                self._logger.warning("保存图片描述到数据库失败", error=str(exc))

        return f"[图片：{description}]"

    async def _remember_ref(self, ref: str | None, description: str) -> None:
        """记下「引用摘要 -> 描述」（best-effort）：图片过期时还能说出它是什么。"""
        if not ref or not description:
            return
        remember = getattr(self._analysis, "remember_ref", None)
        if not callable(remember):
            return
        try:
            await remember(ref, description)
        except Exception as exc:
            self._logger.warning("图片引用索引写入失败", error=str(exc))

    async def description_for_ref(self, source_ref: str) -> str | None:
        """按引用摘要查历史描述（登记表的回显钩子，见 image/unavailable.py）。"""
        if not source_ref:
            return None
        lookup = getattr(self._analysis, "description_for_ref", None)
        if not callable(lookup):
            return None
        try:
            return await lookup(source_ref)
        except Exception:
            return None

    async def _download_image(self, segment) -> bytes | None:
        """从消息段下载图片数据（只关心字节的调用方用这个入口）。"""
        content, _ = await self._download_image_with_reason(segment)
        return content

    async def _download_image_with_reason(self, segment) -> tuple[bytes | None, str | None]:
        """从消息段下载图片数据；返回 (字节, 过期引用键)。

        过期引用键非 None 表示这张图已判定「拉不到」（本次运行内不再重试）。
        命中登记表的引用直接返回、不发请求；终端失败带「这张图没了」信号时登记。
        """
        data = _segment_data(segment)
        key = image_ref_key(data)
        if REGISTRY.notice(key) is not None:
            self._logger.debug("图片已登记为不可用，跳过下载", key=str(key)[:60])
            return None, key

        expired = False
        url = data.get("url")
        file_name = data.get("file")

        if url:
            try:
                async with image_http_client(timeout=IMAGE_FETCH_TIMEOUT_SECONDS, url=url) as client:
                    resp = await client.get(str(url))
                    resp.raise_for_status()
                    content = resp.content
                    if _is_valid_image(content):
                        return content, None
                    self._logger.warning(
                        "从URL下载的内容不是有效图片",
                        url=str(url)[:80],
                        content_type=resp.headers.get("content-type", ""),
                        content_len=len(content),
                    )
            except Exception as exc:
                expired = expired or is_expiry_failure(exc)
                self._logger.warning("从URL下载图片失败", url=str(url)[:80], error=str(exc))

        if file_name:
            try:
                from neobot_adapter.request.message import get_image
                # 将下载超时直接传给 get_image（进 call_api 的 timeout），
                # 不再外层包 asyncio.wait_for —— 双层 wait_for 时，内层超时
                # 与外层 cancel 互相竞争，迟到 echo 容易击中已取消 future 触发
                # InvalidStateError，进而回收连接。单层 + 直接取图超时足够。
                result = await get_image(str(file_name), timeout=IMAGE_FETCH_TIMEOUT_SECONDS)
                img_data = _response_data(result)
                img_file = ""
                if isinstance(img_data, dict):
                    img_file = str(img_data.get("file") or img_data.get("url") or "")
                if img_file:
                    content = await _read_image_ref(img_file)
                    if content is not None and _is_valid_image(content):
                        return content, None
                    self._logger.warning("get_image 返回内容不是有效图片", file=str(file_name)[:60])
                else:
                    # 拿不到 file/url：这个 OneBot 文件 id 已经解析不出来了（历史被清理）。
                    expired = True
                    self._logger.warning("get_image 返回无效数据", file=str(file_name)[:60])
            except TimeoutError:
                expired = True
                self._logger.warning(
                    "通过get_image下载超时",
                    file=str(file_name)[:60],
                    timeout_seconds=IMAGE_FETCH_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                # 非超时异常不判过期：可能是适配器断线一类的瞬时故障，下次还该再试。
                self._logger.warning("通过get_image下载失败", file=str(file_name)[:60], error=str(exc))

        if expired:
            REGISTRY.mark(key)
            return None, key
        return None, None

    async def _call_vision_model(self, image_bytes: bytes) -> str | None:
        """调用视觉模型获取图片描述"""
        try:
            part = _build_vision_image_part(image_bytes, logger=self._logger)
        except Exception as exc:
            self._logger.warning("准备视觉模型图片失败", error=str(exc))
            return None

        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": self._PARSE_PROMPT},
                    part,
                ],
            }
        ]

        try:
            response = await asyncio.wait_for(
                self._vision_provider.chat(messages),
                timeout=60.0,
            )
            content = response.get("content", "")
            text = content.strip() if isinstance(content, str) else str(content)
            return text if text else None
        except asyncio.TimeoutError:
            self._logger.warning(
                "视觉模型调用超时",
                timeout_seconds=60.0,
                image_bytes_len=len(image_bytes),
            )
            return None
        except Exception as exc:
            resp_body = ""
            if hasattr(exc, "response") and hasattr(exc.response, "text"):
                try:
                    resp_body = exc.response.text[:500]
                except Exception:
                    pass
            self._logger.warning(
                "视觉模型调用失败",
                exc_type=type(exc).__name__,
                error=str(exc),
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


def _response_data(response) -> dict:
    if isinstance(response, dict):
        data = response.get("data", {})
        return data if isinstance(data, dict) else {}
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_none=True)
    if hasattr(response, "model_dump"):
        dumped = response.model_dump(exclude_none=True)
        data = dumped.get("data", {})
        return data if isinstance(data, dict) else {}
    return {}


async def _read_image_ref(ref: str) -> bytes | None:
    if ref.startswith("base64://"):
        return base64.b64decode(ref[9:])
    if ref.startswith("file://"):
        return Path(ref[7:]).expanduser().read_bytes()
    path = Path(ref).expanduser()
    if path.exists() and path.is_file():
        return path.read_bytes()
    if not ref.startswith(("http://", "https://")):
        return None  # 非 URL 引用无需创建 HTTP 客户端
    async with image_http_client(timeout=IMAGE_FETCH_TIMEOUT_SECONDS, url=ref) as client:
        resp = await client.get(ref)
        resp.raise_for_status()
        return resp.content


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


_VISION_MAX_IMAGE_PIXELS = 1024 * 1024


def _build_vision_image_part(image_bytes: bytes, *, logger: Logger | None = None) -> dict:
    """把图片字节编码成 OpenAI 兼容的 image_url content part。

    处理流程：
      1. 按 magic 数检测 MIME（无法识别则按 image/png 兜底）。
      2. GIF → PNG：多数视觉 API（含 SiliconFlow Qwen-VL）不支持 GIF。
      3. 若任一边 < _MIN_IMAGE_DIMENSION 则等比放大；若总像素超过
         _VISION_MAX_IMAGE_PIXELS 则按 LANCZOS 等比缩小。
    返回形如 {"type":"image_url","image_url":{"url":"data:...;base64,..."}}，
    可直接放进 user content 列表。

    为什么是 OpenAI 格式而非 Anthropic 原生格式：视觉模型走 SiliconFlow/
    OpenAI 兼容端点，端点只认 image_url（见 self_heal/image_parse 故障）。
    """
    out_bytes, mime_type = _normalize_for_vision(image_bytes, logger=logger)
    data_url = f"data:{mime_type};base64,{base64.b64encode(out_bytes).decode('ascii')}"
    return {"type": "image_url", "image_url": {"url": data_url}}


def _normalize_for_vision(
    image_bytes: bytes, *, logger: Logger | None = None
) -> tuple[bytes, str]:
    """规范化图片为视觉模型可接受的字节 + MIME。GIF→PNG，超尺寸压图。"""
    mime_type = _detect_image_mime(image_bytes)

    try:
        img = Image.open(BytesIO(image_bytes))
        img.load()
    except Exception as exc:
        if logger:
            logger.debug("图片无法解码，按原样发送给视觉模型", error=str(exc))
        return image_bytes, mime_type

    w, h = img.size

    need_resize = False
    new_w, new_h = w, h

    if w < _MIN_IMAGE_DIMENSION or h < _MIN_IMAGE_DIMENSION:
        scale = _MIN_IMAGE_DIMENSION / max(1, min(w, h))
        new_w = max(1, math.ceil(w * scale))
        new_h = max(1, math.ceil(h * scale))
        need_resize = True

    if new_w * new_h > _VISION_MAX_IMAGE_PIXELS:
        scale = math.sqrt(_VISION_MAX_IMAGE_PIXELS / (new_w * new_h))
        new_w = max(1, int(new_w * scale))
        new_h = max(1, int(new_h * scale))
        while new_w * new_h > _VISION_MAX_IMAGE_PIXELS:
            if new_w >= new_h and new_w > 1:
                new_w -= 1
            elif new_h > 1:
                new_h -= 1
            else:
                break
        need_resize = True

    out_format = (img.format or "PNG").upper()
    if out_format not in {"JPEG", "PNG", "WEBP", "BMP"}:
        out_format = "PNG"

    # GIF 强制转 PNG：多数视觉 API 不支持 GIF（动图尤甚）
    if mime_type == "image/gif":
        out_format = "PNG"
        need_resize = True if (new_w, new_h) == (w, h) else need_resize  # flag: 需重编码
        gif_recode = True
    else:
        gif_recode = False

    if not need_resize and not gif_recode:
        return image_bytes, mime_type

    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS) if need_resize else img
    if out_format == "JPEG" and resized.mode not in ("RGB", "L"):
        resized = resized.convert("RGB")

    if logger and need_resize:
        logger.debug(
            "视觉模型图片已压图",
            original=f"{w}x{h}",
            scaled=f"{new_w}x{new_h}",
            fmt=out_format,
        )

    buf = BytesIO()
    resized.save(buf, format=out_format)
    return buf.getvalue(), Image.MIME.get(out_format, "image/png")


_VALID_IMAGE_MAGIC = IMAGE_MAGIC_PREFIXES


def _is_valid_image(content: bytes) -> bool:
    """检查字节内容是否是有效的图片格式"""
    return looks_like_image(content)


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

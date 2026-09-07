"""Load images into the reply model's native context, without a vision provider.

Transport contract: execute returns ImageContextResult (a str). The string is
metadata-only JSON; image_parts is an out-of-band list of OpenAI image_url blocks.
Consumers must collect that attribute BEFORE converting/slicing the string, then
append the parts in a user message AFTER all tool results of the current turn.
This is an ordinary awaited tool, never a background/session submission.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import warnings
from typing import Any

from PIL import Image

from neobot_app.image.source import ImageSourceResolver
from neobot_app.skills.base import SkillModule

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_DIMENSION = 4096
DEFAULT_AUTO_MAX_IMAGES = 4
_SOURCE_FIELDS = (
    "image_base64", "image_path", "image_url", "msg_number", "message_id",
    "chat_flow_id", "source", "image_id", "pool_key", "gallery_id", "emoji_id",
)


class ImageContextResult(str):
    """String-compatible tool text with a deliberately non-JSON image payload."""

    image_parts: list[dict]

    def __new__(cls, text: str, image_parts: list[dict] | None = None) -> ImageContextResult:
        result = super().__new__(cls, text)
        result.image_parts = list(image_parts or [])
        return result


def _result(metadata: dict, parts: list[dict] | None = None) -> ImageContextResult:
    return ImageContextResult(json.dumps(metadata, ensure_ascii=False), parts)


def _integer(value: Any, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} 必须是整数")
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{name} 必须是整数") from None
    if number < minimum:
        raise ValueError(f"{name} 不能小于 {minimum}")
    return number


def _normalize_image(raw: bytes, detail: str) -> tuple[dict, dict, int]:
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("图片为空或超过单图 10 MiB 限制")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                original_width, original_height = image.size
                if original_width * original_height > MAX_IMAGE_PIXELS:
                    raise ValueError("图片像素超过 2000 万限制")
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                animated = bool(getattr(image, "is_animated", False))
                # Keep validated native formats; normalize other formats/animations
                # to a single PNG frame instead of trusting user MIME/extensions.
                fmt = image.format
                resized = max(image.size) > MAX_IMAGE_DIMENSION
                if resized:
                    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.Resampling.LANCZOS)
                width, height = image.size
                if fmt not in ("PNG", "JPEG", "WEBP") or animated or resized:
                    output = io.BytesIO()
                    image.convert("RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB").save(output, format="PNG")
                    raw, fmt = output.getvalue(), "PNG"
                mime = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
    except ValueError:
        raise
    except Exception:
        raise ValueError("图片无效、损坏或无法安全解码") from None
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("规范化后图片超过单图 10 MiB 限制")
    part = {
        "type": "image_url",
        "image_url": {
            "url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}",
            "detail": detail,
        },
    }
    metadata = {
        "mime_type": mime, "width": width, "height": height,
        "original_width": original_width, "original_height": original_height,
        "resized": resized,
        "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "first_frame_only": animated,
    }
    return part, metadata, len(raw)


class ImageContextSkill(SkillModule):
    """Provider-independent native image context loader."""

    def __init__(
        self, *, adapter: Any = None, group_message_queue: Any = None,
        friend_message_queue: Any = None, image_pool: Any = None,
        creator_image_service: Any = None, emoji_service: Any = None,
    ) -> None:
        self._resolver = ImageSourceResolver(
            adapter=adapter, group_message_queue=group_message_queue,
            friend_message_queue=friend_message_queue, max_bytes=MAX_IMAGE_BYTES,
        )
        self._pool = image_pool
        self._image_service = creator_image_service
        self._emoji_service = emoji_service

    @property
    def name(self) -> str:
        return "image_context"

    @property
    def description(self) -> str:
        return "将聊天、图库、缓存池、路径、URL/base64 图片加载到主模型原生视觉上下文（无需独立视觉模型）"

    @property
    def instructions(self) -> str:
        return (
            "image_context__add_image 是普通同步返回工具（非 session）；图片会在本轮所有工具结果后进入视觉上下文，随后直接看图回答，无需另调视觉解析模型。\n"
            "每次选择一种来源；可多次调用，也可 sources=[引用,...]、image_path_list/image_url_list 或 image_indices 批量加载；主动调用不限制图片数量，但受字节/像素安全限额约束。\n"
            "聊天优先 msg_number，用户回复图片时使用[被回复消息]那行编号，不是用户文字回复编号；message_id 为真实 OneBot ID。\n"
            "image_index/image_indices 从0开始；chat_flow_id 如 Group_123/Friend_456，从最新消息向前取图片。\n"
            "source/image 支持 pool:<key>、gallery:<编号>、g_xxx/tmp_xxx 图片ID、emoji:<编号>（e:同义）、chat:<显示编号>:<从1开始的图片索引>、url:<URL>、file:<路径>及直接路径/URL/data URL。\n"
            "image_id 支持图库 g_xxx/tmp_xxx 或当前 image_pool 的 key；pool_key 也可直接引用缓存池。\n"
            "图库编号是 gallery 列表中的1-based编号；缓存池按当前会话隔离，过期或不存在会明确失败，不会自动选择另一张图。\n"
            "只获取图片，不发送、不入库、不产生独立解析描述。返回文本只有尺寸/MIME/哈希等 metadata，不含 base64。\n"
            "限制：单图10 MiB、单次合计20 MiB、2000万像素；最长边超过4096时等比缩小，保留原始与处理后尺寸metadata；校验实际格式，动图仅取首帧。"
        )

    def get_tools(self) -> list[dict]:
        strings = {
            "source": "统一图片引用，支持 pool:/gallery:/emoji:/chat:/url:/file: 或图片ID、路径、URL",
            "image": "source 的别名，与 drawing/图库工具的 image 引用兼容",
            "image_path": "本地图片路径", "image_url": "HTTP(S)/file/data URL",
            "image_base64": "原始base64、base64:// 或 data:image/...;base64,...",
            "image_id": "持久图库g_xxx/tmp_xxx图片ID，或当前缓存池图片key",
            "pool_key": "当前会话 image_pool 图片key", "chat_flow_id": "Group_123 或 Friend_456",
        }
        properties: dict[str, dict] = {
            name: {"type": "string", "description": desc} for name, desc in strings.items()
        }
        for name, desc in {
            "msg_number": "聊天显示编号；回复引用图片时选被回复消息编号",
            "message_id": "真实 OneBot 消息ID，不是显示编号",
            "image_index": "图片索引，从0开始，默认0",
            "gallery_id": "图库列表中的编号，从1开始",
            "emoji_id": "表情包编号，从1开始",
        }.items():
            properties[name] = {"type": "integer", "description": desc}
        for name, item_type, desc in (
            ("sources", "string", "批量统一图片引用"),
            ("image_path_list", "string", "批量本地路径"),
            ("image_url_list", "string", "批量URL"),
            ("image_indices", "integer", "同一聊天来源的多个0-based图片索引"),
        ):
            properties[name] = {"type": "array", "items": {"type": item_type}, "description": desc}
        properties["detail"] = {"type": "string", "enum": ["auto", "low", "high"], "default": "auto"}
        properties["timeout_seconds"] = {"type": "integer", "default": 30, "description": "整个调用超时，1至120秒"}
        return [self._tool_def("add_image", "获取图片到主模型原生视觉上下文；普通同步工具，不提交后台解析。每次只选一种来源；返回文本为metadata，图片另行进入上下文。", {"properties": properties})]

    def _expand(self, args: dict) -> list[dict]:
        args = dict(args)
        if "image" in args:
            if "source" in args:
                raise ValueError("image 和 source 不能同时提供")
            args["source"] = args.pop("image")
        batches = [name for name in ("sources", "image_path_list", "image_url_list", "image_indices") if name in args]
        if len(batches) > 1:
            raise ValueError("只能提供一种批量参数")
        if not batches:
            return [args]
        name = batches[0]
        values = args.pop(name)
        if not isinstance(values, list) or not values:
            raise ValueError("批量参数必须是非空图片列表")
        if name == "image_indices":
            if "image_index" in args or not any(key in args for key in ("msg_number", "message_id", "chat_flow_id")):
                raise ValueError("image_indices 仅用于聊天来源，不能与 image_index 同用")
            return [dict(args, image_index=value) for value in values]
        if any(key in args for key in _SOURCE_FIELDS):
            raise ValueError("批量来源不能与单图来源同时提供")
        field = {"sources": "source", "image_path_list": "image_path", "image_url_list": "image_url"}[name]
        return [dict(args, **{field: value}) for value in values]

    async def _source_args(self, args: dict) -> tuple[dict, str]:
        fields = [key for key in _SOURCE_FIELDS if args.get(key) is not None]
        if len(fields) != 1:
            raise ValueError("请且仅提供一种图片来源参数")
        field = fields[0]
        value = args[field]
        resolved = {key: args[key] for key in ("pipeline_key", "_numbering_mapping") if key in args}
        resolved["image_index"] = _integer(args.get("image_index", 0), "image_index")
        if isinstance(resolved.get("_numbering_mapping"), dict):
            resolved["_numbering_mapping"] = {
                _integer(k, "消息编号映射"): _integer(v, "消息ID映射")
                for k, v in resolved["_numbering_mapping"].items()
            }
        if field in ("msg_number", "message_id"):
            resolved[field] = _integer(value, field)
            return resolved, field
        if field in ("gallery_id", "emoji_id"):
            value = f"{'gallery' if field == 'gallery_id' else 'emoji'}:{_integer(value, field, minimum=1)}"
            field = "source"
        if not isinstance(value, str) or not value.strip():
            raise ValueError("图片引用必须是非空字符串")
        value = value.strip()
        if field in ("image_base64", "image_url", "image_path", "chat_flow_id"):
            resolved[field] = value
            return resolved, field
        if field == "pool_key":
            value = f"pool:{value}"
        if value.startswith("chat:"):
            tokens = value.split(":")
            if len(tokens) not in (2, 3):
                raise ValueError("chat 引用应为 chat:<显示编号>:<1-based图片索引>")
            resolved["msg_number"] = _integer(tokens[1], "msg_number")
            resolved["image_index"] = _integer(tokens[2] if len(tokens) == 3 else 1, "chat 图片索引", minimum=1) - 1
            return resolved, "chat"
        if value.startswith("pool:") or (field == "image_id" and not value.startswith(("g_", "tmp_")) and ":" not in value):
            if self._pool is None:
                raise ValueError("image_pool 未配置")
            pipeline_key = resolved.get("pipeline_key")
            if not isinstance(pipeline_key, str) or ":" not in pipeline_key:
                raise ValueError("缓存池来源缺少当前会话 pipeline_key")
            key = value[5:] if value.startswith("pool:") else value
            staged = self._pool.get(pipeline_key, key)
            if staged is None:
                raise ValueError("缓存池图片不存在或已过期")
            resolved["image_path"] = str(staged.file_path)
            return resolved, "pool"
        if value.startswith(("emoji:", "e:")) and self._emoji_service is not None:
            entry = self._emoji_service.get_entry(_integer(value.partition(":")[2], "emoji_id", minimum=1))
            if entry is None:
                raise ValueError("表情包图片不存在")
            resolved["image_path"] = str(entry.file_path)
            return resolved, "emoji"
        if value.startswith(("gallery:", "emoji:", "e:", "g_", "tmp_")) or value.isdecimal():
            if self._image_service is None:
                raise ValueError("creator_image_service 未配置")
            if value.isdecimal():
                value = f"gallery:{_integer(value, 'gallery_id', minimum=1)}"
            try:
                if value.startswith(("g_", "tmp_")):
                    path = await self._image_service._resolve_process_source(value)
                else:
                    path = await self._image_service.resolve_source_to_path(value)
            except Exception:
                raise ValueError("图库/表情包图片不存在或引用无效") from None
            resolved["image_path"] = str(path)
            return resolved, "gallery"
        if value.startswith("url:"):
            value = value[4:]
        elif value.startswith("file:") and not value.startswith("file://"):
            value = value[5:]
        resolved["image_url" if value.startswith(("http://", "https://", "data:", "file://", "base64://")) else "image_path"] = value
        return resolved, "reference"

    async def load_message(
        self, message: Any, *, pipeline_key: str = "",
        numbering_mapping: dict | None = None,
        max_images: int = DEFAULT_AUTO_MAX_IMAGES,
    ) -> ImageContextResult:
        """Internal eager loader for native replies without a tool-calling loop.

        Raw image/cardimage segments are loaded in order. A reply segment refers
        to a real OneBot message ID, not a display number, and loads its first
        image. No-image messages succeed with an empty payload. The optional
        context arguments keep this API aligned with tool-based loading; reply
        IDs do not require a display-number mapping. max_images is an automatic
        loading limit only (default 4); zero disables this eager loader.
        """
        try:
            max_images = _integer(max_images, "max_images")
        except ValueError as exc:
            return _result({"ok": False, "error": str(exc)})
        if max_images == 0:
            return _result({"ok": True, "count": 0, "images": []})
        if isinstance(message, dict):
            segments = message.get("message") or message.get("content") or []
            original_message_id = message.get("message_id")
        else:
            segments = getattr(message, "message", None) or getattr(message, "content", None) or []
            original_message_id = getattr(message, "message_id", None)
        if not isinstance(segments, (list, tuple)):
            return _result({"ok": True, "count": 0, "images": []})
        try:
            parts, images = [], []
            total = 0
            seen_replies: set[int] = set()
            truncated = False
            current_image_index = 0
            async with asyncio.timeout(30):
                for segment in segments:
                    kind = self._resolver._segment_type(segment)
                    if kind not in ("image", "cardimage", "reply"):
                        continue
                    if len(parts) >= max_images:
                        truncated = True
                        break
                    data = self._resolver._seg_data_to_dict(
                        segment.get("data") if isinstance(segment, dict) else getattr(segment, "data", None)
                    )
                    source_message_id = original_message_id
                    source_image_index = current_image_index
                    if kind == "reply":
                        message_id = _integer(data.get("id") or data.get("message_id"), "reply message_id")
                        source_message_id = message_id
                        source_image_index = 0
                        if message_id in seen_replies:
                            continue
                        seen_replies.add(message_id)
                        replied_segments = await self._resolver._fetch_segments_by_message_id(message_id)
                        if replied_segments is None:
                            raise ValueError("无法获取被引用消息，未能确认其中图片")
                        # Only a confirmed text-only reply can be silently skipped.
                        if self._resolver._image_count(replied_segments) == 0:
                            continue
                        raw, _ = await self._resolver._download_from_segments_with_error(replied_segments, 0, timeout=30)
                    else:
                        current_image_index += 1
                        raw, _ = await self._resolver._download_image_segment(data, timeout=30)
                    if raw is None:
                        raise ValueError("当前消息图片下载失败或超过大小限制")
                    part, metadata, size = await asyncio.to_thread(_normalize_image, raw, "auto")
                    total += size
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("图片合计超过单次20 MiB限制")
                    label = f"消息 {source_message_id if source_message_id is not None else '(当前)'} 第{source_image_index + 1}张图片"
                    images.append(dict(metadata, index=len(parts), source_kind=kind,
                                       message_id=source_message_id, image_index=source_image_index, label=label))
                    parts.append(part)
            metadata = {"ok": True, "count": len(parts), "images": images}
            if truncated:
                metadata["truncated"] = True
                metadata["message"] = f"本次自动加载上限为{max_images}张，后续图片/引用尚未查看；请用 add_image 按索引继续加载"
            return _result(metadata, parts)
        except ValueError as exc:
            return _result({"ok": False, "error": str(exc)})
        except TimeoutError:
            return _result({"ok": False, "error": "图片加载超时"})
        except Exception:
            return _result({"ok": False, "error": "图片加载失败"})

    async def execute(self, tool_name: str, args: dict[str, Any]) -> ImageContextResult:
        if tool_name != "add_image":
            return _result({"ok": False, "error": "未知 image_context 工具"})
        try:
            detail = args.get("detail", "auto")
            if detail not in ("auto", "low", "high"):
                raise ValueError("detail 必须是 auto/low/high")
            timeout = _integer(args.get("timeout_seconds", 30), "timeout_seconds", minimum=1)
            if timeout > 120:
                raise ValueError("timeout_seconds 不能超过120秒")
            requests = self._expand(args)
            parts, images = [], []
            total = 0
            async with asyncio.timeout(timeout):
                for index, request in enumerate(requests):
                    resolved, source_kind = await self._source_args(request)
                    raw, _ = await self._resolver.resolve(resolved, timeout=timeout)
                    if raw is None:
                        # Resolver diagnostics may contain a raw URL/inline base64.
                        # Never echo those into tool text, logs or model context.
                        raise ValueError("图片来源解析失败：检查编号/索引、路径/URL、base64格式及单图10 MiB限制")
                    part, metadata, size = await asyncio.to_thread(_normalize_image, raw, detail)
                    total += size
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("图片合计超过单次20 MiB限制")
                    parts.append(part)
                    image_metadata = dict(metadata, index=index, source_kind=source_kind, label=f"主动加载的第{index + 1}张图片")
                    if any(key in resolved for key in ("msg_number", "message_id", "chat_flow_id")):
                        image_index = resolved.get("image_index", 0)
                        message_id = resolved.get("message_id")
                        if message_id is None and "msg_number" in resolved:
                            message_id = (resolved.get("_numbering_mapping") or {}).get(resolved["msg_number"])
                        image_metadata.update(image_index=image_index, message_id=message_id)
                        if "msg_number" in resolved:
                            image_metadata["msg_number"] = resolved["msg_number"]
                        if message_id is not None:
                            image_metadata["label"] = f"消息 {message_id} 第{image_index + 1}张图片"
                        elif "msg_number" in resolved:
                            image_metadata["label"] = f"消息编号 {resolved['msg_number']} 第{image_index + 1}张图片"
                        elif "chat_flow_id" in resolved:
                            image_metadata["label"] = f"聊天流图片索引 {image_index}"
                    images.append(image_metadata)
            return _result({"ok": True, "count": len(parts), "images": images}, parts)
        except ValueError as exc:
            return _result({"ok": False, "error": str(exc)})
        except TimeoutError:
            return _result({"ok": False, "error": "图片加载超时"})
        except Exception:
            return _result({"ok": False, "error": "图片加载失败"})

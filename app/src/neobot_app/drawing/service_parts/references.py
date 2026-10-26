"""参考图解析、来源路径与图片编辑。"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from PIL import Image

from neobot_contracts.models.memory import CreatorImageRecord

from neobot_app.drawing.config import (
    DEFAULT_IMAGE_SIZE,
    DEFAULT_OUTPUT_FORMAT,
    GALLERY_SOURCE,
    TMP_SOURCE,
)

if TYPE_CHECKING:
    pass

from .helpers import _decode_data_url, _extension_for_mime


class ReferencesMixin:
    """参考图解析、来源路径与图片编辑。"""

    async def _get_reference_by_gallery_no(
        self, reference_id: int
    ) -> CreatorImageRecord | None:
        """按图库固定编号取图片。

        编号在入库时分配一次并写入 creator_images.gallery_no，
        不再依赖列表顺序，因此 gallery_update/删除/排序变化都不会让编号指错图。
        """
        if reference_id <= 0:
            return None
        async with self._uow_factory() as uow:
            record = await uow.creator_images.get_by_gallery_no(reference_id)
        if record is None or not Path(record.file_path).is_file():
            return None
        return record

    async def _resolve_reference(self, ref_str: str, *, conv_id: str = "") -> str | None:
        """解析参考图字符串，返回 base64 data URL。"""
        ref = ref_str.strip()
        if not ref:
            return None

        if ref.lstrip("-").isdigit() and int(ref) > 0:
            record = await self._get_reference_by_gallery_no(int(ref))
            if record is None:
                raise LookupError(f"图库编号 {ref} 不存在（用 gallery_list 查看现有编号）")
            return self._image_data_url(Path(record.file_path), record.mime_type)

        if ":" in ref:
            prefix, _, value = ref.partition(":")
            prefix = prefix.lower().strip()
            value = value.strip()

            if prefix in ("gallery", "g", "image", "img"):
                # 模型经常把图库引用写成 gallery:<编号> 或 gallery:<image_id>，
                # 两种都要接受：纯数字按图库固定编号解析，其余按 image_id 解析。
                if value.lstrip("-").isdigit() and int(value) > 0:
                    record = await self._get_reference_by_gallery_no(int(value))
                    if record is None:
                        raise LookupError(
                            f"图库编号 {value} 不存在（用 gallery_list 查看现有编号）"
                        )
                    return self._image_data_url(Path(record.file_path), record.mime_type)
                record = await self._get_existing(value)
                if record is None:
                    raise LookupError(f"图库中不存在 image_id={value}")
                return self._image_data_url(Path(record.file_path), record.mime_type)

            if prefix == "pool":
                if self._image_pool is None:
                    raise RuntimeError("图片暂存池未配置")
                if not conv_id:
                    raise ValueError("pool 引用需要 conv_id")
                staged = self._image_pool.get(conv_id, value)
                if staged is None:
                    raise LookupError(f"缓存池中不存在 key={value}（可能已过期）")
                return self._image_data_url(staged.file_path, staged.mime_type)

            if prefix in ("e", "emoji"):
                if not value.lstrip("-").isdigit() or int(value) <= 0:
                    raise ValueError(f"表情包编号无效: {value}")
                if self._emoji_service is None:
                    raise RuntimeError("表情包服务未配置")
                entry = self._emoji_service.get_entry(int(value))
                if entry is None:
                    raise LookupError(f"表情包编号 {value} 不存在")
                mime = mimetypes.guess_type(entry.file_path.name)[0] or "image/png"
                return self._image_data_url(entry.file_path, mime)

            if prefix == "url":
                return await self._download_as_data_url(value)

            if prefix == "file":
                path = await self._resolve_creator_path(value)
                if not path.is_file():
                    raise FileNotFoundError(f"文件不存在: {value}")
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                return self._image_data_url(path, mime)

            if prefix == "chat":
                parts = value.split(":")
                msg_id = int(parts[0])
                img_idx = int(parts[1]) if len(parts) > 1 else 1
                image_bytes = await self._load_chat_image_bytes(
                    message_id=msg_id, image_index=img_idx,
                )
                b64 = base64.b64encode(image_bytes).decode("utf-8")
                return f"data:image/png;base64,{b64}"

        if ref.startswith(("http://", "https://")):
            return await self._download_as_data_url(ref)

        record = await self._get_existing(ref)
        if record is not None:
            return self._image_data_url(Path(record.file_path), record.mime_type)

        raise LookupError(
            f"无法解析参考图: {ref}；支持格式："
            "gallery:<image_id 或 图库编号>、<image_id>、<图库编号>、pool:<key>、"
            "emoji:<编号>、url:<URL>、file:<路径>、chat:<消息编号>:<图片序号>"
        )

    async def resolve_source_to_path(self, source: str) -> Path:
        """将 source 描述符解析为本地文件路径。

        用于 ImagePoolSkill 的 put 操作，下载到临时目录并返回路径。

        支持的格式:
          - chat:<msg_id>:<img_index>
          - gallery:<image_id> 或 gallery:<图库编号>
          - emoji:<编号> 或 e:<编号>
          - url:<URL>
          - file:<路径>
        """
        source = source.strip()
        if ":" not in source:
            raise ValueError(f"无法解析 source: {source}")
        prefix, _, value = source.partition(":")
        prefix = prefix.lower().strip()
        value = value.strip()

        if prefix == "chat":
            parts = value.split(":")
            msg_id = int(parts[0])
            img_idx = int(parts[1]) if len(parts) > 1 else 1
            image_bytes = await self._load_chat_image_bytes(
                message_id=msg_id, image_index=img_idx,
            )
            path = self._tmp_dir / f"pool_chat_{msg_id}_{img_idx}.png"
            path.write_bytes(image_bytes)
            return path

        if prefix == "gallery":
            # 与 _resolve_reference 一致：数字按图库编号，其余按 image_id
            if value.lstrip("-").isdigit() and int(value) > 0:
                record = await self._get_reference_by_gallery_no(int(value))
                if record is None:
                    raise LookupError(f"图库编号 {value} 不存在")
            else:
                record = await self._get_existing(value)
                if record is None:
                    raise LookupError(f"图库中不存在 image_id={value}")
            return Path(record.file_path)

        if prefix in ("e", "emoji"):
            if not value.lstrip("-").isdigit() or int(value) <= 0:
                raise ValueError(f"表情包编号无效: {value}")
            if self._emoji_service is None:
                raise RuntimeError("表情包服务未配置")
            entry = self._emoji_service.get_entry(int(value))
            if entry is None:
                raise LookupError(f"表情包编号 {value} 不存在")
            return entry.file_path

        if prefix == "url":
            from neobot_app.utils.ssrf import validate_public_url_async

            if not await validate_public_url_async(value):
                raise ValueError(f"不允许下载非公网地址: {value}")
            response = await self._public_client.get(value)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            ext = ".png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "gif" in content_type:
                ext = ".gif"
            elif "webp" in content_type:
                ext = ".webp"
            path = self._tmp_dir / f"pool_url_{hashlib.md5(value.encode()).hexdigest()[:12]}{ext}"
            data = await self._read_limited(response)
            path.write_bytes(data)
            return path

        if prefix == "file":
            path = await self._resolve_creator_path(value)
            if not path.is_file():
                raise FileNotFoundError(f"文件不存在: {value}")
            return path

        raise ValueError(f"不支持的 source 格式: {source}")

    async def _download_as_data_url(self, url: str) -> str:
        from neobot_app.utils.ssrf import validate_public_url_async

        if not await validate_public_url_async(url):
            raise ValueError(f"不允许下载非公网地址: {url}")
        response = await self._public_client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png")
        mime = content_type.split(";")[0].strip()
        data = await self._read_limited(response)
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    async def _resolve_creator_path(self, value: str) -> Path:
        """限定 file: 引用必须位于 creator 数据目录（tmp/gallery）内。"""
        path = Path(value).expanduser().resolve()
        base = self._base_dir.resolve()
        try:
            path.relative_to(base)
        except ValueError:
            raise PermissionError(f"文件引用越界: {value}")
        return path

    async def _post_edits(
        self,
        client: httpx.AsyncClient,
        registered_model: Any,
        *,
        payload: dict[str, Any],
        references: list[str],
    ) -> httpx.Response | None:
        """参考图生图：multipart 调用 /images/edits（OpenAI 标准形态）。

        参考图必须是 data URL；否则返回 None，由调用方回退到 /images/generations。
        单张参考图字段名用 `image`，多张用重复的 `image[]`。
        """
        decoded: list[tuple[bytes, str]] = []
        for data_url in references:
            raw, mime = _decode_data_url(data_url)
            if raw is None:
                return None
            decoded.append((raw, mime))
        if not decoded:
            return None

        data: dict[str, Any] = {
            "model": payload.get("model") or registered_model.model_name,
            "prompt": str(payload.get("prompt") or ""),
            "size": payload.get("image_size") or DEFAULT_IMAGE_SIZE,
        }
        for key, value in payload.items():
            if key in {"model", "prompt", "image_size", "image", "images"} or value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                data[key] = value
            else:
                data[key] = json.dumps(value, ensure_ascii=False)

        field = "image" if len(decoded) == 1 else "image[]"
        files = [
            (field, (f"reference_{index + 1}{_extension_for_mime(mime)}", raw, mime))
            for index, (raw, mime) in enumerate(decoded)
        ]
        self._logger.debug(
            "参考图生图请求 /images/edits", count=len(decoded), field=field
        )
        return await client.post("/images/edits", data=data, files=files)

    async def _extract_image_bytes(self, data: dict[str, Any]) -> bytes:
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise ValueError("生图接口未返回图片数据")
        first = items[0]
        if not isinstance(first, dict):
            raise ValueError("生图接口返回格式无效")
        b64 = first.get("b64_json")
        if isinstance(b64, str) and b64.strip():
            return base64.b64decode(b64)
        url = first.get("url")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("生图接口未返回 url 或 b64_json")
        response = await self._public_client.get(url)
        response.raise_for_status()
        return await self._read_limited(response)

    def _copy_to_gallery(self, source_path: str, image_id: str) -> Path:
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"图片文件不存在: {source}")
        suffix = source.suffix or ".png"
        target = self._gallery_dir / f"{image_id}{suffix}"
        target.write_bytes(source.read_bytes())
        return target

    @staticmethod
    def _normalize_source(source: str) -> str:
        normalized = source.strip().lower()
        if normalized in {TMP_SOURCE, GALLERY_SOURCE}:
            return normalized
        raise ValueError("source 必须为 tmp 或 gallery")

    def _ensure_gallery_enabled(self) -> None:
        if self._config.gallery_capacity <= 0:
            raise ValueError("图库管理已禁用")

    @staticmethod
    def _new_image_id(source: str) -> str:
        prefix = "g" if source == GALLERY_SOURCE else "tmp"
        return f"{prefix}_{uuid4().hex[:12]}"

    @staticmethod
    def _detect_suffix(image_bytes: bytes) -> str:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
            return "webp"
        return DEFAULT_OUTPUT_FORMAT

    @staticmethod
    def _read_dimensions(file_path: Path) -> tuple[int | None, int | None]:
        try:
            with Image.open(file_path) as image:
                return image.size
        except Exception:
            return None, None

    @staticmethod
    def _image_data_url(file_path: Path, mime_type: str | None) -> str:
        data = base64.b64encode(file_path.read_bytes()).decode("utf-8")
        mime = mime_type or mimetypes.guess_type(file_path.name)[0] or "image/png"
        return f"data:{mime};base64,{data}"

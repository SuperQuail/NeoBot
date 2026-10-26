"""图片发送、聊天图片导入与表情包管理。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any


from neobot_contracts.models import ConversationRef

from neobot_app.drawing.config import (
    GALLERY_SOURCE,
    TMP_SOURCE,
)
from neobot_app.utils.media_sender import send_image as _media_send_image

if TYPE_CHECKING:
    pass

from .helpers import _record_payload, _sanitize_filename


class DeliveryMixin:
    """图片发送、聊天图片导入与表情包管理。"""

    async def send_image(
        self,
        *,
        image_id: str,
        source: str | None = None,
        group_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        if source and record.source != self._normalize_source(source):
            raise LookupError(f"图片 {image_id} 不在 {source} 中")
        path = Path(record.file_path)
        if not path.exists():
            raise FileNotFoundError(f"图片文件不存在: {path}")

        group_id = (group_id or "").strip()
        user_id = (user_id or "").strip()
        if group_id:
            conversation_ref = ConversationRef(kind="group", id=group_id)
        elif user_id:
            conversation_ref = ConversationRef(kind="private", id=user_id)
        else:
            raise ValueError("未指定 group_id 或 user_id，无法确定发送目标")

        if self._file_server is None:
            raise RuntimeError("file_server not initialized")
        await asyncio.wait_for(
            _media_send_image(self._file_server, self._adapter, conversation_ref, path),
            timeout=self._get_io_timeout_seconds(),
        )

    async def send_image_by_path(
        self,
        file_path: str,
        *,
        group_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        """直接通过文件路径发送图片（无需数据库记录）。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"图片文件不存在: {path}")
        group_id = (group_id or "").strip()
        user_id = (user_id or "").strip()
        if group_id:
            conversation_ref = ConversationRef(kind="group", id=group_id)
        elif user_id:
            conversation_ref = ConversationRef(kind="private", id=user_id)
        else:
            raise ValueError("未指定 group_id 或 user_id")
        if self._file_server is None:
            raise RuntimeError("file_server not initialized")
        await asyncio.wait_for(
            _media_send_image(self._file_server, self._adapter, conversation_ref, path),
            timeout=self._get_io_timeout_seconds(),
        )

    def list_markdown_images(self) -> list[dict[str, Any]]:
        """列出 markdown_images 目录中的图片文件。"""
        if self._markdown_dir is None or not self._markdown_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for child in sorted(self._markdown_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not child.is_file():
                continue
            if child.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            try:
                stat = child.stat()
            except OSError:
                stat = None
            result.append({
                "filename": child.name,
                "path": str(child),
                "size": stat.st_size if stat else 0,
                "mtime": stat.st_mtime if stat else 0,
            })
        return result

    async def import_chat_image(
        self,
        *,
        message_id: int,
        image_index: int = 1,
        target: str = TMP_SOURCE,
        description: str | None = None,
        name: str | None = None,
        image_source: str | None = None,
    ) -> dict[str, Any]:
        target = target.strip().lower()
        if target not in {TMP_SOURCE, GALLERY_SOURCE, "emoji"}:
            raise ValueError("target 必须为 tmp、gallery 或 emoji")
        image_bytes = await self._load_chat_image_bytes(
            message_id=message_id,
            image_index=image_index,
        )
        if target == "emoji":
            return await self.add_emoji_bytes(
                image_bytes,
                file_name=name or f"chat_{message_id}_{image_index}",
                description=description,
            )
        if target == GALLERY_SOURCE:
            self._ensure_gallery_enabled()
            await self._ensure_gallery_capacity()
        record = await self._save_image_bytes(
            image_bytes,
            source=target,
            prompt=None,
            description=description,
            image_source=image_source,
        )
        if name and target == GALLERY_SOURCE:
            safe_name = _sanitize_filename(name)
            if safe_name:
                record = await self.gallery_rename(image_id=record.image_id, new_name=safe_name)
        return {"target": target, "image": _record_payload(record)}

    async def import_chat_images(
        self,
        *,
        message_id: int,
        image_indices: list[int] | None = None,
        target: str = TMP_SOURCE,
        description: str | None = None,
        name: str | None = None,
        image_source: str | None = None,
    ) -> list[dict[str, Any]]:
        """一次从同一条消息导入多张图片到 tmp/gallery/emoji。

        Args:
            image_indices: 1-based 索引列表（保持与 import_chat_image 一致）；None 表示全部 image 段
            其他参数与 import_chat_image 一致；name 仅 multi 时不适用（每张图自动生成名）

        Returns:
            每张图的结果列表：成功 {"ok": True, "index": int, "target": ..., "image": ...}，
            失败 {"ok": False, "index": int, "error": ...}。
        """
        target = target.strip().lower()
        if target not in {TMP_SOURCE, GALLERY_SOURCE, "emoji"}:
            raise ValueError("target 必须为 tmp、gallery 或 emoji")

        if target == GALLERY_SOURCE:
            self._ensure_gallery_enabled()

        # 一次 get_msg 拉取 segments
        result = await self._call_api_with_timeout("get_msg", {"message_id": message_id})
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            raise LookupError(f"无法读取消息 {message_id}")
        segments = data.get("message")
        if not isinstance(segments, list):
            raise LookupError(f"消息 {message_id} 不包含消息段")
        image_segments = [
            segment
            for segment in segments
            if isinstance(segment, dict) and str(segment.get("type")) in {"image", "cardimage"}
        ]
        if not image_segments:
            raise LookupError(f"消息 {message_id} 没有图片")

        if image_indices is None:
            indices = list(range(1, len(image_segments) + 1))
        else:
            indices = [int(i) for i in image_indices if int(i) > 0]

        results: list[dict[str, Any]] = []
        for idx in indices:
            if idx > len(image_segments):
                results.append({"ok": False, "index": idx, "error": f"消息 {message_id} 没有第 {idx} 张图片"})
                continue
            segment_data = image_segments[idx - 1].get("data") or {}
            if not isinstance(segment_data, dict):
                results.append({"ok": False, "index": idx, "error": "图片段无效"})
                continue
            try:
                image_bytes = await self._download_image_segment(segment_data)
            except Exception as exc:
                results.append({"ok": False, "index": idx, "error": f"下载失败: {exc}"})
                continue

            try:
                if target == "emoji":
                    rec = await self.add_emoji_bytes(
                        image_bytes,
                        file_name=name or f"chat_{message_id}_{idx}",
                        description=description,
                    )
                    results.append({"ok": True, "index": idx, "target": target, "image": rec})
                    continue
                if target == GALLERY_SOURCE:
                    await self._ensure_gallery_capacity()
                record = await self._save_image_bytes(
                    image_bytes,
                    source=target,
                    prompt=None,
                    description=description,
                    image_source=image_source,
                )
                if name and target == GALLERY_SOURCE:
                    safe_name = _sanitize_filename(f"{name}_{idx}")
                    if safe_name:
                        record = await self.gallery_rename(image_id=record.image_id, new_name=safe_name)
                results.append({"ok": True, "index": idx, "target": target, "image": _record_payload(record)})
            except Exception as exc:
                results.append({"ok": False, "index": idx, "error": f"{type(exc).__name__}: {exc}"})
        return results

    async def add_emoji_from_image(
        self,
        *,
        image_id: str,
        description: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        image_bytes = Path(record.file_path).read_bytes()
        return await self.add_emoji_bytes(
            image_bytes,
            file_name=name or Path(record.file_path).name,
            description=description or record.description,
        )

    async def add_emoji_bytes(
        self,
        image_bytes: bytes,
        *,
        file_name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        if not self._config.allow_emoji_add:
            raise PermissionError("配置禁止 Creator Agent 增加表情包")
        if self._emoji_service is None:
            raise RuntimeError("表情包服务未配置")
        result = await self._emoji_service.add_image_bytes(
            image_bytes,
            file_name=file_name,
            analysis_text=description,
        )
        return {
            "target": "emoji",
            "emoji": {
                "number": result.number,
                "file_name": result.entry.file_name,
                "file_path": str(result.entry.file_path),
                "description": result.entry.analysis_text,
            },
        }

    def list_emojis(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if self._emoji_service is None:
            return []
        limit = limit if limit is not None else self._config.emoji_page_size
        entries, total, has_more = self._emoji_service.list_entries_paginated(
            offset=offset,
            limit=limit,
        )
        result = []
        for number, entry in entries:
            result.append({
                "number": number,
                "file_name": entry.file_name,
                "file_path": str(entry.file_path),
                "description": entry.analysis_text,
                "use_count": entry.use_count,
            })
        return result

    def search_emojis(self, keyword: str, limit: int | None = None) -> list[dict[str, Any]]:
        if self._emoji_service is None:
            return []
        limit = limit if limit is not None else self._config.emoji_page_size
        entries = self._emoji_service.search_entries(keyword, limit=limit)
        return [
            {
                "number": number,
                "file_name": entry.file_name,
                "file_path": str(entry.file_path),
                "description": entry.analysis_text,
                "use_count": entry.use_count,
            }
            for number, entry in entries
        ]

    def get_emoji_count(self) -> int:
        if self._emoji_service is None:
            return 0
        return self._emoji_service.emoji_count

    async def delete_emoji(self, *, number: int) -> bool:
        if not self._config.allow_emoji_delete:
            raise PermissionError("配置禁止 Creator Agent 删除表情包")
        if self._emoji_service is None:
            raise RuntimeError("表情包服务未配置")
        return await self._emoji_service.delete_entry(number)

    async def update_emoji_description(self, *, number: int, description: str) -> dict[str, Any]:
        if self._emoji_service is None:
            raise RuntimeError("表情包服务未配置")
        entry = await self._emoji_service.update_entry_description(number, description)
        return {
            "number": number,
            "file_name": entry.file_name,
            "file_path": str(entry.file_path),
            "description": entry.analysis_text,
        }

    async def rename_emoji(self, *, number: int, new_name: str) -> dict[str, Any]:
        if self._emoji_service is None:
            raise RuntimeError("表情包服务未配置")
        entry = await self._emoji_service.rename_entry(number, new_name)
        return {
            "number": number,
            "file_name": entry.file_name,
            "file_path": str(entry.file_path),
            "description": entry.analysis_text,
        }


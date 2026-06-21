"""Image generation, storage, and reference resolution service."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from PIL import Image

from neobot_adapter import OneBotAdapter
from neobot_chat import get_registered_model
from neobot_chat.providers.base import Provider
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.memory import CreatorImageRecord
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory

from neobot_app.core import DATA_DIR
from neobot_app.drawing.config import (
    DEFAULT_IMAGE_SIZE,
    DEFAULT_OUTPUT_FORMAT,
    GALLERY_SOURCE,
    TMP_SOURCE,
    _IMAGE_EXTENSIONS,
    DrawServiceConfig,
    ImageGenerationError,
)
from neobot_app.message.image_pipeline import prepare_local_image
from neobot_app.time_context import monotonic_seconds
from neobot_app.utils.media_sender import send_image as _media_send_image

if TYPE_CHECKING:
    from neobot_app.core.file_server import FileServer
    from neobot_app.emoji.service import EmojiService
    from neobot_app.image_pool import ImageStagingPool
    from neobot_contracts.models.memory import EmojiRecord


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _read_sidecar_description(file_path: str | Path) -> str | None:
    """Read .txt sidecar file for image description, or None."""
    path = Path(file_path)
    txt_path = path.with_suffix(".txt")
    if not txt_path.exists():
        return None
    try:
        content = txt_path.read_text(encoding="utf-8").strip()
        return content or None
    except Exception:
        return None


def _sanitize_filename(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    stem = Path(raw).stem.strip()
    if not stem:
        return ""
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    cleaned = cleaned.strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:100] or "unnamed"


class CreatorImageService:
    """Generate, store, and send Creator Agent images."""

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
    _TMP_MAX_AGE_SECONDS = 12 * 60 * 60

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        adapter: OneBotAdapter,
        config: DrawServiceConfig,
        data_dir: Path = DATA_DIR,
        model_name: str = "creator_image_model",
        emoji_service: "EmojiService | None" = None,
        vision_provider: Provider | None = None,
        markdown_dir: Path | None = None,
        file_server: "FileServer | None" = None,
        image_pool: "ImageStagingPool | None" = None,
        logger: Logger | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter = adapter
        self._config = config
        self._logger = logger or NullLogger()
        self._emoji_service = emoji_service
        self._vision_provider = vision_provider
        self._file_server = file_server
        self._image_pool = image_pool
        self._model = get_registered_model(model_name)
        self._base_dir = data_dir / "creator"
        self._tmp_dir = self._base_dir / "tmp"
        self._gallery_dir = self._base_dir / "gallery"
        self._markdown_dir = markdown_dir
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._gallery_dir.mkdir(parents=True, exist_ok=True)
        timeout = self._model.settings.timeout_seconds
        self._client = httpx.AsyncClient(
            base_url=self._model.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self._model.api_key}"},
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        )
        self._cleanup_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        await self._stop_cleanup_task()
        await self.cleanup_tmp()
        await self._client.aclose()

    async def start(self) -> None:
        self._start_cleanup_task()

    async def stop(self) -> None:
        await self._stop_cleanup_task()

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    def _get_vision_timeout_seconds(self) -> float:
        return 60.0

    async def _call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await asyncio.wait_for(
            self._adapter.call_api(action, params),
            timeout=self._get_io_timeout_seconds(),
        )

    async def _send_with_timeout(self, conversation_ref: ConversationRef, segments: list[dict[str, Any]]) -> Any:
        return await asyncio.wait_for(
            self._adapter.send(conversation_ref, segments),
            timeout=self._get_io_timeout_seconds(),
        )

    async def _cleanup_stale_records(self) -> None:
        """删除数据库中文件已不存在的记录，更新文件已重命名的记录，并对各目录内哈希重复的文件去重（保留最旧）。"""
        disk_files: set[str] = set()

        # 逐目录去重：同一目录内哈希相同的文件只保留最旧的
        for directory in (self._tmp_dir, self._gallery_dir):
            if not directory.exists():
                continue
            hash_to_files: dict[str, list[Path]] = {}
            for child in directory.iterdir():
                if not child.is_file() or child.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                resolved = str(child.resolve())
                disk_files.add(resolved)
                try:
                    prepared = prepare_local_image(child)
                    hash_to_files.setdefault(prepared.file_hash, []).append(child)
                except Exception:
                    continue

            for file_hash, files in hash_to_files.items():
                if len(files) <= 1:
                    continue
                files.sort(key=lambda f: f.stat().st_mtime)
                keeper = files[0]
                for dup in files[1:]:
                    self._logger.info(
                        f"图库去重: 保留较旧文件 {keeper.name}，删除重复文件 {dup.name}"
                    )
                    dup.unlink(missing_ok=True)
                    dup.with_suffix(".txt").unlink(missing_ok=True)
                    disk_files.discard(str(dup.resolve()))

        async with self._uow_factory() as uow:
            all_records = await uow.creator_images.list(source=None, limit=99999, offset=0)
            for record in all_records:
                record_path = Path(record.file_path)
                if record_path.exists() and record_path.is_file():
                    resolved = str(record_path.resolve())
                    if resolved != record.file_path:
                        await uow.creator_images.rename(record.image_id, resolved)
                    continue
                resolved = str(record_path.resolve())
                if resolved in disk_files:
                    if resolved != record.file_path:
                        await uow.creator_images.rename(record.image_id, resolved)
                    continue
                self._logger.debug(f"清理失效图库记录: {record.image_id} (文件不存在)")
                await uow.creator_images.delete(record.image_id)
            await uow.commit()

    async def _maybe_cleanup(self) -> None:
        """每次工具查询/检索前强制执行全量清理（无冷却）。"""
        self._start_cleanup_task()
        try:
            await self._cleanup_stale_records()
        except Exception as exc:
            self._logger.error(f"图库清理失败: {exc}")

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_stale_records()
                await self._cleanup_expired_tmp_files()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.error(f"图库定时清理失败: {exc}")

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

    async def cleanup_tmp(self) -> None:
        """Delete all files in the tmp directory and remove corresponding DB records."""
        deleted_count = 0
        if self._tmp_dir.exists():
            for child in self._tmp_dir.iterdir():
                if child.is_file():
                    try:
                        child.unlink()
                        deleted_count += 1
                    except OSError as exc:
                        self._logger.warning(
                            f"删除临时文件失败: {child}",
                            error=str(exc),
                        )

        db_deleted = 0
        try:
            async with self._uow_factory() as uow:
                db_deleted = await uow.creator_images.delete_by_source("tmp")
                await uow.commit()
        except Exception as exc:
            self._logger.warning(
                "清理临时图片数据库记录失败",
                error=str(exc),
            )

        if deleted_count or db_deleted:
            self._logger.info(
                "creator 临时文件已清理",
                deleted_files=deleted_count,
                deleted_records=db_deleted,
            )

    async def _cleanup_expired_tmp_files(self) -> None:
        """删除超过保留时间的临时绘图文件及对应记录。"""
        cutoff = time.time() - self._TMP_MAX_AGE_SECONDS
        expired_ids: list[str] = []
        deleted_files = 0

        async with self._uow_factory() as uow:
            records = await uow.creator_images.list(source=TMP_SOURCE, limit=99999, offset=0)
            for record in records:
                path = Path(record.file_path)
                try:
                    mtime = path.stat().st_mtime if path.exists() else 0.0
                except OSError:
                    mtime = 0.0
                if mtime > cutoff:
                    continue
                if path.exists():
                    try:
                        path.unlink()
                        deleted_files += 1
                    except OSError as exc:
                        self._logger.warning(
                            "删除过期临时图片失败",
                            image_id=record.image_id,
                            path=str(path),
                            error=str(exc),
                        )
                        continue
                try:
                    path.with_suffix(".txt").unlink(missing_ok=True)
                except OSError:
                    pass
                expired_ids.append(record.image_id)

            for image_id in expired_ids:
                await uow.creator_images.delete(image_id)
            await uow.commit()

        if expired_ids or deleted_files:
            self._logger.info(
                "creator 过期临时图片已清理",
                deleted_files=deleted_files,
                deleted_records=len(expired_ids),
                max_age_hours=self._TMP_MAX_AGE_SECONDS // 3600,
            )

    async def generate_image(
        self,
        *,
        prompt: str,
        references: list[str] | None = None,
        reference_id: int | None = None,
        negative_prompt: str | None = None,
        image_size: str | None = None,
        seed: int | None = None,
        image_source: str | None = None,
        conv_id: str = "",
    ) -> CreatorImageRecord:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")

        payload: dict[str, Any] = {
            "model": self._model.model_name,
            "prompt": prompt,
            "image_size": image_size or DEFAULT_IMAGE_SIZE,
        }
        payload.update(self._model.settings.extra_body or {})
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed

        resolved_data_urls: list[str] = []
        if reference_id is not None:
            ref = await self._get_reference_by_number(reference_id)
            if ref is None:
                raise LookupError(f"参考图编号 {reference_id} 不存在")
            resolved_data_urls.append(self._image_data_url(Path(ref.file_path), ref.mime_type))
        if references:
            for ref_str in references:
                url = await self._resolve_reference(ref_str.strip(), conv_id=conv_id)
                if url:
                    resolved_data_urls.append(url)

        if len(resolved_data_urls) == 1:
            payload["image"] = resolved_data_urls[0]
        elif len(resolved_data_urls) > 1:
            payload["image"] = resolved_data_urls

        response = await self._client.post("/images/generations", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._logger.error(
                "生图接口返回错误状态码",
                status=response.status_code,
                body=response.text[:500],
            )
            raise ImageGenerationError({
                "error_type": "HTTPStatusError",
                "status_code": exc.response.status_code,
                "response_body": exc.response.text,
                "request_url": str(exc.request.url),
            }) from exc
        try:
            image_bytes = await self._extract_image_bytes(response.json())
        except ValueError as exc:
            self._logger.error(
                "生图接口返回数据解析失败",
                status=response.status_code,
                body=response.text[:500],
            )
            raise ImageGenerationError({
                "error_type": "ValueError",
                "message": str(exc),
                "status_code": response.status_code,
                "response_body": response.text,
            }) from exc
        return await self._save_image_bytes(
            image_bytes,
            source=TMP_SOURCE,
            prompt=prompt,
            description=None,
            image_source=image_source,
        )

    async def list_images(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        normalized = self._normalize_source(source) if source else None
        await self._maybe_cleanup()
        await self._sync_image_sidecars(source=normalized)
        return await self._list_image_records(source=normalized, limit=limit, offset=offset)

    async def count_images(self, *, source: str | None = None) -> int:
        await self._maybe_cleanup()
        async with self._uow_factory() as uow:
            return await uow.creator_images.count(source=source)

    async def search_images(
        self,
        keyword: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        await self._maybe_cleanup()
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            return await uow.creator_images.search(
                keyword,
                source=source,
                limit=limit,
                offset=offset,
            )

    async def _list_image_records(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            return await uow.creator_images.list(source=source, limit=limit, offset=offset)

    async def gallery_add(
        self, *, image_id: str, description: str | None = None, name: str | None = None
    ) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        source = await self._get_existing(image_id)
        if source is None:
            raise LookupError(f"图片 {image_id} 不存在")
        if source.source == GALLERY_SOURCE:
            return source
        await self._ensure_gallery_capacity()
        target_id = self._new_image_id(GALLERY_SOURCE)
        target_path = self._copy_to_gallery(source.file_path, target_id)
        record = await self._upsert_record(
            target_id,
            source=GALLERY_SOURCE,
            file_path=target_path,
            prompt=source.prompt,
            description=description or source.description,
            image_source=source.image_source,
        )
        if name:
            safe_name = _sanitize_filename(name)
            if safe_name:
                record = await self.gallery_rename(image_id=target_id, new_name=safe_name)
        return record

    async def gallery_replace(self, *, target_id: str, source_id: str) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        target = await self._get_existing(target_id)
        if target is None or target.source != GALLERY_SOURCE:
            raise LookupError(f"图库图片 {target_id} 不存在")
        source = await self._get_existing(source_id)
        if source is None:
            raise LookupError(f"来源图片 {source_id} 不存在")
        target_path = Path(target.file_path)
        target_path.write_bytes(Path(source.file_path).read_bytes())
        return await self._upsert_record(
            target.image_id,
            source=GALLERY_SOURCE,
            file_path=target_path,
            prompt=source.prompt,
            description=target.description or source.description,
        )

    async def update_image_description(
        self, *, image_id: str, description: str
    ) -> CreatorImageRecord:
        text = description.strip()
        if not text:
            raise ValueError("图片描述不能为空")
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        file_path = Path(record.file_path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {file_path}")
        return await self._upsert_record(
            record.image_id,
            source=record.source,
            file_path=file_path,
            prompt=record.prompt,
            description=text,
        )

    async def gallery_delete(self, *, image_id: str) -> bool:
        self._ensure_gallery_enabled()
        record = await self._get_existing(image_id)
        if record is None or record.source != GALLERY_SOURCE:
            return False
        async with self._uow_factory() as uow:
            deleted = await uow.creator_images.delete(image_id)
            await uow.commit()
        if deleted:
            Path(record.file_path).unlink(missing_ok=True)
            Path(record.file_path).with_suffix(".txt").unlink(missing_ok=True)
        return deleted

    async def update_image_source(self, image_id: str, image_source: str) -> CreatorImageRecord:
        """更新图库/暂存区图片的图片来源。"""
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        file_path = Path(record.file_path)
        return await self._upsert_record(
            record.image_id,
            source=record.source,
            file_path=file_path,
            prompt=record.prompt,
            description=record.description,
            image_source=image_source,
        )

    async def update_emoji_source(self, number: int, image_source: str) -> EmojiRecord | None:
        """更新表情包的图片来源。"""
        if self._emoji_service is None:
            return None
        return await self._emoji_service.update_emoji_source(number, image_source)

    async def gallery_rename(
        self, *, image_id: str, new_name: str
    ) -> CreatorImageRecord:
        self._ensure_gallery_enabled()
        record = await self._get_existing(image_id)
        if record is None:
            raise LookupError(f"图片 {image_id} 不存在")
        if record.source != GALLERY_SOURCE:
            raise ValueError(f"只能重命名图库图片，{image_id} 来源为 {record.source}")

        old_path = Path(record.file_path)
        if not old_path.exists() or not old_path.is_file():
            raise FileNotFoundError(f"图片文件不存在: {old_path}")

        safe_name = _sanitize_filename(new_name)
        if not safe_name:
            raise ValueError("新名称无效（清理后为空）")

        suffix = old_path.suffix
        new_path = old_path.parent / f"{safe_name}{suffix}"

        old_resolved = old_path.resolve()
        new_resolved = new_path.resolve()
        if old_resolved == new_resolved:
            return record

        if new_path.exists():
            raise FileExistsError(f"目标文件名已存在: {new_path.name}")

        old_path.rename(new_path)
        old_txt = old_path.with_suffix(".txt")
        new_txt = new_path.with_suffix(".txt")
        if old_txt.exists():
            old_txt.rename(new_txt)

        try:
            async with self._uow_factory() as uow:
                renamed = await uow.creator_images.rename(image_id, str(new_path))
                await uow.commit()
        except Exception:
            new_path.rename(old_path)
            if new_txt.exists():
                new_txt.rename(old_txt)
            raise

        return renamed

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

    async def _save_image_bytes(
        self,
        image_bytes: bytes,
        *,
        source: str,
        prompt: str | None,
        description: str | None,
        image_source: str | None = None,
    ) -> CreatorImageRecord:
        file_hash = hashlib.sha256(image_bytes).hexdigest()
        if source != TMP_SOURCE:
            async with self._uow_factory() as uow:
                existing = await uow.creator_images.get_by_hash(file_hash)
                if existing is not None:
                    raise ValueError(
                        f"该图片与已有图片重复（哈希 {file_hash[:12]}…），"
                        f"已有文件: {existing.image_id}，不允许重复加入"
                    )

        image_id = self._new_image_id(source)
        suffix = self._detect_suffix(image_bytes)
        directory = self._gallery_dir if source == GALLERY_SOURCE else self._tmp_dir
        file_path = directory / f"{image_id}.{suffix}"
        file_path.write_bytes(image_bytes)
        return await self._upsert_record(
            image_id,
            source=source,
            file_path=file_path,
            prompt=prompt,
            description=description,
            file_hash=file_hash,
            image_source=image_source,
        )

    async def _load_chat_image_bytes(self, *, message_id: int, image_index: int) -> bytes:
        if image_index <= 0:
            raise ValueError("image_index 必须大于 0")
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
        if image_index > len(image_segments):
            raise LookupError(f"消息 {message_id} 没有第 {image_index} 张图片")
        segment_data = image_segments[image_index - 1].get("data") or {}
        if not isinstance(segment_data, dict):
            raise LookupError(f"消息 {message_id} 的图片段无效")
        return await self._download_image_segment(segment_data)

    async def _download_image_segment(self, data: dict[str, Any]) -> bytes:
        url = data.get("url")
        if isinstance(url, str) and url.strip():
            return await self._download_image_ref(url)

        file_name = data.get("file")
        if not isinstance(file_name, str) or not file_name.strip():
            raise LookupError("图片段缺少 url/file")
        result = await self._call_api_with_timeout("get_image", {"file": file_name})
        img_data = result.get("data") if isinstance(result, dict) else None
        if isinstance(img_data, dict):
            img_ref = img_data.get("file") or img_data.get("url")
            if isinstance(img_ref, str) and img_ref.strip():
                return await self._download_image_ref(img_ref)
        return await self._download_image_ref(file_name)

    async def _download_image_ref(self, ref: str) -> bytes:
        ref = ref.strip()
        if ref.startswith("base64://"):
            return base64.b64decode(ref[9:])
        if ref.startswith("file:///"):
            return Path(ref[8:]).read_bytes()
        if ref.startswith("file://"):
            return Path(ref[7:]).read_bytes()
        if ref.startswith(("http://", "https://")):
            response = await self._client.get(ref)
            response.raise_for_status()
            return response.content
        path = Path(ref)
        if path.exists() and path.is_file():
            return path.read_bytes()
        raise LookupError("无法下载图片内容")

    async def _upsert_record(
        self,
        image_id: str,
        *,
        source: str,
        file_path: Path,
        prompt: str | None,
        description: str | None,
        file_hash: str | None = None,
        image_source: str | None = None,
    ) -> CreatorImageRecord:
        if file_hash is None:
            image_bytes = file_path.read_bytes()
            file_hash = hashlib.sha256(image_bytes).hexdigest()
        mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
        width, height = self._read_dimensions(file_path)
        effective_description = await self._resolve_description(
            image_id=image_id,
            file_path=file_path,
            explicit_description=description,
        )
        async with self._uow_factory() as uow:
            record = await uow.creator_images.set(
                image_id,
                source=source,
                file_hash=file_hash,
                file_path=str(file_path),
                prompt=prompt,
                description=effective_description,
                mime_type=mime_type,
                original_width=width,
                original_height=height,
                image_source=image_source,
            )
            await uow.commit()
            return record

    async def _resolve_description(
        self,
        *,
        image_id: str,
        file_path: Path,
        explicit_description: str | None,
    ) -> str | None:
        explicit = (explicit_description or "").strip()
        if explicit:
            file_path.with_suffix(".txt").write_text(explicit, encoding="utf-8")
            return explicit

        sidecar_text = _read_sidecar_description(file_path)
        if sidecar_text:
            return sidecar_text

        existing = await self._get_existing(image_id)
        db_text = (existing.description or "").strip() if existing and existing.description else ""
        if db_text:
            file_path.with_suffix(".txt").write_text(db_text, encoding="utf-8")
            return db_text

        parsed = await self._parse_local_image(file_path)
        file_path.with_suffix(".txt").write_text(parsed, encoding="utf-8")
        return parsed

    async def _sync_image_sidecars(self, *, source: str | None = None) -> None:
        records = await self._list_image_records(source=source, limit=9999)
        all_records = records if source is None else await self._list_image_records(source=None, limit=9999)
        descriptions_by_hash = {
            record.file_hash: record.description
            for record in all_records
            if record.file_hash and record.description
        }
        known_paths = {str(Path(record.file_path).resolve()) for record in all_records}
        disk_files = [
            (disk_source, path)
            for disk_source, path in self._iter_creator_image_files()
            if source is None or disk_source == source
        ]
        if not records:
            records = []

        async with self._uow_factory() as uow:
            for record in records:
                file_path = Path(record.file_path)
                if not file_path.exists() or not file_path.is_file():
                    continue

                prepared = prepare_local_image(file_path)
                txt_text = _read_sidecar_description(file_path)
                if txt_text:
                    description = txt_text
                else:
                    db_text = (record.description or "").strip()
                    if db_text:
                        description = db_text
                        file_path.with_suffix(".txt").write_text(description, encoding="utf-8")
                    else:
                        description = await self._parse_local_image(file_path)
                        file_path.with_suffix(".txt").write_text(description, encoding="utf-8")
                descriptions_by_hash[prepared.file_hash] = description

                await uow.creator_images.set(
                    record.image_id,
                    source=record.source,
                    file_hash=prepared.file_hash,
                    file_path=str(file_path),
                    prompt=record.prompt,
                    description=description,
                    mime_type=prepared.mime_type,
                    original_width=prepared.original_width,
                    original_height=prepared.original_height,
                    image_source=record.image_source,
                )

            for disk_source, file_path in disk_files:
                resolved_path = str(file_path.resolve())
                if resolved_path in known_paths:
                    continue

                prepared = prepare_local_image(file_path)
                txt_text = _read_sidecar_description(file_path)
                same_hash_description = descriptions_by_hash.get(prepared.file_hash)
                if txt_text:
                    description = txt_text
                elif same_hash_description:
                    description = same_hash_description
                    file_path.with_suffix(".txt").write_text(description, encoding="utf-8")
                else:
                    description = await self._parse_local_image(file_path)
                    file_path.with_suffix(".txt").write_text(description, encoding="utf-8")
                descriptions_by_hash[prepared.file_hash] = description

                image_id = self._image_id_from_file(disk_source, file_path)
                await uow.creator_images.set(
                    image_id,
                    source=disk_source,
                    file_hash=prepared.file_hash,
                    file_path=str(file_path),
                    prompt=None,
                    description=description,
                    mime_type=prepared.mime_type,
                    original_width=prepared.original_width,
                    original_height=prepared.original_height,
                    image_source="部署者提供",
                )
            await uow.commit()

    def _iter_creator_image_files(self) -> list[tuple[str, Path]]:
        files: list[tuple[str, Path]] = []
        for source, directory in ((TMP_SOURCE, self._tmp_dir), (GALLERY_SOURCE, self._gallery_dir)):
            if not directory.exists():
                continue
            for child in sorted(directory.iterdir()):
                if child.is_file() and child.suffix.lower() in _IMAGE_EXTENSIONS:
                    files.append((source, child))
        return files

    def _image_id_from_file(self, source: str, file_path: Path) -> str:
        stem = file_path.stem.strip()
        if source == TMP_SOURCE and stem.startswith("tmp_"):
            return stem
        if source == GALLERY_SOURCE and stem.startswith("g_"):
            return stem
        return self._new_image_id(source)

    async def _parse_local_image(self, file_path: Path) -> str:
        if self._vision_provider is None:
            return "[未配置视觉模型]"
        try:
            prepared = prepare_local_image(file_path)
            image_url = f"data:{prepared.mime_type};base64,{base64.b64encode(prepared.image_bytes).decode('utf-8')}"
            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请用中文简洁描述这张图片的内容，包括文字、主体、动作和情绪。最多100个字。",
                        },
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ]
            response = await asyncio.wait_for(
                self._vision_provider.chat(messages),
                timeout=self._get_vision_timeout_seconds(),
            )
            content = response.get("content", "")
            text = content.strip() if isinstance(content, str) else str(content).strip()
            return text or "[解析失败]"
        except Exception as exc:
            self._logger.error("图库图片解析失败", file=str(file_path), error=str(exc))
            return "[解析失败]"

    async def _get_existing(self, image_id: str) -> CreatorImageRecord | None:
        normalized = image_id.strip()
        if ":" in normalized:
            normalized = normalized.split(":", 1)[1]
        async with self._uow_factory() as uow:
            return await uow.creator_images.get(normalized)

    async def _ensure_gallery_capacity(self) -> None:
        async with self._uow_factory() as uow:
            count = await uow.creator_images.count(source=GALLERY_SOURCE)
        if count >= self._config.gallery_capacity:
            raise ValueError(f"图库容量已满（{self._config.gallery_capacity}）")

    async def _get_reference_by_number(self, reference_id: int) -> CreatorImageRecord | None:
        if reference_id <= 0:
            return None
        # list_images with a large limit to ensure we get the reference
        references = await self.list_images(source=GALLERY_SOURCE, limit=9999, offset=0)
        if reference_id > len(references):
            return None
        return references[reference_id - 1]

    async def _resolve_reference(self, ref_str: str, *, conv_id: str = "") -> str | None:
        """解析参考图字符串，返回 base64 data URL。"""
        ref = ref_str.strip()
        if not ref:
            return None

        if ref.lstrip("-").isdigit() and int(ref) > 0:
            record = await self._get_reference_by_number(int(ref))
            if record is None:
                raise LookupError(f"参考图编号 {ref} 不存在")
            return self._image_data_url(Path(record.file_path), record.mime_type)

        if ":" in ref:
            prefix, _, value = ref.partition(":")
            prefix = prefix.lower().strip()
            value = value.strip()

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
                path = Path(value)
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

        raise LookupError(f"无法解析参考图: {ref}")

    async def resolve_source_to_path(self, source: str) -> Path:
        """将 source 描述符解析为本地文件路径。

        用于 ImagePoolSkill 的 put 操作，下载到临时目录并返回路径。

        支持的格式:
          - chat:<msg_id>:<img_index>
          - gallery:<编号>
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
            if not value.lstrip("-").isdigit() or int(value) <= 0:
                raise ValueError(f"图库编号无效: {value}")
            record = await self._get_reference_by_number(int(value))
            if record is None:
                raise LookupError(f"图库编号 {value} 不存在")
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
            response = await self._client.get(value)
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
            path.write_bytes(response.content)
            return path

        if prefix == "file":
            path = Path(value)
            if not path.is_file():
                raise FileNotFoundError(f"文件不存在: {value}")
            return path

        raise ValueError(f"不支持的 source 格式: {source}")

    async def _download_as_data_url(self, url: str) -> str:
        response = await self._client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/png")
        mime = content_type.split(";")[0].strip()
        b64 = base64.b64encode(response.content).decode("utf-8")
        return f"data:{mime};base64,{b64}"

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
        response = await self._client.get(url)
        response.raise_for_status()
        return response.content

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


def _record_payload(record: CreatorImageRecord) -> dict[str, Any]:
    description = record.description or _read_sidecar_description(record.file_path)
    return {
        "image_id": record.image_id,
        "source": record.source,
        "file_path": record.file_path,
        "prompt": record.prompt,
        "description": description,
        "mime_type": record.mime_type,
        "width": record.original_width,
        "height": record.original_height,
    }

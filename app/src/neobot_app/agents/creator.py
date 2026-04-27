"""Creator agent and tools."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from contextvars import ContextVar
import hashlib
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx
from PIL import Image

from neobot_adapter import OneBotAdapter
from neobot_chat import Agent, get_registered_model
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.memory import CreatorImageRecord
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory

from neobot_app.core import DATA_DIR
from neobot_app.message.image_pipeline import prepare_local_image

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import AgentCreator
    from neobot_app.emoji.service import EmojiService

EXPOSED_TO_MAIN_AGENT_NAME = "creator"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "绘图与图片资产管理。可AI绘图（支持参考图/垫图/图生图）、从聊天导入图片、"
    "管理图库（列表/搜索/添加/替换/更新/删除/重命名）、"
    "管理表情包（列表/搜索/添加/更新/重命名）、发送图片到群聊/私聊。"
    "涉及图片保存、导入图库/表情包、发送图片的任务均委托它；"
    "任务中指代聊天图片时，它可通过聊天上下文自行判断。"
)

# 同级 sub agent 描述，用于识别任务是否应委托给其他 agent
PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注/聊天记录、解析用户头像、调整好感度。\n"
    "- chat_interaction: 聊天互动、群管理（设管理员/禁言/踢人/群名片/头衔等）、好友管理（备注/分组/删除/点赞等）、发送表情包。\n"
    "- image_parse: 仅按需求解析图片内容，不保存、不导入、不管理图库/表情包。\n"
    "如果收到的任务明显属于其他 agent 的职责（如群管理/好友管理/头像解析/图片内容解析），直接告知主Agent该委托给对应的 agent，不要越权处理。"
)

TMP_SOURCE = "tmp"
GALLERY_SOURCE = "gallery"
DEFAULT_IMAGE_SIZE = "512x512"
DEFAULT_OUTPUT_FORMAT = "png"
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_CREATOR_CHAT_CONTEXT: ContextVar[str] = ContextVar("creator_chat_context", default="")

def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }

def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

def _read_sidecar_description(file_path: str | Path) -> str | None:
    """读取与图片同名的 .txt 文件作为描述，不存在则返回 None。"""
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


@dataclass(frozen=True)
class CreatorAgentConfig:
    enabled: bool = False
    gallery_capacity: int = 10
    gallery_page_size: int = 50
    emoji_page_size: int = 50
    allow_emoji_add: bool = False
    allow_emoji_delete: bool = False

    @classmethod
    def from_schema(cls, config: "AgentCreator | None") -> "CreatorAgentConfig":
        if config is None:
            return cls()
        gallery = getattr(config, "gallery", None)
        emoji = getattr(config, "emoji", None)
        return cls(
            enabled=bool(getattr(config, "enabled", False)),
            gallery_capacity=max(int(getattr(gallery, "capacity", 10) or 0), 0),
            gallery_page_size=max(int(getattr(gallery, "page_size", 50) or 1), 1),
            emoji_page_size=max(int(getattr(emoji, "page_size", 50) or 1), 1),
            allow_emoji_add=bool(getattr(emoji, "allow_add", False)),
            allow_emoji_delete=bool(getattr(emoji, "allow_delete", False)),
        )

class CreatorImageService:
    """Generate, store, and send Creator Agent images."""

    _CLEANUP_INTERVAL_SECONDS = 300

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        adapter: OneBotAdapter,
        config: CreatorAgentConfig,
        data_dir: Path = DATA_DIR,
        model_name: str = "creator_image_model",
        emoji_service: "EmojiService | None" = None,
        vision_provider: Provider | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._adapter = adapter
        self._config = config
        self._logger = logger or NullLogger()
        self._emoji_service = emoji_service
        self._vision_provider = vision_provider
        self._model = get_registered_model(model_name)
        self._base_dir = data_dir / "creator"
        self._tmp_dir = self._base_dir / "tmp"
        self._gallery_dir = self._base_dir / "gallery"
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

    async def generate_image(
        self,
        *,
        prompt: str,
        references: list[str] | None = None,
        reference_id: int | None = None,
        negative_prompt: str | None = None,
        image_size: str | None = None,
        seed: int | None = None,
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
                url = await self._resolve_reference(ref_str.strip())
                if url:
                    resolved_data_urls.append(url)

        if len(resolved_data_urls) == 1:
            payload["image"] = resolved_data_urls[0]
        elif len(resolved_data_urls) > 1:
            payload["image"] = resolved_data_urls

        response = await self._client.post("/images/generations", json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            self._logger.error(
                "生图接口返回错误状态码",
                status=response.status_code,
                body=response.text[:500],
            )
            raise
        try:
            image_bytes = await self._extract_image_bytes(response.json())
        except ValueError:
            self._logger.error(
                "生图接口返回数据解析失败",
                status=response.status_code,
                body=response.text[:500],
            )
            raise
        return await self._save_image_bytes(
            image_bytes,
            source=TMP_SOURCE,
            prompt=prompt,
            description=None,
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

        segments: list[dict[str, Any]] = [
            {"type": "image", "data": {"file": f"file:///{path.as_posix()}"}},
        ]
        await self._adapter.send(conversation_ref, segments)

    async def import_chat_image(
        self,
        *,
        message_id: int,
        image_index: int = 1,
        target: str = TMP_SOURCE,
        description: str | None = None,
        name: str | None = None,
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
    ) -> CreatorImageRecord:
        file_hash = hashlib.sha256(image_bytes).hexdigest()
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
        )

    async def _load_chat_image_bytes(self, *, message_id: int, image_index: int) -> bytes:
        if image_index <= 0:
            raise ValueError("image_index 必须大于 0")
        result = await self._adapter.call_api("get_msg", {"message_id": message_id})
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
        result = await self._adapter.call_api("get_image", {"file": file_name})
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
            response = await self._vision_provider.chat(messages)
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

    async def _resolve_reference(self, ref_str: str) -> str | None:
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

class CreatorToolExecutor(ToolExecutor):
    """Tool executor for Creator Agent operations."""

    def __init__(
        self,
        service: CreatorImageService,
        *,
        config: CreatorAgentConfig | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._service = service
        self._config = config or CreatorAgentConfig()
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        tools = [
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射。仅在任务缺少群号、真实 message_id、或需要判断「这张图/刚才那张图/被回复的消息」时调用。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "generate_image",
                "根据提示词调用生图模型生成图片，生成结果会保存为临时图片。"
                "可通过 references 提供参考图片（图生图/垫图），支持多张混合来源。",
                {
                    "properties": {
                        "prompt": {"type": "string", "description": "要生成的图片内容"},
                        "references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "可选，参考图片列表（可混合多种来源）：\n"
                                "- 数字 'N'：list_references 返回的图库参考图编号\n"
                                "- 'g_xxx' 或直接 image_id：图库/临时图\n"
                                "- 'emoji:N'：表情包编号\n"
                                "- 'url:https://...'：外部图片链接\n"
                                "- 'file:/path/to/img'：本地文件路径\n"
                                "- 'chat:message_id' 或 'chat:message_id:index'：聊天图片"
                            ),
                        },
                        "negative_prompt": {"type": "string", "description": "可选，负向提示词"},
                        "image_size": {"type": "string", "description": "可选，例如 512x512 或 1024x1024"},
                        "seed": {"type": "integer", "description": "可选，随机种子"},
                    },
                    "required": ["prompt"],
                },
            ),
            _tool_def(
                "gallery_list",
                "查看临时图片和图库图片。每页默认显示配置数量的图片；图片过多时可翻页。",
                {
                    "properties": {
                        "source": {
                            "type": "string",
                            "enum": ["tmp", "gallery"],
                            "description": "可选，筛选来源。不填则显示全部。",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "可选，翻页偏移量，默认 0。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "可选，每页数量，默认使用配置值。",
                        },
                    },
                    "required": [],
                },
            ),
            _tool_def(
                "gallery_search",
                "在图库/临时图片中搜索。描述信息中匹配关键词的图片。当图库图片数量过多（如200以上）时建议使用搜索而非直接列表查看。",
                {
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词，匹配图片描述和提示词。",
                        },
                        "source": {
                            "type": "string",
                            "enum": ["tmp", "gallery"],
                            "description": "可选，筛选来源。",
                        },
                        "offset": {
                            "type": "integer",
                            "description": "可选，翻页偏移量，默认 0。",
                        },
                    },
                    "required": ["keyword"],
                },
            ),
            _tool_def(
                "gallery_add",
                "将临时图片加入图库。必须用 name 参数为图片命名。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "临时图片 ID，可带 tmp: 前缀"},
                        "description": {"type": "string", "description": "可选，图库描述"},
                        "name": {
                            "type": "string",
                            "description": "图片文件名（不含后缀）。必须提供，根据图片内容命名。仅允许字母、数字、下划线和连字符。不确定名称时先查上下文或问主Agent。",
                        },
                    },
                    "required": ["image_id", "name"],
                },
            ),
            _tool_def(
                "gallery_replace",
                "用一张临时或图库图片替换指定图库图片的文件内容。",
                {
                    "properties": {
                        "target_id": {"type": "string", "description": "要替换的图库图片 ID"},
                        "source_id": {"type": "string", "description": "来源图片 ID"},
                    },
                    "required": ["target_id", "source_id"],
                },
            ),
            _tool_def(
                "gallery_update",
                "修改临时图片或图库图片的描述信息，并同步写入同名 txt 与数据库。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图片 ID，可带 tmp: 或 gallery: 前缀"},
                        "description": {"type": "string", "description": "新的图片描述"},
                    },
                    "required": ["image_id", "description"],
                },
            ),
            _tool_def(
                "gallery_delete",
                "删除图库图片。",
                {
                    "properties": {"image_id": {"type": "string", "description": "图库图片 ID"}},
                    "required": ["image_id"],
                },
            ),
            _tool_def(
                "gallery_rename",
                "重命名图库图片文件。image_id 不变，仅修改磁盘上的图片文件名和对应的 .txt 描述文件。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图库图片 ID，可带 gallery: 前缀"},
                        "new_name": {
                            "type": "string",
                            "description": "新文件名（不含后缀）。仅允许字母、数字、下划线和连字符。",
                        },
                    },
                    "required": ["image_id", "new_name"],
                },
            ),
            _tool_def(
                "gallery_send",
                "发送图片到指定群聊/私聊，只发送图片不附带文字。必须提供 group_id 或 user_id。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图片 ID"},
                        "source": {"type": "string", "description": "可选，tmp 或 gallery"},
                        "group_id": {"type": "string", "description": "目标群号"},
                        "user_id": {"type": "string", "description": "目标 QQ 号"},
                    },
                    "required": ["image_id"],
                },
            ),
            _tool_def("list_references", "列出可作为参考图的图库图片。", {"properties": {}}),
            _tool_def(
                "import_chat_image",
                "从聊天消息中导入图片到临时图或图库；表情包导入需配置允许。当 target 为 gallery 或 emoji 时，必须用 name 参数为图片命名。",
                {
                    "properties": {
                        "message_id": {"type": "integer", "description": "真实消息 ID，不是聊天编号"},
                        "image_index": {"type": "integer", "description": "消息中的第几张图片，默认 1"},
                        "target": {
                            "type": "string",
                            "enum": self._import_targets(),
                            "description": "导入目标：tmp、gallery，允许时可用 emoji",
                        },
                        "description": {"type": "string", "description": "可选描述"},
                        "name": {
                            "type": "string",
                            "description": "图片文件名（不含后缀）。存入图库/表情包时必须提供。仅允许字母、数字、下划线和连字符。不确定名称时先查上下文或问主Agent。",
                        },
                    },
                    "required": ["message_id"],
                },
            ),
            _tool_def(
                "emoji_list",
                "查看当前表情包列表。按使用次数从少到多排列（使用次数均衡器），优先展示不常用的表情包。每页显示配置数量的表情包；表情包过多时可翻页。",
                {
                    "properties": {
                        "offset": {
                            "type": "integer",
                            "description": "可选，翻页偏移量，默认 0。",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "可选，每页数量，默认使用配置值。",
                        },
                    },
                    "required": [],
                },
            ),
            _tool_def(
                "emoji_search",
                "在表情包中搜索。按描述和文件名匹配关键词，结果按使用次数从少到多排列。当表情包数量过多（如200以上）时建议使用搜索。",
                {
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词，匹配表情包描述和文件名。",
                        },
                    },
                    "required": ["keyword"],
                },
            ),
            _tool_def(
                "emoji_update",
                "按编号修改表情包描述信息，并同步写入同名 txt 与数据库。",
                {
                    "properties": {
                        "number": {"type": "integer", "description": "表情包编号"},
                        "description": {"type": "string", "description": "新的表情包描述"},
                    },
                    "required": ["number", "description"],
                },
            ),
            _tool_def(
                "emoji_rename",
                "重命名表情包文件。编号不变，仅修改磁盘上的文件名和对应的 .txt 描述文件。",
                {
                    "properties": {
                        "number": {"type": "integer", "description": "表情包编号"},
                        "new_name": {
                            "type": "string",
                            "description": "新文件名（不含后缀）。仅允许字母、数字、下划线和连字符。",
                        },
                    },
                    "required": ["number", "new_name"],
                },
            ),
        ]
        if self._config.allow_emoji_add:
            tools.append(
                _tool_def(
                    "emoji_add",
                    "把已有临时图/图库图片加入表情包。必须用 name 参数为表情包命名。",
                    {
                        "properties": {
                            "image_id": {"type": "string", "description": "图片 ID"},
                            "description": {"type": "string", "description": "可选表情包描述"},
                            "name": {
                                "type": "string",
                                "description": "表情包文件名（不含后缀）。必须提供，根据图片内容命名。仅允许字母、数字、下划线和连字符。不确定名称时先查上下文或问主Agent。",
                            },
                        },
                        "required": ["image_id", "name"],
                    },
                )
            )
        if self._config.allow_emoji_delete:
            tools.append(
                _tool_def(
                    "emoji_delete",
                    "按编号删除表情包。",
                    {
                        "properties": {
                            "number": {"type": "integer", "description": "表情包编号"},
                        },
                        "required": ["number"],
                    },
                )
            )
        return tools

    async def execute(self, name: str, args: dict) -> str:
        try:
            if name == "get_chat_context":
                return self._get_chat_context()
            if name == "generate_image":
                return await self._generate_image(args)
            if name == "gallery_list":
                return await self._gallery_list(args)
            if name == "gallery_search":
                return await self._gallery_search(args)
            if name == "gallery_add":
                return await self._gallery_add(args)
            if name == "gallery_replace":
                return await self._gallery_replace(args)
            if name == "gallery_update":
                return await self._gallery_update(args)
            if name == "gallery_delete":
                return await self._gallery_delete(args)
            if name == "gallery_rename":
                return await self._gallery_rename(args)
            if name == "gallery_send":
                return await self._gallery_send(args)
            if name == "list_references":
                return await self._list_references()
            if name == "import_chat_image":
                return await self._import_chat_image(args)
            if name == "emoji_list":
                return self._emoji_list(args)
            if name == "emoji_search":
                return self._emoji_search(args)
            if name == "emoji_add":
                return await self._emoji_add(args)
            if name == "emoji_update":
                return await self._emoji_update(args)
            if name == "emoji_delete":
                return await self._emoji_delete(args)
            if name == "emoji_rename":
                return await self._emoji_rename(args)
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})
        return _json({"ok": False, "error": f"未知工具: {name}"})

    async def close(self) -> None:
        await self._service.close()

    def _get_chat_context(self) -> str:
        context = _CREATOR_CHAT_CONTEXT.get("").strip()
        if not context:
            return _json({"ok": False, "error": "当前没有可用的聊天上下文"})
        return _json({"ok": True, "context": context})

    async def _generate_image(self, args: dict[str, Any]) -> str:
        seed = args.get("seed")
        references_raw = args.get("references")
        references: list[str] | None = None
        if isinstance(references_raw, list):
            references = [str(r) for r in references_raw]
        record = await self._service.generate_image(
            prompt=str(args.get("prompt") or ""),
            references=references,
            reference_id=self._optional_int(args.get("reference_id")),
            negative_prompt=self._optional_str(args.get("negative_prompt")),
            image_size=self._optional_str(args.get("image_size")),
            seed=int(seed) if seed is not None else None,
        )
        return _json({"ok": True, "image": self._record_payload(record)})

    async def _gallery_list(self, args: dict[str, Any]) -> str:
        source = self._optional_str(args.get("source"))
        offset = int(args.get("offset", 0) or 0)
        limit = args.get("limit")
        if limit is not None:
            limit = int(limit)
        normalized_source = self._service._normalize_source(source) if source else None
        images = await self._service.list_images(source=normalized_source, limit=limit, offset=offset)
        total = await self._service.count_images(source=normalized_source)
        result: dict[str, Any] = {
            "ok": True,
            "images": [self._record_payload(item) for item in images],
            "total": total,
            "offset": offset,
        }
        limit_val = limit if limit is not None else self._config.gallery_page_size
        if offset + limit_val < total:
            result["next_offset"] = offset + limit_val
            result["has_more"] = True
        return _json(result)

    async def _gallery_search(self, args: dict[str, Any]) -> str:
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return _json({"ok": False, "error": "keyword 不能为空"})
        source = self._optional_str(args.get("source"))
        offset = int(args.get("offset", 0) or 0)
        normalized_source = self._service._normalize_source(source) if source else None
        images = await self._service.search_images(
            keyword,
            source=normalized_source,
            offset=offset,
        )
        return _json({
            "ok": True,
            "keyword": keyword,
            "images": [self._record_payload(item) for item in images],
            "offset": offset,
            "has_more": len(images) >= self._config.gallery_page_size,
        })

    async def _gallery_add(self, args: dict[str, Any]) -> str:
        record = await self._service.gallery_add(
            image_id=str(args.get("image_id") or ""),
            description=self._optional_str(args.get("description")),
            name=self._optional_str(args.get("name")),
        )
        return _json({"ok": True, "image": self._record_payload(record)})

    async def _gallery_replace(self, args: dict[str, Any]) -> str:
        record = await self._service.gallery_replace(
            target_id=str(args.get("target_id") or ""),
            source_id=str(args.get("source_id") or ""),
        )
        return _json({"ok": True, "image": self._record_payload(record)})

    async def _gallery_update(self, args: dict[str, Any]) -> str:
        record = await self._service.update_image_description(
            image_id=str(args.get("image_id") or ""),
            description=str(args.get("description") or ""),
        )
        return _json({"ok": True, "image": self._record_payload(record)})

    async def _gallery_delete(self, args: dict[str, Any]) -> str:
        deleted = await self._service.gallery_delete(image_id=str(args.get("image_id") or ""))
        return _json({"ok": True, "deleted": deleted})

    async def _gallery_rename(self, args: dict[str, Any]) -> str:
        record = await self._service.gallery_rename(
            image_id=str(args.get("image_id") or ""),
            new_name=str(args.get("new_name") or ""),
        )
        return _json({"ok": True, "image": self._record_payload(record)})

    async def _gallery_send(self, args: dict[str, Any]) -> str:
        image_id = str(args.get("image_id") or "")
        await self._service.send_image(
            image_id=image_id,
            source=self._optional_str(args.get("source")),
            group_id=self._optional_str(args.get("group_id")),
            user_id=self._optional_str(args.get("user_id")),
        )
        return _json({"ok": True, "sent": True, "image_id": image_id})

    async def _list_references(self) -> str:
        # 获取全部图库图片作为参考图（不受分页限制）
        images = await self._service.list_images(source=GALLERY_SOURCE, limit=9999, offset=0)
        references = [
            {"number": index, **self._record_payload(item)}
            for index, item in enumerate(images, start=1)
        ]
        return _json({"ok": True, "references": references})

    async def _import_chat_image(self, args: dict[str, Any]) -> str:
        result = await self._service.import_chat_image(
            message_id=int(args.get("message_id") or 0),
            image_index=int(args.get("image_index") or 1),
            target=str(args.get("target") or TMP_SOURCE),
            description=self._optional_str(args.get("description")),
            name=self._optional_str(args.get("name")),
        )
        return _json({"ok": True, **result})

    def _emoji_list(self, args: dict[str, Any]) -> str:
        offset = int(args.get("offset", 0) or 0)
        limit = args.get("limit")
        if limit is not None:
            limit = int(limit)
        emojis = self._service.list_emojis(offset=offset, limit=limit)
        total = self._service.get_emoji_count()
        result: dict[str, Any] = {
            "ok": True,
            "emojis": emojis,
            "total": total,
            "offset": offset,
            "sorted_by": "use_count_asc",
            "usage_balancer": True,
        }
        limit_val = limit if limit is not None else self._config.emoji_page_size
        if offset + limit_val < total:
            result["next_offset"] = offset + limit_val
            result["has_more"] = True
        return _json(result)

    def _emoji_search(self, args: dict[str, Any]) -> str:
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return _json({"ok": False, "error": "keyword 不能为空"})
        emojis = self._service.search_emojis(keyword)
        return _json({
            "ok": True,
            "keyword": keyword,
            "emojis": emojis,
            "sorted_by": "use_count_asc",
            "usage_balancer": True,
        })

    async def _emoji_add(self, args: dict[str, Any]) -> str:
        result = await self._service.add_emoji_from_image(
            image_id=str(args.get("image_id") or ""),
            description=self._optional_str(args.get("description")),
            name=self._optional_str(args.get("name")),
        )
        return _json({"ok": True, **result})

    async def _emoji_update(self, args: dict[str, Any]) -> str:
        emoji = await self._service.update_emoji_description(
            number=int(args.get("number") or 0),
            description=str(args.get("description") or ""),
        )
        return _json({"ok": True, "emoji": emoji})

    async def _emoji_delete(self, args: dict[str, Any]) -> str:
        deleted = await self._service.delete_emoji(number=int(args.get("number") or 0))
        return _json({"ok": True, "deleted": deleted})

    async def _emoji_rename(self, args: dict[str, Any]) -> str:
        emoji = await self._service.rename_emoji(
            number=int(args.get("number") or 0),
            new_name=str(args.get("new_name") or ""),
        )
        return _json({"ok": True, "emoji": emoji})

    @staticmethod
    def _record_payload(record: CreatorImageRecord) -> dict[str, Any]:
        return _record_payload(record)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    def _import_targets(self) -> list[str]:
        targets = [TMP_SOURCE, GALLERY_SOURCE]
        if self._config.allow_emoji_add:
            targets.append("emoji")
        return targets

def build_creator_toolset(
    service: CreatorImageService,
    config: CreatorAgentConfig | None = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = CreatorToolExecutor(service=service, config=config or CreatorAgentConfig(), logger=logger)
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())

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

def _build_system_prompt(config: CreatorAgentConfig) -> str:
    gallery_text = (
        f"图库容量上限为 {config.gallery_capacity}。"
        if config.gallery_capacity > 0
        else "图库管理已禁用，只能生成和发送临时图片。"
    )
    emoji_text = (
        "表情包管理由 agent.creator.emoji.allow_add / allow_delete 控制："
        f"增加={'允许' if config.allow_emoji_add else '禁止'}，"
        f"删除={'允许' if config.allow_emoji_delete else '禁止'}。"
    )
    pagination_text = (
        f"图库每页显示 {config.gallery_page_size} 张，表情包每页显示 {config.emoji_page_size} 个。"
        "图片/表情包过多时使用 offset 参数翻页。"
        "当图库/表情包数量很多（200以上）时，优先使用 gallery_search / emoji_search 搜索，不要逐个翻页查找。"
        "emoji_list 按使用次数从少到多排列（使用次数均衡器），优先展示不常用的表情包。"
    )
    return (
        "你是创作者 Agent，负责生成图片、管理图库/表情包、发送图片。\n"
        "执行任务时优先使用工具，不要假装已经生成或发送图片。\n"
        "生成图片后会得到 image_id；发送图片必须使用 gallery_send，并提供 group_id 或 user_id。\n"
        "\n"
        "【参考图片（references）】\n"
        "生成图片时，如果用户要求以某张图片为参考/参考图/垫图/图生图，使用 generate_image 的 references 参数传入参考图。\n"
        "references 支持同时传入多张参考图，格式如下：\n"
        "  - 图库参考图编号：直接用数字（如 '3'），来自 list_references 返回的编号\n"
        "  - 图库/临时图：用 image_id（如 'g_abc123'），无需加前缀\n"
        "  - 表情包：用 'emoji:<编号>'（如 'emoji:5'）\n"
        "  - 外部链接：用 'url:<URL>'（如 'url:https://example.com/img.jpg'）\n"
        "  - 本地文件：用 'file:<路径>'（如 'file:/data/images/ref.png'）\n"
        "  - 聊天图片：用 'chat:<message_id>' 或 'chat:<message_id>:<image_index>'（index 默认 1）\n"
        "\n"
        "【图片命名（必须遵守）】\n"
        "将图片加入图库（gallery_add）或表情包（emoji_add）时，必须通过 name 参数为图片指定有意义的文件名：\n"
        "  - 如果用户指定了名称，使用用户指定的名称\n"
        "  - 如果用户未指定，根据图片内容生成简短有意义的英文名（如 'sunset_ocean'、'cute_white_cat'）\n"
        "  - 不要使用默认名称或自动生成的名称（如 tmp_xxx、g_xxx、chat_xxx），必须自己命名\n"
        "  - 名称仅含字母、数字、下划线、连字符，不含扩展名，长度不超过 100 字符\n"
        "  - 不确定用什么名称时，先调用 get_chat_context 查看上下文是否有线索\n"
        "  - 如果仍无法确定合适名称，向主Agent询问后再操作\n"
        "  - 图片入库后如需改名，可使用 gallery_rename 或 emoji_rename\n"
        "\n"
        "导入聊天图片时使用真实 message_id；不要把聊天编号当作 message_id。\n"
        "如果任务提到这张图、刚才那张图、回复的图片、聊天编号，或缺少群号/真实 message_id，先调用 get_chat_context 查看主Agent上下文和消息编号映射。\n"
        "如果用户要求把聊天图片加入图库或表情包，不要要求用户重发；先用 get_chat_context 找到对应消息编号和真实 message_id，再用 import_chat_image 导入。\n"
        "如果用户要求修改图库图片或表情包的信息、说明、备注、描述，使用 gallery_update 或 emoji_update。\n"
        "如果用户要求重命名图库图片或表情包，使用 gallery_rename 或 emoji_rename。\n"
        "gallery_send 只发送图片本身，不要附加任何文字或 @ 消息。\n"
        "当你需要更多信息（如群号）才能完成任务时，直接向主 Agent 提问，不要猜测或编造。\n"
        f"{gallery_text}\n"
        f"{emoji_text}\n"
        f"{pagination_text}\n"
        f"{PEER_AGENT_DESCRIPTIONS}\n"
        "输出尽量简短，任务完成后只返回必要结果。"
    )

class CreatorAgent:
    """LLM-backed agent dedicated to image creation operations."""

    def __init__(
        self,
        provider: Provider,
        *,
        service: CreatorImageService,
        config: CreatorAgentConfig | AgentCreator | None = None,
        logger: Logger | None = None,
    ) -> None:
        normalized_config = (
            config if isinstance(config, CreatorAgentConfig) else CreatorAgentConfig.from_schema(config)
        )
        self._service = service
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_creator_toolset(service=service, config=normalized_config, logger=logger)
        self.tool_definitions = self._toolset.definitions()
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(normalized_config),
            logger=logger or NullLogger(),
        )

    async def start(self) -> None:
        await self._service.start()

    async def stop(self) -> None:
        await self._service.stop()

    async def invoke(self, state: State) -> State:
        token = _CREATOR_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            return await self._agent.invoke(state)
        finally:
            _CREATOR_CHAT_CONTEXT.reset(token)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _CREATOR_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _CREATOR_CHAT_CONTEXT.reset(token)

    async def close(self) -> None:
        await self._agent.close()
        await self._service.close()

def build_creator_agent(
    provider: Provider,
    *,
    uow_factory: UnitOfWorkFactory,
    adapter: OneBotAdapter,
    config: CreatorAgentConfig | AgentCreator | None = None,
    emoji_service: "EmojiService | None" = None,
    vision_provider: Provider | None = None,
    logger: Logger | None = None,
) -> CreatorAgent:
    normalized_config = (
        config if isinstance(config, CreatorAgentConfig) else CreatorAgentConfig.from_schema(config)
    )
    service = CreatorImageService(
        uow_factory=uow_factory,
        adapter=adapter,
        config=normalized_config,
        emoji_service=emoji_service,
        vision_provider=vision_provider,
        logger=logger,
    )
    return CreatorAgent(
        provider=provider,
        service=service,
        config=normalized_config,
        logger=logger,
    )

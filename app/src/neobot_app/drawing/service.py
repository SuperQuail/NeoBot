"""图片生成、存储与参考图解析服务。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import mimetypes
import time
from collections.abc import Sequence
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
from neobot_app.message.image_pipeline import (
    prepare_local_image_async,
)
from neobot_app.utils.http import image_http_client, is_local_or_private_url
from neobot_app.utils.media_sender import send_image as _media_send_image

if TYPE_CHECKING:
    from neobot_app.core.file_server import FileServer
    from neobot_app.emoji.service import EmojiService
    from neobot_app.image_pool import ImageStagingPool
    from neobot_contracts.models.memory import EmojiRecord


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


_MAX_REMOTE_FETCH_BYTES = 100 * 1024 * 1024


def _read_sidecar_description(file_path: str | Path) -> str | None:
    """读取图片同名的 .txt 伴生文件获取描述，不存在时返回 None。"""
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
    """生成、存储并发送 Creator Agent 图片。"""

    _CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
    _TMP_MAX_AGE_SECONDS = 12 * 60 * 60

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        adapter: OneBotAdapter,
        config: DrawServiceConfig,
        data_dir: Path = DATA_DIR,
        model_name: str = "",  # 生图模型 key（由 bootstrap 传入 [models.assignments].creator_image_models）
        model_names: Sequence[str] | None = None,
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
        names = tuple(model_names) if model_names else ((model_name,) if model_name else ())
        self._model_names: tuple[str, ...] = tuple(dict.fromkeys(name for name in names if name))
        if not self._model_names:
            raise ValueError("至少需要一个生图模型注册名")
        self._models: dict[str, Any] = {
            name: get_registered_model(name) for name in self._model_names
        }
        self._default_model_name = self._model_names[0]
        self._base_dir = data_dir / "creator"
        self._tmp_dir = self._base_dir / "tmp"
        self._gallery_dir = self._base_dir / "gallery"
        self._markdown_dir = markdown_dir
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self._gallery_dir.mkdir(parents=True, exist_ok=True)
        default_model = self._models[self._default_model_name]
        timeout = default_model.settings.timeout_seconds
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, model in self._models.items():
            model_timeout = float(model.settings.timeout_seconds or timeout)
            self._clients[name] = httpx.AsyncClient(
                base_url=model.base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {model.api_key}"},
                timeout=httpx.Timeout(model_timeout, connect=min(model_timeout, 10.0)),
                trust_env=bool(getattr(model, "use_system_proxy", False)),
            )
        self._model = default_model
        self._client = self._clients[self._default_model_name]
        # 用户可控 URL 下载使用无凭据 client，避免 API Key 外发
        self._public_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
        )
        self._cleanup_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        await self._stop_cleanup_task()
        await self.cleanup_tmp()
        for client in self._clients.values():
            await client.aclose()
        await self._public_client.aclose()

    async def start(self) -> None:
        self._start_cleanup_task()

    async def stop(self) -> None:
        await self._stop_cleanup_task()

    # ------------------------------------------------------------------
    # 生图模型选择（支持配置多个模型/供应商）
    # ------------------------------------------------------------------

    @property
    def default_model_name(self) -> str:
        return self._default_model_name

    @property
    def model_names(self) -> tuple[str, ...]:
        return self._model_names

    def available_models(self) -> list[dict[str, Any]]:
        """可用生图模型清单（供绘图工具描述与面板展示）。"""
        return [
            {
                "name": name,
                "index": index,
                "description": self._models[name].description,
                "provider": self._models[name].provider_name,
                "model_name": self._models[name].model_name,
                "default": name == self._default_model_name,
            }
            for index, name in enumerate(self._model_names)
        ]

    def resolve_model_name(self, selector: str | None) -> str:
        """把 Agent 给出的选择（序号 / 注册名 / 描述 / 供应商 / 模型名）解析为注册名。"""
        if selector is None:
            return self._default_model_name
        raw = str(selector).strip()
        if not raw:
            return self._default_model_name
        if raw in self._models:
            return raw
        if raw.isdigit():
            index = int(raw)
            if 0 <= index < len(self._model_names):
                return self._model_names[index]
        lowered = raw.casefold()
        for name in self._model_names:
            model = self._models[name]
            candidates = {
                str(model.description).casefold(),
                str(model.provider_name).casefold(),
                str(model.model_name).casefold(),
            }
            if lowered in candidates:
                return name
        for name in self._model_names:
            model = self._models[name]
            if lowered in str(model.model_name).casefold() or lowered in str(model.provider_name).casefold():
                return name
        available = "、".join(
            f"{index}:{self._models[name].description or name}"
            for index, name in enumerate(self._model_names)
        )
        raise ValueError(f"未知生图模型选择 {selector!r}；可用: {available}")

    def _client_for(self, model_name: str) -> tuple[Any, httpx.AsyncClient]:
        return self._models[model_name], self._clients[model_name]

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    def _get_vision_timeout_seconds(self) -> float:
        return 60.0

    async def _read_limited(self, response: Any) -> bytes:
        """分块读取响应体，超过上限即中止。"""
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                declared = 0
            if declared > _MAX_REMOTE_FETCH_BYTES:
                raise ValueError(
                    f"下载内容过大（{declared} 字节），超过上限 {_MAX_REMOTE_FETCH_BYTES} 字节"
                )
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > _MAX_REMOTE_FETCH_BYTES:
                raise ValueError(
                    f"下载内容过大，超过上限 {_MAX_REMOTE_FETCH_BYTES} 字节，已中止"
                )
            chunks.append(chunk)
        return b"".join(chunks)

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
        """删除数据库中文件已不存在的记录，更新文件已重命名的记录，并对各目录内哈希重复的文件去重（保留最新）。"""
        disk_files: set[str] = set()

        # 逐目录去重：同一目录内哈希相同的文件只保留最新的
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
                    prepared = await prepare_local_image_async(child)
                    hash_to_files.setdefault(prepared.file_hash, []).append(child)
                except Exception:
                    continue

            for file_hash, files in hash_to_files.items():
                if len(files) <= 1:
                    continue
                files.sort(key=lambda f: f.stat().st_mtime)
                keeper = files[-1]
                for dup in files[:-1]:
                    self._logger.info(
                        f"图库去重: 保留较新文件 {keeper.name}，删除重复文件 {dup.name}"
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

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_stale_records()
                await self._sync_image_sidecars()
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
        """删除 tmp 目录中的全部文件，并移除对应的数据库记录。"""
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
        model: str | None = None,
    ) -> CreatorImageRecord:
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt 不能为空")

        resolved_name = self.resolve_model_name(model)
        registered_model, client = self._client_for(resolved_name)

        payload: dict[str, Any] = {
            "model": registered_model.model_name,
            "prompt": prompt,
            "image_size": image_size or DEFAULT_IMAGE_SIZE,
        }
        payload.update(registered_model.settings.extra_body or {})
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt
        if seed is not None:
            payload["seed"] = seed

        resolved_data_urls: list[str] = []
        if reference_id is not None:
            ref = await self._get_reference_by_gallery_no(reference_id)
            if ref is None:
                raise LookupError(f"图库编号 {reference_id} 不存在")
            resolved_data_urls.append(self._image_data_url(Path(ref.file_path), ref.mime_type))
        if references:
            for ref_str in references:
                url = await self._resolve_reference(ref_str.strip(), conv_id=conv_id)
                if url:
                    resolved_data_urls.append(url)

        settings = registered_model.settings
        image_api = str(getattr(settings, "image_api", "auto") or "auto").strip().lower()
        if image_api not in {"auto", "edits", "generations"}:
            image_api = "auto"
        reference_param = str(
            getattr(settings, "image_reference_param", "image") or "image"
        ).strip() or "image"

        response: httpx.Response | None = None
        if resolved_data_urls and image_api in {"auto", "edits"}:
            # 参考图必须走 /images/edits（multipart）：部分中转站会静默忽略
            # /images/generations 上的 image 字段，导致「参考图不生效」
            response = await self._post_edits(
                client,
                registered_model,
                payload=payload,
                references=resolved_data_urls,
            )
            if response is not None and response.status_code in {400, 404, 405}:
                if image_api == "edits":
                    pass  # 显式指定 edits 时不回退，交给下方 raise_for_status 报错
                else:
                    self._logger.warning(
                        f"参考图接口 /images/edits 返回 {response.status_code}，"
                        f"回退到 /images/generations（字段 {reference_param}）"
                    )
                    response = None
        if response is None:
            if resolved_data_urls:
                # 复数形式的字段名（images / image_urls / reference_images）用数组，
                # 单数形式（image / image_url / input_image）单张时用字符串
                payload[reference_param] = (
                    list(resolved_data_urls)
                    if len(resolved_data_urls) > 1 or reference_param.endswith("s")
                    else resolved_data_urls[0]
                )
            response = await client.post("/images/generations", json=payload)
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

    async def process_image(
        self,
        *,
        image: str,
        operation: str,
        width: int | None = None,
        height: int | None = None,
        crop_box: list[int] | None = None,
        quality: int | None = None,
        background_color: str | None = None,
        image_source: str | None = None,
        conv_id: str = "",
    ) -> CreatorImageRecord:
        """本地图片后处理:缩放 / 裁切 / 格式转换 / 去底透明。

        image 支持图片 ID(image_id,如 tmp_xxx / g_xxx)或来源描述符
        (gallery:<图库编号> / emoji:<编号> / file:<路径> / url:<URL> / chat:<msg>:<idx>)。
        operation:
          - resize: 等比缩放;只给 width 或 height 时按单边等比,
            两者都给时精确拉伸
          - crop: 按 crop_box=[left, top, right, bottom] 裁切
          - to_png / to_jpeg: 格式转换(quality 仅 jpeg 生效)
          - remove_background: 纯色背景去底为透明 PNG
            (background_color 指定键色,如 "#00ff00";不指定则自动从边框采样)
        结果保存到临时目录,返回新图片 ID。
        """
        source_path = await self._resolve_process_source(image, conv_id=conv_id)
        operation = (operation or "").strip().lower()
        allowed = {"resize", "crop", "to_png", "to_jpeg", "remove_background"}
        if operation not in allowed:
            raise ValueError(
                f"不支持的操作: {operation}(可选: {', '.join(sorted(allowed))})"
            )

        from PIL import Image, ImageOps

        with Image.open(source_path) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened).convert("RGB")
            if operation == "resize":
                if width and height:
                    img = img.resize((int(width), int(height)), Image.Resampling.LANCZOS)
                elif width or height:
                    target = (int(width) if width else None, int(height) if height else None)
                    img = _resize_keep_ratio(img, target)
            elif operation == "crop":
                if not crop_box or len(crop_box) != 4:
                    raise ValueError("crop 操作需要 crop_box=[left, top, right, bottom]")
                left, top, right, bottom = (int(v) for v in crop_box)
                if right <= left or bottom <= top:
                    raise ValueError("crop_box 必须满足 right > left 且 bottom > top")
                img = img.crop((left, top, right, bottom))
            elif operation == "remove_background":
                img = _remove_background(img, background_color=background_color)

            output_format = "PNG"
            if operation == "to_jpeg":
                output_format = "JPEG"
                img = img.convert("RGB")
            elif operation == "remove_background":
                output_format = "PNG"

            buffer = io.BytesIO()
            save_kwargs: dict[str, Any] = {}
            if output_format == "JPEG" and quality:
                save_kwargs["quality"] = max(1, min(int(quality), 100))
            img.save(buffer, format=output_format, **save_kwargs)
            image_bytes = buffer.getvalue()

        return await self._save_image_bytes(
            image_bytes,
            source=TMP_SOURCE,
            prompt=f"process_image({operation})",
            description=None,
            image_source=image_source,
        )

    async def _resolve_process_source(self, image: str, *, conv_id: str = "") -> Path:
        """解析 process_image 的输入:图片 ID 或来源描述符。"""
        image = str(image or "").strip()
        if not image:
            raise ValueError("缺少 image 参数")
        # 先尝试按图片 ID 查找(DB 记录,覆盖 tmp_xxx / g_xxx)
        record = await self._get_existing(image)
        if record is not None and Path(record.file_path).is_file():
            return Path(record.file_path)
        # 再尝试来源描述符(gallery: / emoji: / file: / url: / chat:)
        if ":" in image:
            prefix = image.partition(":")[0].lower().strip()
            if prefix in ("gallery", "g", "emoji", "e", "file", "url", "chat"):
                return await self.resolve_source_to_path(image)
        raise LookupError(f"图片不存在或无法解析: {image}")

    async def list_images(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        normalized = self._normalize_source(source) if source else None
        self._start_cleanup_task()
        return await self._list_image_records(source=normalized, limit=limit, offset=offset)

    async def count_images(self, *, source: str | None = None) -> int:
        self._start_cleanup_task()
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
        """按关键词搜索图库图片。

        支持多关键词(空格分隔):返回按"命中关键词数"降序排列,
        全部关键词都命中的记录排在最前(角色立绘精确搜索)。
        """
        self._start_cleanup_task()
        limit = limit if limit is not None else self._config.gallery_page_size
        keywords = [part.strip() for part in keyword.split() if part.strip()]
        if not keywords:
            return await self._list_image_records(
                source=source, limit=limit, offset=offset
            )
        if len(keywords) == 1:
            return await self._search_single(keywords[0], source=source, limit=limit, offset=offset)

        # 多关键词:分别查询(扩大候选),按命中词数排序后截断
        fetch_limit = max(limit * 3, 30)
        scored: dict[str, tuple[CreatorImageRecord, int]] = {}
        for index, word in enumerate(keywords):
            records = await self._search_single(word, source=source, limit=fetch_limit)
            for record in records:
                previous = scored.get(record.image_id)
                if previous is None:
                    scored[record.image_id] = (record, 1)
                else:
                    scored[record.image_id] = (previous[0], previous[1] + 1)
        ordered = sorted(
            scored.values(), key=lambda item: (-item[1], item[0].id or 0)
        )
        return [record for record, _count in ordered][offset : offset + limit]

    async def _search_single(
        self,
        keyword: str,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            records: list[CreatorImageRecord] = await uow.creator_images.search(
                keyword,
                source=source,
                limit=limit,
                offset=offset,
            )
        return [record for record in records if Path(record.file_path).is_file()]

    async def _list_image_records(
        self,
        *,
        source: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CreatorImageRecord]:
        limit = limit if limit is not None else self._config.gallery_page_size
        async with self._uow_factory() as uow:
            records = await uow.creator_images.list(source=source, limit=limit, offset=offset)
        return [record for record in records if Path(record.file_path).is_file()]

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
            return await self._read_local_image(Path(ref[8:]))
        if ref.startswith("file://"):
            return await self._read_local_image(Path(ref[7:]))
        if ref.startswith(("http://", "https://")):
            if is_local_or_private_url(ref):
                # 本机/内网地址（含 Bot 自己的文件服务器）不能走系统代理
                async with image_http_client(
                    timeout=self._get_io_timeout_seconds(),
                    follow_redirects=True,
                    url=ref,
                ) as client:
                    async with client.stream("GET", ref) as response:
                        response.raise_for_status()
                        return await self._read_limited(response)
            response = await self._public_client.get(ref)
            response.raise_for_status()
            return await self._read_limited(response)
        path = Path(ref)
        if path.exists() and path.is_file():
            return await self._read_local_image(path)
        raise LookupError("无法下载图片内容")

    async def _read_local_image(self, path: Path) -> bytes:
        """读取本地图片引用（file:// 或裸路径）。

        本地引用可能来自 OneBot 框架自身的图片缓存，也可能来自被注入的事件，
        而原实现对任何路径都直接 read_bytes，等于把「任意本地文件读取」暴露给
        上游：内容形态校验 + 体积上限把它收敛为「只读图片」，同时不改变
        框架正常传图的行为（真实图片无论放在哪个目录都仍可读）。
        """
        return await asyncio.to_thread(self._read_local_image_sync, path)

    @staticmethod
    def _read_local_image_sync(path: Path) -> bytes:
        from neobot_app.utils.image_bytes import looks_like_image

        if not path.is_file():
            raise LookupError(f"本地图片不存在: {path}")
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise LookupError(f"无法读取本地图片: {exc}") from exc
        if size > _MAX_REMOTE_FETCH_BYTES:
            raise LookupError(f"本地图片过大（{size} 字节），已拒绝读取")
        data = path.read_bytes()
        if not looks_like_image(data):
            raise LookupError(f"本地引用不是图片内容，已拒绝读取: {path.name}")
        return data

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
            # 图库编号只在这里分配一次（现有最大值 +1），仓库层不会覆盖已有编号
            gallery_no = await self._allocate_gallery_no(uow, source)
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
                gallery_no=gallery_no,
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

                prepared = await prepare_local_image_async(file_path)
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

                prepared = await prepare_local_image_async(file_path)
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
                    # 手动放进图库目录的图片同样要有固定编号
                    gallery_no=await self._allocate_gallery_no(uow, disk_source),
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
            prepared = await prepare_local_image_async(file_path)
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

    @staticmethod
    async def _allocate_gallery_no(uow: Any, source: str) -> int | None:
        """图库记录入库时分配固定编号；暂存区等其它来源不参与编号。"""
        if source != GALLERY_SOURCE:
            return None
        return await uow.creator_images.next_gallery_no()

    async def _ensure_gallery_capacity(self) -> None:
        async with self._uow_factory() as uow:
            count = await uow.creator_images.count(source=GALLERY_SOURCE)
        if count >= self._config.gallery_capacity:
            raise ValueError(f"图库容量已满（{self._config.gallery_capacity}）")

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


#: data URL -> 文件扩展名
_MIME_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def _extension_for_mime(mime: str) -> str:
    return _MIME_EXTENSIONS.get(str(mime or "").lower(), ".png")


def _decode_data_url(value: str) -> tuple[bytes | None, str]:
    """解析 data URL，返回 (原始字节, mime)；非 base64 data URL 返回 (None, "")。"""
    text = str(value or "")
    if not text.startswith("data:") or "," not in text:
        return None, ""
    header, _, encoded = text.partition(",")
    if "base64" not in header.lower():
        return None, ""
    mime = header[len("data:") :].split(";")[0].strip() or "image/png"
    try:
        return base64.b64decode(encoded), mime
    except Exception:
        return None, ""


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


def _resize_keep_ratio(img: Any, target: tuple[int | None, int | None]) -> Any:
    """等比缩放:只给一边时按单边等比,两边都给时取 fit(不拉伸)。"""
    width, height = target
    original_w, original_h = img.size
    if width and height:
        ratio = min(width / original_w, height / original_h)
        new_size = (
            max(1, int(original_w * ratio)),
            max(1, int(original_h * ratio)),
        )
    elif width:
        ratio = width / original_w
        new_size = (int(width), max(1, int(original_h * ratio)))
    elif height:
        ratio = height / original_h
        new_size = (max(1, int(original_w * ratio)), int(height))
    else:
        return img
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _remove_background(img: Any, background_color: str | None = None) -> Any:
    """纯色背景去底为透明(参考 codex remove_chroma_key 思路)。

    - 键色:background_color 指定(如 "#00ff00");未指定时从边框四角采样平均
    - alpha:色差距离做 soft matte(transparent 阈值 12 / opaque 阈值 220)
    - despill:低透明度边缘向键色方向清理,避免色边
    """
    import numpy as np

    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).astype(np.float32)
    rgb = arr[:, :, :3]

    if background_color:
        key = _parse_hex_color(background_color)
        key_arr = np.array(key, dtype=np.float32)
    else:
        # 边框采样:四角小方块平均
        h, w = rgb.shape[:2]
        patch = max(1, min(h, w, 12))
        patches = [
            rgb[0:patch, 0:patch],
            rgb[0:patch, w - patch : w],
            rgb[h - patch : h, 0:patch],
            rgb[h - patch : h, w - patch : w],
        ]
        key_arr = np.mean(np.concatenate([p.reshape(-1, 3) for p in patches]), axis=0)

    # 归一化颜色距离(0-1)
    distance = np.linalg.norm(rgb - key_arr, axis=2) / np.sqrt(3.0)

    transparent_threshold = 12.0 / 255.0
    opaque_threshold = 220.0 / 255.0
    alpha = np.clip(
        (distance - transparent_threshold)
        / max(opaque_threshold - transparent_threshold, 1e-6),
        0.0,
        1.0,
    )

    # despill:键色成分主导的低透明度区域,把颜色向键色方向收敛
    key_dominance = (rgb * key_arr).sum(axis=2) / (
        np.linalg.norm(rgb, axis=2) * np.linalg.norm(key_arr) + 1e-6
    )
    spill = (alpha < 0.5) & (key_dominance > 0.9)
    if spill.any():
        rgb[spill] = rgb[spill] * (1.0 - alpha[spill, None] * 0.8)

    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _parse_hex_color(raw: str) -> tuple[int, int, int]:
    """解析 "#rrggbb" 或 "rrggbb" 颜色。"""
    value = str(raw or "").strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"颜色格式无效: {raw}(应为 #rrggbb)")
    try:
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
    except ValueError as exc:
        raise ValueError(f"颜色格式无效: {raw}") from exc

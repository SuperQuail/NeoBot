"""图片登记、字节落盘、记录持久化与描述解析。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any


from neobot_contracts.models.memory import CreatorImageRecord

from neobot_app.drawing.config import (
    GALLERY_SOURCE,
    TMP_SOURCE,
)
from neobot_app.utils.http import image_http_client, is_local_or_private_url

if TYPE_CHECKING:
    pass

from ._facade import facade
from .helpers import _read_sidecar_description


class StorageMixin:
    """图片登记、字节落盘、记录持久化与描述解析。"""

    async def register_local_image(
        self,
        file_path: Path | str,
        *,
        image_source: str | None = None,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> CreatorImageRecord | None:
        """把一个本地图片文件登记进 temp 图库，返回记录（失败返回 None）。

        Bot 自己发出去的图片用这条最小入口落进与「其他人发的图片」完全相同的
        tmp_xxx 存储与加载入口（image_context__add_image(image_id="tmp_xxx")），
        因此队列里只留索引即可被 agent 再次取回查看。

        不新增表、不新增存储层：复用既有的 _save_image_bytes(TMP_SOURCE)。
        """
        path = Path(file_path)
        try:
            if not path.is_file():
                return None
            size = path.stat().st_size
            if size <= 0 or size > max_bytes:
                return None
            data = path.read_bytes()
        except OSError as exc:
            self._logger.warning(
                "登记本地图片失败（读取失败）", file=str(file_path), error=str(exc)
            )
            return None
        return await self._save_image_bytes(
            data,
            source=TMP_SOURCE,
            prompt=None,
            description=None,
            image_source=image_source or "Bot 自发图片",
        )

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
        if size > facade()._MAX_REMOTE_FETCH_BYTES:
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
            # 图库编号只在这里分配一次（持久化高水位 +1），仓库层不会覆盖已有编号
            gallery_no = await self._allocate_gallery_no(uow, source, image_id)
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


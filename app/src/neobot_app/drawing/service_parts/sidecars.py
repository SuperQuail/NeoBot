"""图片伴生描述同步与本地文件索引。"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any


from neobot_contracts.models.memory import CreatorImageRecord

from neobot_app.drawing.config import (
    GALLERY_SOURCE,
    TMP_SOURCE,
    _IMAGE_EXTENSIONS,
)

if TYPE_CHECKING:
    pass

from ._facade import facade
from .helpers import _read_sidecar_description


class SidecarsMixin:
    """图片伴生描述同步与本地文件索引。"""

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

                prepared = await facade().prepare_local_image_async(file_path)
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

                prepared = await facade().prepare_local_image_async(file_path)
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
                    gallery_no=await self._allocate_gallery_no(uow, disk_source, image_id),
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
            prepared = await facade().prepare_local_image_async(file_path)
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
    async def _allocate_gallery_no(uow: Any, source: str, image_id: str) -> int | None:
        """图库记录入库时分配固定编号；暂存区等其它来源不参与编号。

        高水位编号是消耗品：只为新记录或历史缺号记录分配，更新已有编号的记录
        直接复用旧号，否则每次改描述都会打出空洞（编号只增不复用，空洞不可回填）。
        """
        if source != GALLERY_SOURCE:
            return None
        existing = await uow.creator_images.get(image_id)
        if existing is not None and existing.gallery_no is not None:
            return None
        return await uow.creator_images.allocate_gallery_no()

    async def _ensure_gallery_capacity(self) -> None:
        async with self._uow_factory() as uow:
            count = await uow.creator_images.count(source=GALLERY_SOURCE)
        if count >= self._config.gallery_capacity:
            raise ValueError(f"图库容量已满（{self._config.gallery_capacity}）")


"""表情包编号重建（由 service.py 拆分）。"""

from __future__ import annotations

from pathlib import Path

from neobot_contracts.models.memory import EmojiRecord

from neobot_app.emoji.service_parts.models import EmojiEntry


class _IndexMixin:
    def _rebuild_mapping(
        self,
        image_files: list[Path],
        analysis_map: dict[str, str],
        path_to_hash: dict[Path, str],
        use_counts: dict[str, int] | None = None,
        records_by_hash: dict[str, EmojiRecord] | None = None,
    ) -> None:
        """根据当前文件列表和分析结果重建编号映射"""
        counts = use_counts or {}
        records = records_by_hash or {}
        # 保留仍存在的旧条目编号
        old_by_name: dict[str, tuple[int, EmojiEntry]] = {}
        for number, entry in self._entries.items():
            old_by_name[entry.file_name] = (number, entry)

        new_entries: dict[int, EmojiEntry] = {}
        # 从已有条目的真实编号集合计算，新编号必须避开已占用编号且不复用已删除编号
        used_numbers = set(self._entries.keys())
        max_existing_number = max(used_numbers, default=0)

        for file_path in image_files:
            name = file_path.name
            file_hash = path_to_hash.get(file_path)
            entry_use_count = counts.get(file_hash, 0) if file_hash else 0

            if name in old_by_name and old_by_name[name][1].file_path == file_path:
                num = old_by_name[name][0]
                analysis_text = (
                    analysis_map.get(file_hash, old_by_name[name][1].analysis_text)
                    if file_hash is not None
                    else old_by_name[name][1].analysis_text
                )
                old_entry = self._entries.get(num)
                record = records.get(file_hash) if file_hash is not None else None
                new_entries[num] = EmojiEntry(
                    file_name=name,
                    file_path=file_path,
                    analysis_text=analysis_text,
                    use_count=entry_use_count,
                    file_hash=file_hash or getattr(old_entry, "file_hash", ""),
                    image_source=(
                        record.image_source
                        if record is not None
                        else getattr(old_entry, "image_source", None)
                    ),
                    created_at=(
                        record.created_at
                        if record is not None
                        else getattr(old_entry, "created_at", None)
                    ),
                    updated_at=(
                        record.updated_at
                        if record is not None
                        else getattr(old_entry, "updated_at", None)
                    ),
                    exposure_score=(
                        record.exposure_score
                        if record is not None
                        else getattr(old_entry, "exposure_score", 0.0)
                    ),
                    is_favorite=(
                        record.is_favorite
                        if record is not None
                        else getattr(old_entry, "is_favorite", False)
                    ),
                )
                if num > max_existing_number:
                    max_existing_number = num
            else:
                analysis_text = "[待解析]"
                if file_hash is not None:
                    analysis_text = analysis_map.get(file_hash, "[待解析]")
                old_entry = None
                if name in old_by_name:
                    num = old_by_name[name][0]
                    old_entry = self._entries.get(num)
                else:
                    max_existing_number += 1
                    num = max_existing_number
                record = records.get(file_hash) if file_hash is not None else None
                new_entries[num] = EmojiEntry(
                    file_name=name,
                    file_path=file_path,
                    analysis_text=analysis_text,
                    use_count=entry_use_count,
                    file_hash=file_hash or getattr(old_entry, "file_hash", ""),
                    image_source=(
                        record.image_source
                        if record is not None
                        else getattr(old_entry, "image_source", None)
                    ),
                    created_at=(
                        record.created_at
                        if record is not None
                        else getattr(old_entry, "created_at", None)
                    ),
                    updated_at=(
                        record.updated_at
                        if record is not None
                        else getattr(old_entry, "updated_at", None)
                    ),
                    exposure_score=(
                        record.exposure_score
                        if record is not None
                        else getattr(old_entry, "exposure_score", 0.0)
                    ),
                    is_favorite=(
                        record.is_favorite
                        if record is not None
                        else getattr(old_entry, "is_favorite", False)
                    ),
                )

        removed = set(self._entries) - set(new_entries)
        if removed:
            self._logger.info(f"表情包文件已删除，移除编号: {sorted(removed)}")

        self._entries = new_entries
        self._next_number = max(new_entries) + 1 if new_entries else 1

"""表情包发送、使用计数与候选曝光（由 service.py 拆分）。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from neobot_app.message.image_pipeline import prepare_local_image_async

from neobot_app.emoji.service_parts.models import EmojiEntry, _file_hash_sync


class _SendingMixin:
    async def send_sticker(
        self,
        number: int,
        *,
        text: str = "",
        group_id: Any = None,
        user_id: Any = None,
    ) -> Any:
        """发送指定编号的表情包到群聊或私聊，成功后记录使用次数。

        group_id 与 user_id 至少提供一个；两者都有时优先群聊。
        """
        if self._adapter is None or self._file_server is None:
            raise RuntimeError("表情包发送能力未注入（缺少 adapter/file_server）")
        entry = self.get_entry(number)
        if entry is None:
            raise LookupError(f"表情包编号 {number} 不存在")
        if not entry.file_path.exists():
            raise FileNotFoundError(f"表情包文件不存在: {entry.file_path}")

        group_id = str(group_id or "").strip()
        user_id = str(user_id or "").strip()
        if not group_id and not user_id:
            raise ValueError("缺少 group_id 或 user_id")

        from neobot_app.utils.media_sender import prepare_image_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segments: list[dict] = []
        if text:
            segments.append({"type": "text", "data": {"text": text}})
        segments.append(prepare_image_segment(self._file_server, entry.file_path))

        resp = await self._adapter.send(conv_ref, segments)
        await self.record_usage(number)
        return resp

    async def record_usage(self, number: int) -> None:
        """记录一次表情包使用，递增 use_count。"""
        entry = self._entries.get(number)
        if entry is None:
            return
        try:
            file_hash = (await prepare_local_image_async(entry.file_path)).file_hash
            async with self._uow_factory() as uow:
                await uow.emojis.increment_usage(file_hash)
                await uow.commit()
        except Exception as exc:
            self._logger.warning(f"记录表情包使用次数失败 #{number}: {exc}")
            return

        # 更新内存中的计数（只动 use_count，曝光分与爱用标记原样保留）
        self._entries[number] = replace(entry, use_count=entry.use_count + 1)

    def pick_context_candidates(
        self,
        random_limit: int = 10,
        favorite_limit: int = 10,
    ) -> list[tuple[int, EmojiEntry]]:
        """挑选一轮表情包候选：爱用组在前，随机组在后。

        - 爱用：最多 favorite_limit 个，按 effective_use_count 从少到多；
        - 随机：非爱用里 effective_use_count 最低的 random_limit 个。
        两组天然不重叠（爱用不占随机槽位）；没有爱用时只返回随机组。
        """
        self._notify_disk_changed()
        ordered = sorted(
            self._entries.items(), key=lambda item: item[1].effective_use_count
        )
        favorites = [
            (number, entry) for number, entry in ordered if entry.is_favorite
        ][: max(int(favorite_limit), 0)]
        random_slots = [
            (number, entry) for number, entry in ordered if not entry.is_favorite
        ][: max(int(random_limit), 0)]
        return favorites + random_slots

    async def record_candidate_round(
        self,
        numbers: Sequence[int],
        selected: int | None = None,
    ) -> None:
        """给本轮候选各记 0.5 次曝光，selected 照记。

        真实发送次数仍只由 record_usage 负责：进过候选但没发出去的不算「用过」。
        """
        _ = selected  # 契约参数：本轮候选无论是否最终选中都记同样曝光
        targets = [
            (number, self._entries[number])
            for number in dict.fromkeys(numbers)
            if number in self._entries
        ]
        if not targets:
            return
        try:
            async with self._uow_factory() as uow:
                for _, entry in targets:
                    file_hash = entry.file_hash or _file_hash_sync(entry.file_path)
                    if file_hash:
                        await uow.emojis.add_exposure(
                            file_hash, self._CANDIDATE_EXPOSURE
                        )
                await uow.commit()
        except Exception as exc:
            self._logger.warning(f"记录表情包候选曝光失败: {exc}")
            return
        for number, entry in targets:
            self._entries[number] = replace(
                entry,
                exposure_score=entry.exposure_score + self._CANDIDATE_EXPOSURE,
            )

    async def set_favorite_emojis(self, numbers: Sequence[int]) -> dict[str, Any]:
        """整组替换爱用表情包；空列表清空。

        返回 {"ok": True, "favorites": [...]} 或 {"ok": False, "error": ...}；
        编号不存在或超过 favorite_limit 时不改任何状态。
        """
        self._notify_disk_changed()
        unique = list(dict.fromkeys(numbers))
        invalid = [number for number in unique if number not in self._entries]
        if invalid:
            return {
                "ok": False,
                "error": f"表情包编号不存在: {invalid}",
                "invalid_numbers": invalid,
            }
        if len(unique) > self._favorite_limit:
            return {
                "ok": False,
                "error": f"爱用表情包最多 {self._favorite_limit} 个，收到 {len(unique)} 个",
            }

        hashes: list[str] = []
        for number in unique:
            entry = self._entries[number]
            file_hash = entry.file_hash or _file_hash_sync(entry.file_path)
            if not file_hash:
                return {"ok": False, "error": f"无法读取表情包文件: {entry.file_name}"}
            hashes.append(file_hash)

        try:
            async with self._uow_factory() as uow:
                await uow.emojis.set_favorites(hashes)
                await uow.commit()
        except Exception as exc:
            self._logger.warning(f"保存爱用表情包失败: {exc}")
            return {"ok": False, "error": f"保存爱用表情包失败: {exc}"}

        favorite_numbers = set(unique)
        for number, entry in self._entries.items():
            self._entries[number] = replace(entry, is_favorite=number in favorite_numbers)
        return {
            "ok": True,
            "favorites": unique,
            "count": len(unique),
            "limit": self._favorite_limit,
        }

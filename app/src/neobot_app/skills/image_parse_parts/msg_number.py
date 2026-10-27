"""按聊天记录消息编号解析图片（单张/多张）。"""

from __future__ import annotations

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS
from neobot_app.message.numbering import MessageNumbering

from .helpers import _find_in_replied

class MsgNumberResolveMixin:

    async def _resolve_by_msg_number(
        self, pipeline_key: str, msg_number: int, image_index: int = 0,
        numbering_mapping: dict[int, int] | None = None,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> tuple[bytes | None, str | None]:
        """通过显示消息编号（如 "75: 用户名: [图片]" 中的 75）获取图片字节。

        优先使用 Agent 注入的 numbering_mapping（与 prompt 编号一致），
        否则从实时队列重建编号映射。
        """
        parts = pipeline_key.split(":", 1)
        if len(parts) != 2:
            return None, "pipeline_key 格式错误"
        conv_kind, conv_id = parts
        if conv_kind == "group":
            queue = self._group_queue
        elif conv_kind in ("private", "friend"):
            queue = self._friend_queue
        else:
            return None, f"未知会话类型: {conv_kind}"

        if queue is None or not conv_id:
            return None, "消息队列未配置"

        # 优先使用 Agent 注入的编号映射（保证与 prompt 一致）
        if numbering_mapping:
            real_message_id = numbering_mapping.get(msg_number)
        else:
            try:
                entries = queue.entries(conv_id)
            except KeyError:
                return None, f"队列不存在 key={conv_id}"
            if not entries:
                return None, "队列为空"
            numbering = MessageNumbering()
            for entry in entries:
                from neobot_app.message.queue import QueueEntryType
                if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                    msg_id = entry.message.message_id
                    if msg_id is None:
                        continue
                    for replied in getattr(entry, "replied_messages", []) or []:
                        rid = getattr(replied, "message_id", None)
                        if rid is not None and numbering.get_number(rid) is None:
                            numbering._assign_number(rid)
                    numbering._assign_number(msg_id)
            real_message_id = numbering.get_message_id(msg_number)

        if real_message_id is None:
            return None, f"消息编号 {msg_number} 无法映射到真实消息ID"

        message = queue.find_by_message_id(conv_id, real_message_id)
        if message is None:
            message = _find_in_replied(queue, conv_id, real_message_id)

        queue_reason: str
        if message is None:
            queue_reason = (
                f"消息 {real_message_id} 不在队列或 replied_messages 中"
                f"（编号={msg_number}）"
            )
        else:
            queue_result, queue_error = await self._extract_image_from_message(
                message,
                image_index,
                timeout=timeout,
            )
            if queue_result is not None:
                return queue_result, None
            queue_reason = queue_error or "队列中的图片下载失败"

        # 自动图片解析会原地替换队列中的 image 段。编号映射已经给出了
        # OneBot message_id，因此队列副本不可用时应从 Adapter 获取原始消息。
        api_result, api_error = await self._resolve_by_message_id_with_error(
            real_message_id,
            image_index,
            timeout=timeout,
        )
        if api_result is not None:
            return api_result, None
        return (
            None,
            f"{queue_reason}；Adapter 回源失败：{api_error or '未知错误'}",
        )

    async def _resolve_many_by_msg_number(
        self, pipeline_key: str, msg_number: int, image_indices: list[int],
        numbering_mapping: dict[int, int] | None = None,
        timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS,
    ) -> list[tuple[bytes | None, str | None]]:
        """通过显示消息编号一次拉取多张图片字节（共用同一次消息查找）。
        Returns: [(bytes_or_None, error_reason_or_None), ...]
        """
        _n = len(image_indices)
        parts = pipeline_key.split(":", 1)
        if len(parts) != 2:
            return [(None, "pipeline_key 格式错误")] * _n
        conv_kind, conv_id = parts
        if conv_kind == "group":
            queue = self._group_queue
        elif conv_kind in ("private", "friend"):
            queue = self._friend_queue
        else:
            return [(None, f"未知会话类型: {conv_kind}")] * _n

        if queue is None or not conv_id:
            return [(None, "消息队列未配置")] * _n

        if numbering_mapping:
            real_message_id = numbering_mapping.get(msg_number)
        else:
            try:
                entries = queue.entries(conv_id)
            except KeyError:
                return [(None, f"队列不存在 key={conv_id}")] * _n
            if not entries:
                return [(None, "队列为空")] * _n
            numbering = MessageNumbering()
            for entry in entries:
                from neobot_app.message.queue import QueueEntryType
                if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                    msg_id = entry.message.message_id
                    if msg_id is None:
                        continue
                    for replied in getattr(entry, "replied_messages", []) or []:
                        rid = getattr(replied, "message_id", None)
                        if rid is not None and numbering.get_number(rid) is None:
                            numbering._assign_number(rid)
                    numbering._assign_number(msg_id)
            real_message_id = numbering.get_message_id(msg_number)

        if real_message_id is None:
            return [(None, f"消息编号 {msg_number} 无法映射到真实消息ID")] * _n

        message = queue.find_by_message_id(conv_id, real_message_id)
        if message is None:
            message = _find_in_replied(queue, conv_id, real_message_id)

        if message is None:
            queue_reason = f"消息 {real_message_id} 不在队列或 replied_messages 中"
            results = [(None, queue_reason) for _ in image_indices]
        else:
            results = [
                await self._extract_image_from_message(
                    message,
                    index,
                    timeout=timeout,
                )
                for index in image_indices
            ]

        failed_positions = [
            position
            for position, (raw, _) in enumerate(results)
            if raw is None
        ]
        if not failed_positions:
            return results

        # 只回源一次消息，批量补齐所有在队列副本中失败的图片。
        api_results = await self._resolve_many_by_message_id_with_errors(
            real_message_id,
            [image_indices[position] for position in failed_positions],
            timeout=timeout,
        )
        for position, (api_result, api_error) in zip(
            failed_positions,
            api_results,
        ):
            if api_result is not None:
                results[position] = (api_result, None)
                continue
            queue_error = results[position][1] or "队列中的图片下载失败"
            results[position] = (
                None,
                f"{queue_error}；Adapter 回源失败：{api_error or '未知错误'}",
            )
        return results

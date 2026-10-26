"""按聊天流 ID 解析图片（单张/多张）。"""

from __future__ import annotations

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS

class ChatFlowResolveMixin:

    async def _resolve_by_chat_flow(self, chat_flow_id: str, image_index: int = 0, timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS) -> bytes | None:
        """通过聊天流 ID 和图片编号获取图片字节。"""
        if chat_flow_id.startswith("Group_"):
            queue_key = chat_flow_id[len("Group_"):]
            queue = self._group_queue
        elif chat_flow_id.startswith("Friend_"):
            queue_key = chat_flow_id[len("Friend_"):]
            queue = self._friend_queue
        else:
            return None

        if queue is None or not queue_key:
            return None

        try:
            remaining_index = image_index
            for msg in queue.iterate_from_newest(queue_key):
                local_segments = (
                    getattr(msg, "message", None)
                    or getattr(msg, "content", None)
                    or []
                )
                segments = local_segments
                message_id = getattr(msg, "message_id", None)

                # 自动解析会原地把 image 段替换为 "[图片：...]" 文本。
                # 主动解析遇到这种标记时，通过 get_msg 恢复原始消息段。
                if (
                    self._image_count(local_segments) == 0
                    and self._may_be_auto_parsed_image(local_segments)
                    and message_id is not None
                ):
                    fetched = await self._fetch_segments_by_message_id(message_id)
                    if fetched is not None:
                        segments = fetched

                image_count = self._image_count(segments)
                if remaining_index >= image_count:
                    remaining_index -= image_count
                    continue

                result, _ = await self._download_from_segments_with_error(
                    segments,
                    remaining_index,
                    timeout=timeout,
                )
                if result is not None:
                    return result

                # 队列中的原始 URL 也可能过期，再回源一次获取新 URL/file。
                if message_id is not None and segments is local_segments:
                    result, _ = await self._resolve_by_message_id_with_error(
                        message_id,
                        remaining_index,
                        timeout=timeout,
                    )
                    return result
                return None
            return None
        except Exception:
            return None

    async def _resolve_many_by_chat_flow(self, chat_flow_id: str, image_indices: list[int], timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS) -> list[bytes | None]:
        """通过聊天流 ID 一次性获取多张图片字节。"""
        if chat_flow_id.startswith("Group_"):
            queue_key = chat_flow_id[len("Group_"):]
            queue = self._group_queue
        elif chat_flow_id.startswith("Friend_"):
            queue_key = chat_flow_id[len("Friend_"):]
            queue = self._friend_queue
        else:
            return [None] * len(image_indices)

        if queue is None or not queue_key:
            return [None] * len(image_indices)

        # 在队列中找到第一条含图片的消息，从其后逐张提取
        try:
            ordered_indices = sorted(set(image_indices))
            collected: dict[int, bytes | None] = {}
            for idx in ordered_indices:
                collected[idx] = None
            found_msg_segments = None
            found_message_id = None
            found_from_local = False
            for msg in queue.iterate_from_newest(queue_key):
                local_segments = (
                    getattr(msg, "message", None)
                    or getattr(msg, "content", None)
                    or []
                )
                if not local_segments:
                    continue
                message_segments = local_segments
                message_id = getattr(msg, "message_id", None)
                if (
                    self._image_count(local_segments) == 0
                    and self._may_be_auto_parsed_image(local_segments)
                    and message_id is not None
                ):
                    fetched = await self._fetch_segments_by_message_id(message_id)
                    if fetched is not None:
                        message_segments = fetched
                if self._image_count(message_segments):
                    found_msg_segments = message_segments
                    found_message_id = message_id
                    found_from_local = message_segments is local_segments
                    break

            if found_msg_segments is None:
                return [collected.get(idx) for idx in image_indices]

            for idx in ordered_indices:
                collected[idx] = await self._download_from_segments(found_msg_segments, idx, timeout=timeout)

            # 若队列保留的是原始图片但 URL 已失效，用同一条消息的一次
            # Adapter 回源刷新所有失败图片，避免每张图片分别请求 get_msg。
            failed_indices = [
                idx
                for idx in ordered_indices
                if collected[idx] is None
            ]
            if failed_indices and found_from_local and found_message_id is not None:
                refreshed = await self._fetch_segments_by_message_id(
                    found_message_id
                )
                if refreshed is not None:
                    for idx in failed_indices:
                        collected[idx] = await self._download_from_segments(
                            refreshed,
                            idx,
                            timeout=timeout,
                        )
            return [collected.get(idx) for idx in image_indices]
        except Exception:
            return [None] * len(image_indices)

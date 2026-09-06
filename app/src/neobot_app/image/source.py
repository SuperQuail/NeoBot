"""统一的图片来源解析:任何 skill 都可以用同一套方式从参数中获取图片字节。

支持来源(与 parse_image/detect 工具一致):
- image_base64 — base64 编码图片(或 data URL)
- image_path — 本地图片路径
- image_url — HTTP/file URL
- msg_number — 聊天记录显示的消息编号(需注入 pipeline_key/_numbering_mapping)
- chat_flow_id + image_index — 聊天流 ID + 图片编号
- message_id + image_index — OneBot 消息 ID

设计说明:
- ImageParseSkill 是既有实现,其多图逻辑暂不迁移;本模块提供与它一致的单图解析,
  vision_detect / emoji_add 等新增图片入口统一使用本模块,保证"任意情况下
  都可以基于统一的方式操作图片"。
- 内部逻辑自 image_parse_skill 提取,行为保持一致(编号映射/队列查找/Adapter 回源)。
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

from neobot_app.message.numbering import MessageNumbering


def _response_data_for_get_image(response: Any) -> dict | None:
    """从 get_image API 响应中提取 data 字典。"""
    if response is None:
        return None
    if isinstance(response, dict):
        data = response.get("data", {})
        return data if isinstance(data, dict) else None
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    dump = getattr(data, "model_dump", None)
    if callable(dump):
        return dump(exclude_none=True)
    return None


async def _read_bounded_image_ref(
    ref: str, *, timeout: float, max_bytes: int
) -> bytes | None:
    """受限读取入口；在解码/读取/下载过程中限制大小，不影响旧调用。"""
    from urllib.parse import unquote, urlsplit

    try:
        if ref.startswith(("base64://", "data:")):
            if ref.startswith("data:"):
                header, separator, payload = ref.partition(",")
                if not separator or not header.lower().startswith("data:image/") or not header.endswith(";base64"):
                    return None
            else:
                payload = ref[9:]
            if len(payload) > 4 * ((max_bytes + 2) // 3):
                return None
            data = base64.b64decode(payload, validate=True)
        elif ref.startswith(("http://", "https://")):
            import httpx

            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                async with client.stream("GET", ref) as response:
                    response.raise_for_status()
                    length = response.headers.get("content-length")
                    if length is not None and int(length) > max_bytes:
                        return None
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                        if len(data) + len(chunk) > max_bytes:
                            return None
                        data.extend(chunk)
                    data = bytes(data)
        else:
            if ref.startswith("file://"):
                parsed = urlsplit(ref)
                if parsed.netloc not in ("", "localhost"):
                    return None
                ref = unquote(parsed.path)
                # Path.as_uri() encodes Windows drive paths as file:///C:/...
                if len(ref) >= 3 and ref[0] == "/" and ref[2] == ":":
                    ref = ref[1:]
            path = Path(ref).expanduser()
            if not path.is_file() or path.stat().st_size > max_bytes:
                return None
            with path.open("rb") as handle:
                data = handle.read(max_bytes + 1)
        return data if len(data) <= max_bytes else None
    except Exception:
        return None


async def read_image_ref(
    ref: str, *, timeout: float = 30.0, max_bytes: int | None = None
) -> bytes | None:
    """读取图片引用；max_bytes 可选，设置后严格校验 base64 并限制 IO 大小。"""
    if max_bytes is not None:
        return await _read_bounded_image_ref(ref, timeout=timeout, max_bytes=max_bytes)
    if ref.startswith("base64://"):
        try:
            return base64.b64decode(ref[9:])
        except Exception:
            return None
    if ref.startswith("data:") and ";base64," in ref:
        try:
            return base64.b64decode(ref.split(";base64,", 1)[1])
        except Exception:
            return None
    if ref.startswith("file://"):
        try:
            return Path(ref[7:]).expanduser().read_bytes()
        except OSError:
            return None
    path = Path(ref).expanduser()
    if path.exists() and path.is_file():
        try:
            return path.read_bytes()
        except OSError:
            return None
    try:
        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(ref)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None


def _find_in_replied(queue: Any, conv_id: str, message_id: int) -> Any:
    """在队列所有条目的 replied_messages 中查找指定消息。"""
    from neobot_app.message.queue import QueueEntryType

    try:
        entries = queue.entries(conv_id)
    except KeyError:
        return None
    for entry in entries:
        if entry.kind != QueueEntryType.MESSAGE:
            continue
        for replied in getattr(entry, "replied_messages", []) or []:
            if getattr(replied, "message_id", None) == message_id:
                return replied
    return None


class ImageSourceResolver:
    """统一的图片来源解析器(单图)。

    用法::

        resolver = ImageSourceResolver(
            adapter=adapter,
            group_message_queue=group_queue,
            friend_message_queue=friend_queue,
        )
        data, error = await resolver.resolve(args, timeout=30.0)
    """

    def __init__(
        self,
        *,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
        max_bytes: int | None = None,
    ) -> None:
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._max_bytes = max_bytes

    async def _read_ref(self, ref: str, *, timeout: float) -> bytes | None:
        if self._max_bytes is None:
            return await read_image_ref(ref, timeout=timeout)
        return await read_image_ref(ref, timeout=timeout, max_bytes=self._max_bytes)

    async def resolve(
        self,
        args: dict[str, Any],
        *,
        timeout: float = 30.0,
    ) -> tuple[bytes | None, str | None]:
        """按参数解析图片字节。

        Returns:
            (image_bytes, None) 成功
            (None, error_reason) 失败 — error_reason 为中文可诊断信息
        """
        image_index, index_error = self._safe_int(args.get("image_index") or 0)
        if index_error:
            return None, f"image_index 无效: {index_error}"
        if image_index < 0:
            return None, "image_index 不能为负数"

        ref = args.get("image_base64") or args.get("image_path") or args.get("image_url")
        if ref:
            if not isinstance(ref, str) or not ref.strip():
                return None, "图片引用参数不能为空"
            if args.get("image_base64") and not (
                ref.startswith("base64://") or ref.startswith("data:")
            ):
                ref = f"base64://{ref}"
            data = await self._read_ref(ref, timeout=timeout)
            if data is None:
                return None, "图片下载/解码失败(检查路径/URL/base64 是否有效)"
            return data, None

        if args.get("msg_number") is not None:
            msg_number, number_error = self._safe_int(args["msg_number"])
            if number_error:
                return None, f"msg_number 无效: {number_error}"
            pipeline_key = str(args.get("pipeline_key") or "")
            if not pipeline_key:
                return None, "无法确定当前会话(缺少 pipeline_key)"
            numbering_mapping = args.get("_numbering_mapping")
            return await self._resolve_by_msg_number(
                pipeline_key,
                msg_number,
                image_index=image_index,
                numbering_mapping=numbering_mapping if isinstance(numbering_mapping, dict) else None,
                timeout=timeout,
            )

        if args.get("chat_flow_id"):
            data = await self._resolve_by_chat_flow(
                str(args["chat_flow_id"]),
                image_index=image_index,
                timeout=timeout,
            )
            if data is None:
                return None, "按聊天流 ID 获取图片失败"
            return data, None

        if args.get("message_id") is not None:
            message_id, id_error = self._safe_int(args["message_id"])
            if id_error:
                return None, f"message_id 无效: {id_error}"
            return await self._resolve_by_message_id_with_error(
                message_id,
                image_index=image_index,
                timeout=timeout,
            )

        return None, (
            "缺少图片来源参数: 请提供 image_path / image_url / image_base64 / "
            "msg_number / chat_flow_id / message_id 之一"
        )

    @staticmethod
    def _safe_int(value: Any) -> tuple[int, str | None]:
        if isinstance(value, bool):
            return 0, "参数必须是整数"
        try:
            return int(value), None
        except (TypeError, ValueError):
            return 0, f"无法解析为整数: {value!r}"

    # ── 消息级来源(队列/Adapter 回源) ──

    async def _fetch_segments_by_message_id(self, message_id: int) -> list | None:
        """通过消息 ID 拉取消息并返回其 message segments。"""
        if self._adapter is None:
            return None
        try:
            response = await asyncio.wait_for(
                self._adapter.get_msg(message_id), timeout=10
            )
            data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
        except Exception:
            try:
                result = await self._adapter.call_api("get_msg", {"message_id": message_id})
                if not result:
                    return None
                data = result.get("data", {}) if isinstance(result, dict) else None
            except Exception:
                return None

        if data is None:
            return None
        if hasattr(data, "message"):
            return data.message
        if isinstance(data, dict):
            return data.get("message")
        return None

    @staticmethod
    def _segment_type(segment: Any) -> str:
        value = (
            segment.get("type")
            if isinstance(segment, dict)
            else getattr(segment, "type", None)
        )
        value = getattr(value, "value", value)
        return str(value or "")

    @classmethod
    def _image_count(cls, segments: list | None) -> int:
        return sum(
            1
            for segment in segments or []
            if cls._segment_type(segment) in ("image", "cardimage")
        )

    @classmethod
    def _may_be_auto_parsed_image(cls, segments: list | None) -> bool:
        """识别已被自动解析服务替换成描述文本的图片段。"""
        for segment in segments or []:
            if cls._segment_type(segment) != "text":
                continue
            data = (
                segment.get("data", {})
                if isinstance(segment, dict)
                else getattr(segment, "data", None)
            )
            text = str(cls._seg_data_to_dict(data).get("text") or "")
            if text.startswith("[图片"):
                return True
        return False

    @staticmethod
    def _seg_data_to_dict(seg_data: Any) -> dict:
        if isinstance(seg_data, dict):
            return seg_data
        if hasattr(seg_data, "model_dump"):
            return seg_data.model_dump(exclude_none=True) or {}
        return {}

    async def _resolve_by_message_id_with_error(
        self,
        message_id: int,
        image_index: int = 0,
        timeout: float = 30.0,
    ) -> tuple[bytes | None, str | None]:
        """通过 Adapter 回源消息,并返回第 N 张图片及失败原因。"""
        segments = await self._fetch_segments_by_message_id(message_id)
        if segments is None:
            return None, f"Adapter 无法获取消息 {message_id}"
        if not segments:
            return None, f"消息 {message_id} 没有可解析的内容段"
        return await self._download_from_segments_with_error(
            segments, image_index, timeout=timeout
        )

    async def _download_from_segments_with_error(
        self,
        segments: list,
        image_index: int = 0,
        timeout: float = 30.0,
    ) -> tuple[bytes | None, str | None]:
        if image_index < 0:
            return None, f"图片编号不能为负数: {image_index}"
        if not segments:
            return None, "消息中没有可解析的内容段"

        image_segments = [
            segment
            for segment in segments
            if self._segment_type(segment) in ("image", "cardimage")
        ]
        if image_index >= len(image_segments):
            return (
                None,
                f"消息中找不到第 {image_index} 张图片（图片总数 {len(image_segments)}）",
            )

        segment = image_segments[image_index]
        data = (
            segment.get("data", {})
            if isinstance(segment, dict)
            else getattr(segment, "data", None)
        )
        return await self._download_image_segment(
            self._seg_data_to_dict(data), timeout=timeout
        )

    async def _download_image_segment(
        self, seg_data: dict, *, timeout: float = 30.0
    ) -> tuple[bytes | None, str | None]:
        """从 segment data 下载图片字节(URL 直下,失败走 get_image API)。"""
        import httpx

        url = seg_data.get("url")
        if url:
            if self._max_bytes is not None:
                content = await self._read_ref(str(url), timeout=timeout)
                if content is not None:
                    return content, None
            else:
                try:
                    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                        resp = await client.get(str(url))
                        resp.raise_for_status()
                        return resp.content, None
                except Exception:
                    pass  # fall through to file fallback

        file_name = seg_data.get("file")
        # Native context also accepts OneBot inline/file references without an Adapter.
        if file_name and self._max_bytes is not None:
            content = await self._read_ref(str(file_name), timeout=timeout)
            if content is not None:
                return content, None
        if file_name and self._adapter is not None:
            try:
                from neobot_adapter.request.message import get_image

                result = await get_image(str(file_name), timeout=timeout)
                img_data = _response_data_for_get_image(result)
                if isinstance(img_data, dict):
                    img_ref = img_data.get("file") or img_data.get("url")
                    if img_ref:
                        content = await self._read_ref(str(img_ref), timeout=timeout)
                        if content is not None:
                            return content, None
                        return None, f"get_image 返回的图片引用下载失败(file={file_name})"
                return None, f"get_image 返回无效数据(file={file_name})"
            except Exception as exc:
                return None, f"get_image API 异常(file={file_name}): {exc}"

        if url and file_name:
            return None, f"URL下载和get_image均失败(url={str(url)[:60]}, file={file_name})"
        if url:
            return None, f"URL下载失败且无file字段(url={str(url)[:60]})"
        return None, "segment data 既无url也无file字段"

    async def _resolve_by_chat_flow(
        self,
        chat_flow_id: str,
        image_index: int = 0,
        timeout: float = 30.0,
    ) -> bytes | None:
        """通过聊天流 ID 和图片编号获取图片字节(从最新消息向前找)。"""
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

                # 自动解析会原地把 image 段替换为 "[图片：...]" 文本
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
                    segments, remaining_index, timeout=timeout
                )
                if result is not None:
                    return result

                # 队列中的原始 URL 也可能过期,再回源一次
                if message_id is not None and segments is local_segments:
                    result, _ = await self._resolve_by_message_id_with_error(
                        message_id, remaining_index, timeout=timeout
                    )
                    return result
                return None
            return None
        except Exception:
            return None

    async def _extract_image_from_message(
        self, message: Any, image_index: int = 0, timeout: float = 30.0
    ) -> tuple[bytes | None, str | None]:
        """从消息对象中提取第 image_index 张图片的字节。"""
        segments = getattr(message, "message", None)
        if not segments:
            return None, "消息中没有可解析的内容段"

        img_idx = 0
        for seg in segments:
            if self._segment_type(seg) not in ("image", "cardimage"):
                continue
            if img_idx != image_index:
                img_idx += 1
                continue
            if isinstance(seg, dict):
                seg_data = seg.get("data", {}) or {}
            else:
                seg_data = getattr(seg, "data", None)
            seg_data = self._seg_data_to_dict(seg_data)
            return await self._download_image_segment(seg_data, timeout=timeout)

        return None, f"消息中找不到第 {image_index} 张图片（图片总数不足）"

    async def _resolve_by_msg_number(
        self,
        pipeline_key: str,
        msg_number: int,
        image_index: int = 0,
        numbering_mapping: dict[int, int] | None = None,
        timeout: float = 30.0,
    ) -> tuple[bytes | None, str | None]:
        """通过显示消息编号(如 "75: 用户名: [图片]" 中的 75)获取图片字节。"""
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
                f"消息 {real_message_id} 不在队列或 replied_messages 中（编号={msg_number}）"
            )
        else:
            queue_result, queue_error = await self._extract_image_from_message(
                message, image_index, timeout=timeout
            )
            if queue_result is not None:
                return queue_result, None
            queue_reason = queue_error or "队列中的图片下载失败"

        api_result, api_error = await self._resolve_by_message_id_with_error(
            real_message_id, image_index, timeout=timeout
        )
        if api_result is not None:
            return api_result, None
        return (
            None,
            f"{queue_reason}；Adapter 回源失败：{api_error or '未知错误'}",
        )


async def resolve_image_bytes(
    args: dict[str, Any],
    *,
    adapter: Any = None,
    group_message_queue: Any = None,
    friend_message_queue: Any = None,
    timeout: float = 30.0,
) -> tuple[bytes | None, str | None]:
    """便捷入口:按参数解析图片字节(与 ImageSourceResolver.resolve 一致)。"""
    resolver = ImageSourceResolver(
        adapter=adapter,
        group_message_queue=group_message_queue,
        friend_message_queue=friend_message_queue,
    )
    return await resolver.resolve(args, timeout=timeout)

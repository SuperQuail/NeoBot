"""ImageParseSkill — 图片内容解析（支持路径/URL/base64/消息ID/聊天流）。"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from neobot_app.message.numbering import MessageNumbering
from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


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
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_none=True)
    return None


async def _read_image_ref(ref: str) -> bytes | None:
    """读取图片引用（base64 / file / URL / 路径）。"""
    import base64 as _base64

    if ref.startswith("base64://"):
        return _base64.b64decode(ref[9:])
    if ref.startswith("file://"):
        return Path(ref[7:]).expanduser().read_bytes()
    path = Path(ref).expanduser()
    if path.exists() and path.is_file():
        return path.read_bytes()
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
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


class ImageParseSkill(SkillModule):
    """图片内容解析 Skill — 解析聊天中的图片内容。"""

    @property
    def name(self) -> str:
        return "image_parse"

    @property
    def description(self) -> str:
        return "图片内容解析：按需求解析图片，支持本地路径/URL/base64/消息ID"

    @property
    def instructions(self) -> str:
        return (
            "图片解析 Skill 提供以下能力：\n\n"
            "## parse_image\n"
            "按指定需求解析图片内容，支持多种图片来源：\n"
            "  - image_path — 本地图片路径（推荐，与沙箱系统协作）\n"
            "  - image_url — HTTP/data/file URL\n"
            "  - image_base64 — base64 编码图片\n"
            "  - msg_number — **推荐**，聊天记录中显示的消息编号（如「75: 用户名: [图片]」中的 75）\n"
            "  - chat_flow_id + image_index — 通过聊天流 ID 和图片编号定位\n"
            "  - message_id — OneBot 消息 ID（不常用，勿将显示编号当作 message_id 传入）\n\n"
            "parse_image 为会话工具(session模式)：\n"
            "  - 调用后立即返回 session_submitted，实际解析在后台进行\n"
            "  - timeout_seconds 默认为 300 秒（5分钟），agent 可按需设置，最长 1800 秒（30分钟）\n"
            "  - 收到返回后请立即结束本轮回复，不要继续调用其他工具或使用 wait\n"
            "  - 系统会在解析完成后通过通知自动唤醒你，届时携带解析结果\n\n"
            "多张图片（推荐用法，省 API 调用）：\n"
            "  - 同一消息多张图：msg_number + image_indices=[0,1,2]（0-based）一次解析\n"
            "  - 多个 URL：image_url_list=[...] \n"
            "  - 多个本地路径：image_path_list=[...] \n"
            "  - 多图时返回 {ok:true, descriptions:[{index,ok,description/error},...], full_text, errors}\n"
            "  - 单图保持原 {ok, description} 兼容格式\n\n"
            "仅负责解析回传结果，不保存、不导入、不管理图库/表情包。"
        )

    @property
    def session_tools(self) -> set[str]:
        return {"parse_image"}

    def __init__(
        self,
        vision_provider: Any = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
    ) -> None:
        self._vision_provider = vision_provider
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "parse_image",
                "【会话工具】解析一张或多张图片的内容。"
                "支持 image_path（本地图片路径）、image_url（HTTP/data/file URL）、image_base64（base64编码）、"
                "msg_number（聊天记录中的消息编号，如「75: 用户名: [图片]」中的 75）、"
                "chat_flow_id+image_index（聊天流ID+图片编号）。\n"
                "多张图片：可传 image_indices 数组（从0开始）、image_url_list、image_path_list 一次解析多张，"
                "返回 descriptions 列表；单张时返回 description 字段以兼容旧调用。",
                {
                    "properties": {
                        "requirement": {
                            "type": "string",
                            "description": "解析要求，例如「请简洁描述这张图片的主要内容」",
                            "default": "请简洁描述这张图片的主要内容。",
                        },
                        "image_path": {"type": "string", "description": "可选，本地图片路径"},
                        "image_url": {"type": "string", "description": "可选，图片 HTTP/file/data URL"},
                        "image_base64": {"type": "string", "description": "可选，base64 编码的图片数据"},
                        "image_path_list": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，一次解析多个本地图片路径",
                        },
                        "image_url_list": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，一次解析多个图片 URL",
                        },
                        "mime_type": {"type": "string", "description": "可选，图片 MIME 类型，默认 image/png"},
                        "msg_number": {"type": "integer", "description": "可选，聊天记录中的消息编号（如「75: xxx: [图片]」中的75），用于定位图片"},
                        "message_id": {"type": "integer", "description": "可选，OneBot 消息 ID（不常用，优先使用 msg_number）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（如 Group_12345），与 image_index 配合使用"},
                        "image_index": {"type": "integer", "description": "可选，图片编号（从0开始），与 chat_flow_id / msg_number / message_id 配合使用", "default": 0},
                        "image_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，一张消息内多张图片时，传入多个 image_index（从0开始）一起解析；与 msg_number / message_id / chat_flow_id 配合使用",
                        },
                        "timeout_seconds": {"type": "integer", "description": "可选，下载超时秒数，默认 300（5分钟），最长 1800（30分钟）", "default": 300},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown image_parse tool: {tool_name}"})
        return await handler(self, args)

    # ── 图片来源解析 ──

    async def _fetch_segments_by_message_id(self, message_id: int) -> list | None:
        """通过消息 ID 拉取消息并返回其 message segments（供多图复用避免多次请求 API）。"""
        if self._adapter is None:
            return None
        try:
            response = await asyncio.wait_for(
                self._adapter.get_msg(message_id), timeout=10,
            )
            data = getattr(response, "data", None)
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

    async def _resolve_by_message_id(self, message_id: int, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
        """通过消息 ID 获取第 N 张图片的字节。"""
        segments = await self._fetch_segments_by_message_id(message_id)
        if not segments:
            return None
        return await self._download_from_segments(segments, image_index, timeout=timeout)

    async def _resolve_many_by_message_id(self, message_id: int, image_indices: list[int], timeout: float = 30.0) -> list[bytes | None]:
        """通过消息 ID 一次性获取多张图片字节（一次 API 调用，多次下载）。"""
        segments = await self._fetch_segments_by_message_id(message_id)
        if not segments:
            return [None] * len(image_indices)
        results: list[bytes | None] = []
        for idx in image_indices:
            results.append(await self._download_from_segments(segments, idx, timeout=timeout))
        return results

    async def _download_from_segments(self, segments: list, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
        """从 segments 列表中找第 image_index 张图片并下载。"""
        if not segments:
            return None
        img_idx = 0
        for seg in segments:
            seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
            if isinstance(seg_type, type) and hasattr(seg_type, "value"):
                seg_type = seg_type.value
            if str(seg_type) not in ("image", "cardimage"):
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
        return None

    async def _resolve_by_chat_flow(self, chat_flow_id: str, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
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
            img_idx = 0
            for msg in queue.iterate_from_newest(queue_key):
                message_segments = getattr(msg, "message", None) or getattr(msg, "content", None)
                if not message_segments:
                    continue
                for seg in message_segments:
                    seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
                    if isinstance(seg_type, type) and hasattr(seg_type, "value"):
                        seg_type = seg_type.value
                    if str(seg_type) not in ("image", "cardimage"):
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
            return None
        except Exception:
            return None

    async def _resolve_many_by_chat_flow(self, chat_flow_id: str, image_indices: list[int], timeout: float = 30.0) -> list[bytes | None]:
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
            img_idx = 0
            found_msg_segments = None
            for msg in queue.iterate_from_newest(queue_key):
                message_segments = getattr(msg, "message", None) or getattr(msg, "content", None)
                if not message_segments:
                    continue
                has_image = False
                for seg in message_segments:
                    seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
                    if isinstance(seg_type, type) and hasattr(seg_type, "value"):
                        seg_type = seg_type.value
                    if str(seg_type) in ("image", "cardimage"):
                        has_image = True
                        break
                if has_image:
                    found_msg_segments = message_segments
                    break

            if found_msg_segments is None:
                return [collected.get(idx) for idx in image_indices]

            for idx in ordered_indices:
                collected[idx] = await self._download_from_segments(found_msg_segments, idx, timeout=timeout)
            return [collected.get(idx) for idx in image_indices]
        except Exception:
            return [None] * len(image_indices)

    async def _download_image_segment(self, seg_data: dict, *, timeout: float = 30.0) -> bytes | None:
        """从 segment data 下载图片字节。

        先尝试 URL 直下，失败/缺失时 fallback 到 file 字段走 get_image API
        （旧消息的 URL 可能已过期，但 file 字段可用于 OneBot get_image 重新获取）。
        """
        import httpx

        url = seg_data.get("url")
        if url:
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    resp = await client.get(str(url))
                    resp.raise_for_status()
                    return resp.content
            except Exception:
                pass

        file_name = seg_data.get("file")
        if file_name and self._adapter is not None:
            try:
                from neobot_adapter.request.message import get_image

                result = await get_image(str(file_name), timeout=timeout)
                img_data = _response_data_for_get_image(result)
                if isinstance(img_data, dict):
                    img_ref = img_data.get("file") or img_data.get("url")
                    if img_ref:
                        content = await _read_image_ref(str(img_ref))
                        if content is not None:
                            return content
            except Exception:
                pass

        return None

    async def _resolve_by_msg_number(
        self, pipeline_key: str, msg_number: int, image_index: int = 0,
        numbering_mapping: dict[int, int] | None = None,
        timeout: float = 30.0,
    ) -> bytes | None:
        """通过显示消息编号（如 "75: 用户名: [图片]" 中的 75）获取图片字节。

        优先使用 Agent 注入的 numbering_mapping（与 prompt 编号一致），
        否则从实时队列重建编号映射。
        """
        parts = pipeline_key.split(":", 1)
        if len(parts) != 2:
            return None
        conv_kind, conv_id = parts
        if conv_kind == "group":
            queue = self._group_queue
        elif conv_kind in ("private", "friend"):
            queue = self._friend_queue
        else:
            return None

        if queue is None or not conv_id:
            return None

        # 优先使用 Agent 注入的编号映射（保证与 prompt 一致）
        if numbering_mapping:
            real_message_id = numbering_mapping.get(msg_number)
        else:
            try:
                entries = queue.entries(conv_id)
            except KeyError:
                return None
            if not entries:
                return None
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
            return None

        message = queue.find_by_message_id(conv_id, real_message_id)
        if message is None:
            message = _find_in_replied(queue, conv_id, real_message_id)
        if message is None:
            return None

        return await self._extract_image_from_message(message, image_index, timeout=timeout)

    async def _resolve_many_by_msg_number(
        self, pipeline_key: str, msg_number: int, image_indices: list[int],
        numbering_mapping: dict[int, int] | None = None,
        timeout: float = 30.0,
    ) -> list[bytes | None]:
        """通过显示消息编号一次拉取多张图片字节（共用同一次消息查找）。"""
        parts = pipeline_key.split(":", 1)
        if len(parts) != 2:
            return [None] * len(image_indices)
        conv_kind, conv_id = parts
        if conv_kind == "group":
            queue = self._group_queue
        elif conv_kind in ("private", "friend"):
            queue = self._friend_queue
        else:
            return [None] * len(image_indices)

        if queue is None or not conv_id:
            return [None] * len(image_indices)

        if numbering_mapping:
            real_message_id = numbering_mapping.get(msg_number)
        else:
            try:
                entries = queue.entries(conv_id)
            except KeyError:
                return [None] * len(image_indices)
            if not entries:
                return [None] * len(image_indices)
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
            return [None] * len(image_indices)

        message = queue.find_by_message_id(conv_id, real_message_id)
        if message is None:
            message = _find_in_replied(queue, conv_id, real_message_id)
        if message is None:
            return [None] * len(image_indices)

        results: list[bytes | None] = []
        for idx in image_indices:
            results.append(await self._extract_image_from_message(message, idx, timeout=timeout))
        return results

    @staticmethod
    def _seg_data_to_dict(seg_data: Any) -> dict:
        """将 segment.data 转为 dict，兼容 dict / pydantic 模型。"""
        if isinstance(seg_data, dict):
            return seg_data
        if hasattr(seg_data, "model_dump"):
            return seg_data.model_dump(exclude_none=True) or {}
        return {}

    async def _extract_image_from_message(self, message: Any, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
        """从消息对象中提取第 image_index 张图片的字节。"""
        segments = getattr(message, "message", None)
        if not segments:
            return None

        img_idx = 0
        for seg in segments:
            seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
            if isinstance(seg_type, type) and hasattr(seg_type, "value"):
                seg_type = seg_type.value
            if str(seg_type) not in ("image", "cardimage"):
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

        return None

# ── Handler ──

async def _handle_parse_image(self: ImageParseSkill, args: dict) -> str:
    if self._vision_provider is None:
        return _json({"ok": False, "error": "vision_provider 未配置"})
    requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
    image_path = args.get("image_path")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")
    image_path_list = args.get("image_path_list") or []
    image_url_list = args.get("image_url_list") or []
    msg_number = args.get("msg_number")
    message_id = args.get("message_id")
    chat_flow_id = args.get("chat_flow_id")
    image_indices_arg = args.get("image_indices") or []
    pipeline_key = str(args.get("pipeline_key", "")).strip()

    timeout_seconds = float(int(args.get("timeout_seconds", 300) or 300))
    timeout_seconds = max(1.0, min(timeout_seconds, 1800.0))

    if not any([
        image_path, image_url, image_base64, msg_number, message_id, chat_flow_id,
        image_path_list, image_url_list,
    ]):
        return _json({
            "ok": False,
            "error": "请提供 image_path/image_url/image_base64/msg_number/message_id/chat_flow_id 或对应的 *_list 数组中的至少一种",
        })

    try:
        content_parts: list[dict] = [{"type": "text", "text": requirement}]

        from neobot_app.image.parser import _build_vision_image_part

        def _add_image_part(raw: bytes) -> None:
            content_parts.append(_build_vision_image_part(raw))

        # ── 收集所有图片字节，跟踪其来源索引 ──
        # 当且仅当只有一张时返回兼容的 {"ok": True, "description": "..."} 旧格式
        # 多张时返回 {"ok": True, "descriptions": [{"index": i, "description": "..."}, ...]}
        # 失败的图片位置也会被记录为 {"index": i, "ok": False, "error": ...}

        errors: list[dict] = []
        single_image: bytes | None = None
        multi_images: list[bytes | None] = []

        def _is_multi_mode() -> bool:
            return bool(image_path_list or image_url_list or image_indices_arg)

        def _record_bytes(raw: bytes | None, error_msg: str | None = None) -> None:
            """记录一张图的下载结果：成功入 multi_images，失败记 errors。"""
            multi_images.append(raw)
            if raw is None:
                errors.append({"index": len(multi_images) - 1, "ok": False, "error": error_msg or "下载失败"})

        # ── 路径/URL/base64 多图（显式 list 优先）──
        if image_path_list:
            for p in image_path_list:
                try:
                    raw = Path(str(p)).expanduser().read_bytes()
                    _record_bytes(raw)
                except Exception as exc:
                    _record_bytes(None, f"读取本地图片失败: {exc}")
        elif image_url_list:
            for u in image_url_list:
                content_parts.append({"type": "image_url", "image_url": {"url": str(u)}})
                multi_images.append(b"\x00url\x00")  # placeholder，URL 直接走 content_parts
            # URL 不计入 download 失败评估，这里直接清空同位置 errors 标记
        elif image_path:
            try:
                raw = Path(str(image_path)).expanduser().read_bytes()
                single_image = raw
            except Exception as exc:
                return _json({"ok": False, "error": f"读取本地图片失败: {exc}"})
        elif image_url:
            single_image = b"\x00url\x00"  # 标记 URL 单图
            content_parts.append({"type": "image_url", "image_url": {"url": str(image_url)}})
        elif image_base64:
            try:
                raw = base64.b64decode(str(image_base64))
                single_image = raw
            except Exception as exc:
                return _json({"ok": False, "error": f"base64 解码失败: {exc}"})
        elif msg_number:
            numbering_mapping = args.get("_numbering_mapping")
            if isinstance(numbering_mapping, dict):
                numbering_mapping = {int(k): int(v) for k, v in numbering_mapping.items()}
            else:
                numbering_mapping = None
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_msg_number(
                    pipeline_key, int(msg_number), indices,
                    numbering_mapping=numbering_mapping, timeout=timeout_seconds,
                )
                for i, raw in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({"index": i, "ok": False, "error": f"无法从消息编号 {msg_number}（第 {i} 张图片）获取图片"})
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes = await self._resolve_by_msg_number(
                    pipeline_key, int(msg_number), image_index,
                    numbering_mapping=numbering_mapping, timeout=timeout_seconds,
                )
                if image_bytes is None:
                    return _json({"ok": False, "error": f"无法从消息编号 {msg_number}（第 {image_index} 张图片）获取图片，请尝试用 msg_number 指定正确的消息编号"})
                single_image = image_bytes
        elif message_id:
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_message_id(int(message_id), indices, timeout=timeout_seconds)
                for i, raw in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({"index": i, "ok": False, "error": f"无法从消息 {message_id} 获取第 {i} 张图片"})
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes = await self._resolve_by_message_id(int(message_id), image_index, timeout=timeout_seconds)
                if image_bytes is None:
                    return _json({"ok": False, "error": f"无法从消息 {message_id} 获取第 {image_index} 张图片"})
                single_image = image_bytes
        elif chat_flow_id:
            if image_indices_arg and isinstance(image_indices_arg, list):
                indices = [int(i) for i in image_indices_arg]
                results = await self._resolve_many_by_chat_flow(chat_flow_id, indices, timeout=timeout_seconds)
                for i, raw in zip(indices, results):
                    multi_images.append(raw)
                    if raw is None:
                        errors.append({"index": i, "ok": False, "error": f"无法从 {chat_flow_id} 获取第 {i} 张图片"})
            else:
                image_index = int(args.get("image_index", 0))
                image_bytes = await self._resolve_by_chat_flow(chat_flow_id, image_index, timeout=timeout_seconds)
                if image_bytes is None:
                    return _json({"ok": False, "error": f"无法从 {chat_flow_id} 获取第 {image_index} 张图片"})
                single_image = image_bytes

        # ── 把 multi_images 中真正下载到的字节加入 content_parts（URL 已加入）──
        if _is_multi_mode():
            # multi_images 中混合真实 bytes / None / URL placeholder
            success_count = 0
            for entry in multi_images:
                if entry is None:
                    continue
                if entry == b"\x00url\x00":
                    success_count += 1
                    continue
                _add_image_part(entry)
                success_count += 1
            if success_count == 0:
                return _json({"ok": False, "error": "全部图片下载失败", "details": errors})
        else:
            if single_image is not None and single_image != b"\x00url\x00":
                _add_image_part(single_image)

        # ── 调用 vision 模型 ──
        result = await self._vision_provider.chat([{"role": "user", "content": content_parts}])
        text = result.get("content", "") if isinstance(result, dict) else str(result)

        if _is_multi_mode():
            # 多图时 vision 模型通常返回整段文本涵盖所有图；
            # 这里把整段描述放 descriptions 数组每项的 description 字段（共享文本，
            # 同时单独给每项 index 与 ok 状态）。如模型按序输出了多段，
            # agent 仍可从 text 中按顺序分辨。
            descriptions = []
            for i, entry in enumerate(multi_images):
                if entry is None:
                    descriptions.append({"index": i, "ok": False, "error": "下载失败"})
                else:
                    descriptions.append({"index": i, "ok": True, "description": text[:2000]})
            return _json({
                "ok": True,
                "descriptions": descriptions,
                "full_text": text[:2000],
                "errors": errors or None,
            })
        return _json({"ok": True, "description": text[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": f"{type(e).__name__}: {e}"})

_HANDLERS = {
    "parse_image": _handle_parse_image,
}

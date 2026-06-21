"""ImageParseSkill — 图片内容解析（支持路径/URL/base64/消息ID/聊天流）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from neobot_app.message.numbering import MessageNumbering
from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

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
                "chat_flow_id+image_index（聊天流ID+图片编号）。",
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
                        "mime_type": {"type": "string", "description": "可选，图片 MIME 类型，默认 image/png"},
                        "msg_number": {"type": "integer", "description": "可选，聊天记录中的消息编号（如「75: xxx: [图片]」中的75），用于定位图片"},
                        "message_id": {"type": "integer", "description": "可选，OneBot 消息 ID（不常用，优先使用 msg_number）"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（如 Group_12345），与 image_index 配合使用"},
                        "image_index": {"type": "integer", "description": "可选，图片编号（从0开始），与 chat_flow_id 配合使用", "default": 0},
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

    async def _resolve_by_message_id(self, message_id: int, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
        """通过消息 ID 获取第 N 张图片的字节。"""
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

        message_segments = None
        if hasattr(data, "message"):
            message_segments = data.message
        elif isinstance(data, dict):
            message_segments = data.get("message")

        if not message_segments:
            return None

        img_idx = 0
        for seg in message_segments:
            seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
            if seg_type not in ("image", "cardimage"):
                continue
            if img_idx != image_index:
                img_idx += 1
                continue
            seg_data = seg.get("data", {}) if isinstance(seg, dict) else (getattr(seg, "data", {}) or {})
            url = None
            if isinstance(seg_data, dict):
                url = seg_data.get("url")
            if not url:
                return None
            return await self._download_image(url, timeout=timeout)

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
                    if seg_type not in ("image", "cardimage"):
                        continue
                    if img_idx != image_index:
                        img_idx += 1
                        continue
                    seg_data = seg.get("data", {}) if isinstance(seg, dict) else (getattr(seg, "data", {}) or {})
                    url = seg_data.get("url") if isinstance(seg_data, dict) else None
                    if url:
                        return await self._download_image(url, timeout=timeout)
            return None
        except Exception:
            return None

    async def _download_image(self, url: str, timeout: float = 30.0) -> bytes | None:
        """下载图片字节。"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception:
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
            return None

        return await self._extract_image_from_message(message, image_index, timeout=timeout)

    @staticmethod
    async def _extract_image_from_message(message: Any, image_index: int = 0, timeout: float = 30.0) -> bytes | None:
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
            seg_data = seg.get("data", {}) if isinstance(seg, dict) else (getattr(seg, "data", {}) or {})
            url = seg_data.get("url") if isinstance(seg_data, dict) else None
            if not url:
                return None
            try:
                import httpx
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.content
            except Exception:
                return None

        return None

# ── Handler ──

async def _handle_parse_image(self: ImageParseSkill, args: dict) -> str:
    if self._vision_provider is None:
        return _json({"ok": False, "error": "vision_provider 未配置"})
    requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
    image_path = args.get("image_path")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")
    msg_number = args.get("msg_number")
    message_id = args.get("message_id")
    chat_flow_id = args.get("chat_flow_id")
    pipeline_key = str(args.get("pipeline_key", "")).strip()

    timeout_seconds = float(int(args.get("timeout_seconds", 300) or 300))
    timeout_seconds = max(1.0, min(timeout_seconds, 1800.0))

    if not any([image_path, image_url, image_base64, msg_number, message_id, chat_flow_id]):
        return _json({"ok": False, "error": "请提供 image_path、image_url、image_base64、msg_number、message_id 或 chat_flow_id 中的至少一种"})

    try:
        content_parts = [{"type": "text", "text": requirement}]

        if image_path:
            content_parts.append({"type": "image", "source": {"type": "local", "path": image_path}})
        elif image_url:
            content_parts.append({"type": "image", "source": {"type": "url", "url": image_url}})
        elif image_base64:
            mime = args.get("mime_type", "image/png")
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_base64}})
        elif msg_number:
            image_index = int(args.get("image_index", 0))
            numbering_mapping = args.get("_numbering_mapping")
            if isinstance(numbering_mapping, dict):
                numbering_mapping = {int(k): int(v) for k, v in numbering_mapping.items()}
            else:
                numbering_mapping = None
            image_bytes = await self._resolve_by_msg_number(
                pipeline_key, int(msg_number), image_index,
                numbering_mapping=numbering_mapping, timeout=timeout_seconds,
            )
            if image_bytes is None:
                return _json({"ok": False, "error": f"无法从消息编号 {msg_number}（第 {image_index} 张图片）获取图片，请尝试用 msg_number 指定正确的消息编号"})
            import base64
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode("utf-8")}})
        elif message_id:
            image_index = int(args.get("image_index", 0))
            image_bytes = await self._resolve_by_message_id(int(message_id), image_index, timeout=timeout_seconds)
            if image_bytes is None:
                return _json({"ok": False, "error": f"无法从消息 {message_id} 获取第 {image_index} 张图片"})
            import base64
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode("utf-8")}})
        elif chat_flow_id:
            image_index = int(args.get("image_index", 0))
            image_bytes = await self._resolve_by_chat_flow(chat_flow_id, image_index, timeout=timeout_seconds)
            if image_bytes is None:
                return _json({"ok": False, "error": f"无法从 {chat_flow_id} 获取第 {image_index} 张图片"})
            import base64
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode("utf-8")}})

        result = await self._vision_provider.chat([{"role": "user", "content": content_parts}])
        text = result.get("content", "") if isinstance(result, dict) else str(result)
        return _json({"ok": True, "description": text[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "parse_image": _handle_parse_image,
}

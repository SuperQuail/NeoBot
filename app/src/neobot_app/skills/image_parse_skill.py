"""ImageParseSkill — 图片内容解析（支持路径/URL/base64/消息ID/聊天流）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

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
            "  - message_id — 通过消息 ID 定位图片\n"
            "  - chat_flow_id + image_index — 通过聊天流 ID 和图片编号定位\n\n"
            "仅负责解析回传结果，不保存、不导入、不管理图库/表情包。"
        )

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
                "解析一张或多张图片的内容。"
                "支持 image_path（本地图片路径）、image_url（HTTP/data/file URL）、image_base64（base64编码）、"
                "message_id（消息ID）、chat_flow_id+image_index（聊天流ID+图片编号）。",
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
                        "message_id": {"type": "integer", "description": "可选，消息 ID，用于从聊天记录定位图片"},
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（如 Group_12345），与 image_index 配合使用"},
                        "image_index": {"type": "integer", "description": "可选，图片编号（从0开始），与 chat_flow_id 配合使用", "default": 0},
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

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}

    # ── 图片来源解析 ──

    async def _resolve_by_message_id(self, message_id: int, image_index: int = 0) -> bytes | None:
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

        # 提取消息中的消息段列表
        message_segments = None
        if hasattr(data, "message"):
            message_segments = data.message
        elif isinstance(data, dict):
            message_segments = data.get("message")

        if not message_segments:
            return None

        # 找到第 image_index 张图片
        img_idx = 0
        for seg in message_segments:
            seg_type = seg.get("type") if isinstance(seg, dict) else getattr(seg, "type", None)
            if seg_type not in ("image", "cardimage"):
                continue
            if img_idx != image_index:
                img_idx += 1
                continue
            # 获取图片 URL
            seg_data = seg.get("data", {}) if isinstance(seg, dict) else (getattr(seg, "data", {}) or {})
            url = None
            if isinstance(seg_data, dict):
                url = seg_data.get("url")
            if not url:
                return None
            return await self._download_image(url)

        return None

    async def _resolve_by_chat_flow(self, chat_flow_id: str, image_index: int = 0) -> bytes | None:
        """通过聊天流 ID 和图片编号获取图片字节。"""
        # 解析 "Group_12345" 或 "Friend_12345"
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

        # 从最新消息开始遍历，找第 image_index 张图片
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
                        return await self._download_image(url)
            return None
        except Exception:
            return None

    async def _download_image(self, url: str) -> bytes | None:
        """下载图片字节。"""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.content
        except Exception:
            return None


# ── Handler ──

async def _handle_parse_image(self: ImageParseSkill, args: dict) -> str:
    if self._vision_provider is None:
        return _json({"ok": False, "error": "vision_provider 未配置"})
    requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
    image_path = args.get("image_path")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")
    message_id = args.get("message_id")
    chat_flow_id = args.get("chat_flow_id")

    # 至少需要一种图片来源
    if not any([image_path, image_url, image_base64, message_id, chat_flow_id]):
        return _json({"ok": False, "error": "请提供 image_path、image_url、image_base64、message_id 或 chat_flow_id 中的至少一种"})

    try:
        content_parts = [{"type": "text", "text": requirement}]

        if image_path:
            content_parts.append({"type": "image", "source": {"type": "local", "path": image_path}})
        elif image_url:
            content_parts.append({"type": "image", "source": {"type": "url", "url": image_url}})
        elif image_base64:
            mime = args.get("mime_type", "image/png")
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_base64}})
        elif message_id:
            image_index = int(args.get("image_index", 0))
            image_bytes = await self._resolve_by_message_id(int(message_id), image_index)
            if image_bytes is None:
                return _json({"ok": False, "error": f"无法从消息 {message_id} 获取第 {image_index} 张图片"})
            import base64
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image_bytes).decode("utf-8")}})
        elif chat_flow_id:
            image_index = int(args.get("image_index", 0))
            image_bytes = await self._resolve_by_chat_flow(chat_flow_id, image_index)
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

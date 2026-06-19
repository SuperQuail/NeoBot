"""ImageParseSkill — 图片内容解析（增强版，支持本地路径/URL/base64）。"""

from __future__ import annotations

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
            "  - chat_flow_id + image_index — 通过聊天流 ID 和图片编号定位\n"
            "  - message_id — 通过消息 ID 定位（兼容旧方式）\n\n"
            "仅负责解析回传结果，不保存、不导入、不管理图库/表情包。"
        )

    def __init__(self, vision_provider: Any = None, adapter: Any = None) -> None:
        self._vision_provider = vision_provider
        self._adapter = adapter

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "parse_image",
                "解析一张或多张图片的内容。"
                "支持 image_path（本地图片路径）、image_url（HTTP/data/file URL）、image_base64（base64编码）、"
                "chat_flow_id+image_index（聊天流ID+图片编号）、message_id（消息ID）。",
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
                        "chat_flow_id": {"type": "string", "description": "可选，聊天流 ID（如 Group_12345），用于定位图片"},
                        "image_index": {"type": "integer", "description": "可选，图片编号，与 chat_flow_id 配合使用"},
                        "message_id": {"type": "integer", "description": "可选，消息 ID，用于从聊天记录定位图片"},
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


# ── Handlers ──

async def _handle_parse_image(self: ImageParseSkill, args: dict) -> str:
    if self._vision_provider is None:
        return _json({"ok": False, "error": "vision_provider 未配置"})
    requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容。").strip()
    image_path = args.get("image_path")
    image_url = args.get("image_url")
    image_base64 = args.get("image_base64")
    if not any([image_path, image_url, image_base64]):
        return _json({"ok": False, "error": "请提供 image_path、image_url 或 image_base64 中的至少一种"})
    try:
        content_parts = [{"type": "text", "text": requirement}]
        if image_path:
            content_parts.append({"type": "image", "source": {"type": "local", "path": image_path}})
        elif image_url:
            content_parts.append({"type": "image", "source": {"type": "url", "url": image_url}})
        elif image_base64:
            mime = args.get("mime_type", "image/png")
            content_parts.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": image_base64}})
        result = await self._vision_provider.chat([{"role": "user", "content": content_parts}])
        text = result.get("content", "") if isinstance(result, dict) else str(result)
        return _json({"ok": True, "description": text[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "parse_image": _handle_parse_image,
}

"""ImageSendSkill — 图片发送。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class ImageSendSkill(SkillModule):
    """图片发送 Skill — 发送图片到指定群聊或私聊。"""

    @property
    def name(self) -> str:
        return "image_send"

    @property
    def description(self) -> str:
        return "图片发送：发送图片到指定群聊或私聊"

    @property
    def instructions(self) -> str:
        return (
            "图片发送 Skill 提供以下能力：\n\n"
            "  send_image — 发送图片到指定群聊或私聊\n\n"
            "注意：如果图片在图库中，提供 image_id；如果是本地文件，提供 file_path。"
        )

    def __init__(self, adapter: Any = None, file_server: Any = None) -> None:
        self._adapter = adapter
        self._file_server = file_server

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        tools = [
            self._tool_def(
                "send_image",
                "发送图片到指定群聊或私聊。支持图库图片 ID 或本地文件路径。",
                {
                    "properties": {
                        "image_id": {"type": "integer", "description": "可选，图库图片 ID"},
                        "file_path": {"type": "string", "description": "可选，本地图片路径（沙箱内路径）"},
                        "group_id": {"type": "string", "description": "可选，目标群号"},
                        "user_id": {"type": "string", "description": "可选，目标QQ号"},
                    },
                    "required": [],
                },
            ),
        ]
        return tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown image_send tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_send_image(self: ImageSendSkill, args: dict) -> str:
    return _json({"ok": False, "error": "图片发送服务未配置"})


_HANDLERS = {
    "send_image": _handle_send_image,
}

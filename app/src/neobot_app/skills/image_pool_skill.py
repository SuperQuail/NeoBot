"""ImagePoolSkill — 图片暂存池管理（put/list/remove/clear）。"""

from __future__ import annotations

import json
import time
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class ImagePoolSkill(SkillModule):
    """图片暂存池 Skill — 将图片加入聊天流缓存池，供绘图/发送引用。"""

    @property
    def name(self) -> str:
        return "image_pool"

    @property
    def description(self) -> str:
        return "图片暂存池：将聊天/图库/表情包/URL/本地图片加入缓存池，供绘图和发送引用"

    @property
    def instructions(self) -> str:
        return (
            "图片暂存池 Skill 提供以下能力：\n\n"
            "  image_pool__put — 将图片加入当前聊天流的缓存池\n"
            "  image_pool__list — 列出当前缓存池中的所有图片\n"
            "  image_pool__remove — 移除缓存池中的指定图片\n"
            "  image_pool__clear — 清空当前聊天流的缓存池\n\n"

            "【source 格式】\n"
            "  image_pool__put 的 source 参数支持以下格式：\n"
            "    chat:<msg_id>:<img_index>  — 聊天消息中的图片（index 默认 1）\n"
            "    gallery:<编号>              — 图库中的图片\n"
            "    emoji:<编号>                — 表情包中的图片\n"
            "    url:<URL>                   — 网络图片\n"
            "    file:<路径>                 — 本地文件路径\n\n"

            "【使用场景】\n"
            "  - 用户要求参考聊天记录中的某张图片来绘图时，先用 put 存入缓存池，再用 drawing__draw 的 references=[\"pool:<key>\"] 引用\n"
            "  - 用户要发送的图片不在本地时，先用 put 存入，再用 image_send__send_image 的 pool_key 参数发送\n"
            "  - 缓存池中的图片 5 分钟后自动过期，也可用 clear 手动清空\n"
        )

    def __init__(
        self,
        image_pool: Any = None,
        creator_image_service: Any = None,
    ) -> None:
        self._pool = image_pool
        self._image_service = creator_image_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "put",
                "将图片加入当前聊天流的缓存池。返回图片 key，可用于 drawing__draw 的 references=[\"pool:<key>\"] 引用。",
                {
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": (
                                "图片来源描述符。格式：chat:<msg_id>:<img_index>（聊天图片）、"
                                "gallery:<编号>（图库）、emoji:<编号>（表情包）、"
                                "url:<URL>（网络图片）、file:<路径>（本地文件）"
                            ),
                        },
                        "pipeline_key": {
                            "type": "string",
                            "description": "管线标识，格式为 kind:id（如 group:123456、private:789012）。不填则使用当前管线。",
                        },
                    },
                    "required": ["source"],
                },
            ),
            self._tool_def(
                "list",
                "列出当前聊天流缓存池中的所有图片（含 key、来源、大小、类型、剩余秒数）。",
                {
                    "properties": {
                        "pipeline_key": {
                            "type": "string",
                            "description": "管线标识，格式为 kind:id。不填则使用当前管线。",
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "remove",
                "移除缓存池中指定 key 的图片。",
                {
                    "properties": {
                        "key": {"type": "string", "description": "要移除的图片 key"},
                        "pipeline_key": {
                            "type": "string",
                            "description": "管线标识。不填则使用当前管线。",
                        },
                    },
                    "required": ["key"],
                },
            ),
            self._tool_def(
                "clear",
                "清空当前聊天流的图片缓存池。",
                {
                    "properties": {
                        "pipeline_key": {
                            "type": "string",
                            "description": "管线标识。不填则使用当前管线。",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if self._pool is None:
            return _json({"ok": False, "error": "image_pool 未配置"})

        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown image_pool tool: {tool_name}"})
        return await handler(self, args)

    def _resolve_conv_id(self, args: dict) -> str:
        """从 args 中提取 conv_id。"""
        pipeline_key = str(args.get("pipeline_key", "") or "").strip()
        if ":" in pipeline_key:
            return pipeline_key
        return ""


# ── Handlers ──


async def _handle_put(self: ImagePoolSkill, args: dict) -> str:
    source = str(args.get("source", "") or "").strip()
    if not source:
        return _json({"ok": False, "error": "source 不能为空"})

    conv_id = self._resolve_conv_id(args)
    if not conv_id:
        return _json({"ok": False, "error": "缺少 pipeline_key，格式为 kind:id"})

    if self._image_service is None:
        return _json({"ok": False, "error": "creator_image_service 未配置"})

    try:
        file_path = await self._image_service.resolve_source_to_path(source)
        key = self._pool.put(conv_id, file_path, source=source)
        return _json({"ok": True, "key": key, "source": source})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})


async def _handle_list(self: ImagePoolSkill, args: dict) -> str:
    conv_id = self._resolve_conv_id(args)
    if not conv_id:
        return _json({"ok": False, "error": "缺少 pipeline_key"})

    images = self._pool.list(conv_id)
    now = time.monotonic()
    items: list[dict] = []
    for img in images:
        items.append({
            "key": img.key,
            "source": img.source,
            "size": img.size,
            "mime_type": img.mime_type,
            "remaining_seconds": max(0, int(img.expires_at - now)),
        })
    return _json({"ok": True, "images": items, "count": len(items)})


async def _handle_remove(self: ImagePoolSkill, args: dict) -> str:
    conv_id = self._resolve_conv_id(args)
    if not conv_id:
        return _json({"ok": False, "error": "缺少 pipeline_key"})
    key = str(args.get("key", "") or "").strip()
    if not key:
        return _json({"ok": False, "error": "key 不能为空"})
    removed = self._pool.remove(conv_id, key)
    if not removed:
        return _json({"ok": False, "error": f"key={key} 不存在或已过期"})
    return _json({"ok": True, "removed": key})


async def _handle_clear(self: ImagePoolSkill, args: dict) -> str:
    conv_id = self._resolve_conv_id(args)
    if not conv_id:
        return _json({"ok": False, "error": "缺少 pipeline_key"})
    count = self._pool.clear(conv_id)
    return _json({"ok": True, "cleared": count})


_HANDLERS = {
    "put": _handle_put,
    "list": _handle_list,
    "remove": _handle_remove,
    "clear": _handle_clear,
}

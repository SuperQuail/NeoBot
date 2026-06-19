"""GallerySkill — 图库管理（列/搜/增/改/删/重命名）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _format_image_item(record: Any, return_paths: bool) -> dict[str, Any]:
    """将 CreatorImageRecord 格式化为 dict。"""
    item = {
        "image_id": record.image_id,
        "description": record.description,
        "prompt": record.prompt,
        "source": record.source,
        "created_at": str(record.created_at) if record.created_at else None,
    }
    if return_paths:
        item["path"] = record.file_path
    return item


class GallerySkill(SkillModule):
    """图库管理 Skill — 列/搜/增/改/删/重命名图库图片。"""

    @property
    def name(self) -> str:
        return "gallery"

    @property
    def description(self) -> str:
        return "图库管理：列出、搜索、添加、更新、删除、重命名图库图片"

    @property
    def instructions(self) -> str:
        return (
            "图库管理 Skill 提供以下能力：\n\n"
            "  gallery_list — 列出图库图片\n"
            "  gallery_search — 搜索图库图片\n"
            "  gallery_add — 从聊天导入图片到图库\n"
            "  gallery_update — 更新图库图片信息（描述）\n"
            "  gallery_delete — 删除图库图片\n"
            "  gallery_rename — 重命名图库图片\n\n"
            "注意：图库文件对文件操作 agent 只读暴露，修改操作应通过本 skill。"
        )

    def __init__(
        self,
        creator_image_service: Any = None,
        uow_factory: Any = None,
        vision_provider: Any = None,
        file_server: Any = None,
        adapter: Any = None,
    ) -> None:
        self._image_service = creator_image_service
        self._uow_factory = uow_factory
        self._vision_provider = vision_provider
        self._file_server = file_server
        self._adapter = adapter

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "gallery_list",
                "列出图库中的图片。",
                {
                    "properties": {
                        "page": {"type": "integer", "description": "页码，从1开始", "default": 1},
                        "page_size": {"type": "integer", "description": "每页数量", "default": 50},
                        "return_paths": {"type": "boolean", "description": "是否返回文件路径", "default": False},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "gallery_search",
                "搜索图库图片。",
                {
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"},
                        "return_paths": {"type": "boolean", "description": "是否返回文件路径", "default": False},
                    },
                    "required": ["keyword"],
                },
            ),
            self._tool_def(
                "gallery_add",
                "从聊天导入图片到图库。",
                {
                    "properties": {
                        "image_path": {"type": "string", "description": "本地图片路径"},
                        "description": {"type": "string", "description": "可选，图片描述"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "可选，标签列表"},
                    },
                    "required": ["image_path"],
                },
            ),
            self._tool_def(
                "gallery_update",
                "更新图库中图片的描述。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图片 ID（如 gallery_xxx）"},
                        "description": {"type": "string", "description": "新的描述"},
                    },
                    "required": ["image_id", "description"],
                },
            ),
            self._tool_def(
                "gallery_delete",
                "删除图库中的图片。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图片 ID"},
                    },
                    "required": ["image_id"],
                },
            ),
            self._tool_def(
                "gallery_rename",
                "重命名图库中的图片。",
                {
                    "properties": {
                        "image_id": {"type": "string", "description": "图片 ID"},
                        "name": {"type": "string", "description": "新的图片名称"},
                    },
                    "required": ["image_id", "name"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown gallery tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_gallery_list(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 50))
    return_paths = bool(args.get("return_paths", False))
    try:
        offset = (page - 1) * page_size
        images = await self._image_service.list_images(limit=page_size, offset=offset)
        items = [_format_image_item(img, return_paths) for img in images]
        return _json({"ok": True, "items": items, "total": len(items)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_gallery_search(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    keyword = str(args.get("keyword", "")).strip()
    return_paths = bool(args.get("return_paths", False))
    try:
        images = await self._image_service.search_images(keyword)
        items = [_format_image_item(img, return_paths) for img in images]
        return _json({"ok": True, "items": items, "total": len(items)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_gallery_add(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    image_path = str(args.get("image_path", "")).strip()
    description = args.get("description", None)
    if not image_path:
        return _json({"ok": False, "error": "缺少 image_path"})
    path = Path(image_path)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {image_path}"})
    try:
        from neobot_app.message.image_pipeline import prepare_local_image
        prepared = prepare_local_image(path)
        if prepared is None:
            return _json({"ok": False, "error": "无法处理图片"})
        record = await self._image_service.gallery_add(
            image_id=prepared.file_hash,
            description=description,
        )
        return _json({"ok": True, "image_id": record.image_id, "path": record.file_path})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_gallery_update(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    image_id = str(args.get("image_id", "")).strip()
    description = str(args.get("description", "")).strip()
    if not image_id or not description:
        return _json({"ok": False, "error": "缺少 image_id 或 description"})
    try:
        record = await self._image_service.update_image_description(
            image_id=image_id, description=description
        )
        return _json({"ok": True, "image_id": record.image_id, "description": record.description})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_gallery_delete(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    image_id = str(args.get("image_id", "")).strip()
    if not image_id:
        return _json({"ok": False, "error": "缺少 image_id"})
    try:
        result = await self._image_service.gallery_delete(image_id=image_id)
        return _json({"ok": bool(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_gallery_rename(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    image_id = str(args.get("image_id", "")).strip()
    name = str(args.get("name", "")).strip()
    if not image_id or not name:
        return _json({"ok": False, "error": "缺少 image_id 或 name"})
    try:
        record = await self._image_service.gallery_rename(image_id=image_id, new_name=name)
        return _json({"ok": True, "image_id": record.image_id, "name": name})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "gallery_list": _handle_gallery_list,
    "gallery_search": _handle_gallery_search,
    "gallery_add": _handle_gallery_add,
    "gallery_update": _handle_gallery_update,
    "gallery_delete": _handle_gallery_delete,
    "gallery_rename": _handle_gallery_rename,
}

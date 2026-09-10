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
            "  gallery_list — 分页列出图库图片（含编号、描述、创建时间）\n"
            "  gallery_search — 按关键词搜索图库图片（搜索描述和 prompt 字段）\n"
            "  gallery_add — 将图片加入图库（需指定 name）\n"
            "  gallery_update — 更新图库图片的描述信息\n"
            "  gallery_delete — 删除图库图片\n"
            "  gallery_rename — 重命名图库图片\n"
            "  gallery_batch_add_from_chat — 批量从聊天消息导入多张图片到图库（一次 API 调用）\n\n"

            "【查找图库图片（操作指导）】\n"
            "  1. 如果用户提到了具体的图片描述、角色名、风格等，优先用 gallery_search\n"
            "  2. 支持多关键词搜索：用空格分隔多个词（如「弥音 立绘」），"
            "全部命中的结果排在最前，用于精确查找角色立绘\n"
            "  3. 如果 gallery_search 返回空，尝试换关键词或更宽泛的搜索词\n"
            "  4. 如果用户只是想浏览图库内容，用 gallery_list 分页查看\n"
            "  5. gallery_list 和 gallery_search 返回的每个结果都有一个编号\n"
            "     - 此编号可直接用于 drawing__draw 的 reference_id 参数\n"
            "     - 也可用于 image_pool__put(source=\"gallery:<编号>\") 存入缓存池\n"
            "  6. 如果找不到用户描述的图片，如实告知，不要编造编号\n\n"

            "【角色立绘参考（配合绘图）】\n"
            "  绘图请求涉及角色时，务必先搜索图库是否有该角色立绘：\n"
            "    - 用角色名 + 特征词搜索（如「弥音 立绘」「sakura standing」）\n"
            "    - 搜索 bot 自己的形象时用角色名或特征（粉色头发/猫娘等）\n"
            "    - 找到立绘后把编号交给 drawing__draw 作为 reference_id 参考生图\n\n"

            "【图片命名规范】\n"
            "  将图片加入图库（gallery_add）时：\n"
            "    - 如果用户指定了名称，使用用户指定的\n"
            "    - 如果未指定，根据图片内容生成简短英文名（如 'sunset_ocean'、'character_standing'）\n"
            "    - 不要使用 image_id 格式的名称（如 tmp_xxx、g_xxx）\n"
            "    - 名称仅含字母、数字、下划线、连字符，不超过 100 字符\n"
            "    - 入库后可用 gallery_rename 改名\n\n"

            "【角色立绘命名格式】\n"
            "  对于角色立绘类图片，建议命名包含角色特征便于搜索：\n"
            "    - 格式：<角色/特征>_<姿势/场景>_<序号>\n"
            "    - 示例：'sakura_standing_01'、'swimsuit_sitting_02'、'uniform_front_view'\n"
            "    - 这样后续用 gallery_search 搜索 'sakura' 或 'standing' 都能找到\n\n"

            "【立绘与QQ用户关联标注（强制）】\n"
            "  存储或更新立绘（角色图/人设图/用户形象等）时：\n"
            "  1. 如果该立绘与某个QQ用户强相关——例如：该用户的角色/OC/人设、"
            "为用户本人或其亲友绘制的形象、聊天中明确属于某人（谁的女朋友/谁的设子/谁的皮套）的立绘——\n"
            "     必须在 description（资料）中明确写入对应相关者的QQ号\n"
            "  2. 写入格式：在描述中加入「相关者QQ:<QQ号>」（如「相关者QQ:123456789」），"
            "可放在描述开头或结尾；同一人的多张立绘保持一致的写法，便于 gallery_search 检索\n"
            "  3. 只有完全不与任何QQ用户相关的立绘（风景/静物/通用角色等）才不需要标注\n"
            "  4. 立绘入库时（gallery_add / gallery_batch_add_from_chat）就应写入；"
            "遗漏时用 gallery_update 补充，不要省略\n"
            "  5. 判断相关者以聊天上下文为准（消息发送者/被@对象/明确提及的QQ号）；"
            "拿不准是否强相关时倾向标注（标注冗余优于漏标，便于后续检索归属）\n\n"

            "【批量从聊天导入】\n"
            "  当用户一条消息发了多张图片并希望全部加入图库时，用 gallery_batch_add_from_chat：\n"
            "    - 必填 msg_number 或 message_id\n"
            "    - image_indices 不填则导入消息中所有图片\n"
            "    - name_prefix 可选，最终图片名 = name_prefix + '_' + 索引\n"
            "    - 单次工具调用完成全部入库，避免多次 import_chat_image\n"
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
                        "description": {
                            "type": "string",
                            "description": "可选，图片描述。存储立绘（角色/人设/用户形象）且与某个QQ用户强相关时，"
                            "必须在描述中明确写入其QQ号（格式「相关者QQ:<QQ号>」）；完全不与人相关的图片可不写",
                        },
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
                        "description": {
                            "type": "string",
                            "description": "新的描述。立绘与某个QQ用户强相关时，描述中必须包含相关者QQ号（格式「相关者QQ:<QQ号>」）",
                        },
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
            self._tool_def(
                "gallery_batch_add_from_chat",
                "批量从聊天消息导入多张图片到图库。一次 get_msg 调用拉取消息，逐张下载入库。",
                {
                    "properties": {
                        "msg_number": {
                            "type": "integer",
                            "description": "聊天记录中的消息编号（如「75: 用户名: [图片]」中的75）",
                        },
                        "message_id": {
                            "type": "integer",
                            "description": "可选，直接用 OneBot 消息 ID（优先级低于 msg_number）",
                        },
                        "image_indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，1-based 索引列表（如 [1,2,3]）；不填则导入该消息中的全部图片",
                        },
                        "description": {
                            "type": "string",
                            "description": "可选，对每张图片应用的描述。立绘（角色/人设/用户形象）与某个QQ用户强相关时，"
                            "描述中必须包含相关者QQ号（格式「相关者QQ:<QQ号>」）",
                        },
                        "name_prefix": {
                            "type": "string",
                            "description": "可选，图片名前缀，自动按索引生成后缀",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown gallery tool: {tool_name}"})
        return await handler(self, args)

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
        from neobot_app.message.image_pipeline import prepare_local_image_async
        prepared = await prepare_local_image_async(path)
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

async def _handle_gallery_batch_add_from_chat(self: GallerySkill, args: dict) -> str:
    if self._image_service is None:
        return _json({"ok": False, "error": "图库服务未配置"})
    msg_number = args.get("msg_number")
    message_id_arg = args.get("message_id")
    image_indices = args.get("image_indices") or None
    description = args.get("description")
    name_prefix = str(args.get("name_prefix", "") or "").strip() or None

    # 解析真实 message_id：优先用 numbering_mapping 翻译 msg_number
    real_message_id: int | None = None
    numbering_mapping = args.get("_numbering_mapping")
    if msg_number is not None:
        if isinstance(numbering_mapping, dict):
            mapping = {int(k): int(v) for k, v in numbering_mapping.items()}
            real_message_id = mapping.get(int(msg_number))
        if real_message_id is None:
            return _json({"ok": False, "error": f"无法从编号映射获得 msg_number={msg_number} 的真实消息 ID（请确认编号或使用 message_id 参数）"})
    elif message_id_arg is not None:
        real_message_id = int(message_id_arg)
    else:
        return _json({"ok": False, "error": "请提供 msg_number 或 message_id"})

    indices_list: list[int] | None = None
    if image_indices and isinstance(image_indices, list):
        indices_list = [int(i) for i in image_indices if int(i) > 0]

    try:
        # target=gallery 时 _ensure_gallery_enabled 在 import_chat_images 中处理
        results = await self._image_service.import_chat_images(
            message_id=real_message_id,
            image_indices=indices_list,
            target="gallery",
            description=description,
            name=name_prefix,
        )
        ok_count = sum(1 for r in results if r.get("ok"))
        return _json({
            "ok": ok_count > 0,
            "imported": ok_count,
            "total": len(results),
            "results": results,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "gallery_list": _handle_gallery_list,
    "gallery_search": _handle_gallery_search,
    "gallery_add": _handle_gallery_add,
    "gallery_update": _handle_gallery_update,
    "gallery_delete": _handle_gallery_delete,
    "gallery_rename": _handle_gallery_rename,
    "gallery_batch_add_from_chat": _handle_gallery_batch_add_from_chat,
}

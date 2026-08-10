"""DrawingSkill — AI 绘图（提交/查询/冷却管理/图片后处理）。

生图指导参考 codex imagegen SKILL 提炼(中文精简版),
结合本 bot 场景:图库角色立绘参考、外接生图 API(GPT image-2 为主,
从不请求原生透明背景,透明用本地去底处理)。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class DrawingSkill(SkillModule):
    """AI 绘图 Skill — 提交绘图任务、查询状态、取消冷却、图片后处理。"""

    def __init__(
        self,
        drawing_manager: Any = None,
        image_service: Any = None,
        vision_provider: Any = None,
        enable_image_inspect: bool = False,
    ) -> None:
        self._drawing_manager = drawing_manager
        self._image_service = image_service
        self._vision_provider = vision_provider
        self._enable_image_inspect = enable_image_inspect

    @property
    def name(self) -> str:
        return "drawing"

    @property
    def description(self) -> str:
        return "AI绘图：提交绘图任务（支持参考图/垫图/图生图）、图片后处理（缩放/裁切/去底透明）、查询状态"

    @property
    def instructions(self) -> str:
        parts = [
            "AI 绘图 Skill 提供以下能力：\n"
            "  draw — 提交绘图任务，后台异步完成（参考图/垫图/图生图）\n"
            "  check_draw_status — 查询绘图状态和剩余冷却\n"
            "  cancel_draw_cooldown — 取消冷却期\n"
            "  process_image — 本地图片后处理（缩放/裁切/格式转换/去底透明）",
        ]

        if self._enable_image_inspect:
            parts.append(
                "  inspect_image — 检查图片内容（尺寸/描述，需视觉模型支持）"
            )

        parts.extend(
            [
                "【角色立绘参考规则（强制）】\n"
                "涉及任何角色（群友 OC、动画角色、甚至你自己）的绘图请求：\n"
                "  1. 先用 gallery_search 搜索该角色名/特征，检查图库是否有立绘\n"
                "     - 多关键词可空格分隔（如「弥音 立绘」），提高匹配精度\n"
                "     - 搜索你自己的形象时，用「弥音」或你的角色特征（粉色头发、猫娘等）\n"
                "  2. 有立绘 → 将编号填入 draw 的 reference_id（或 references），参考立绘生图\n"
                "  3. 没有 → 如实告知用户「图库没有该角色立绘，将按描述创作」，然后正常绘图\n"
                "  4. 用户明确表示「不用参考/随意画/自由发挥/别看图库」时，跳过查图库\n\n"
                "【参考绘图工作流】\n"
                "  1. 调用 gallery_search 查找目标图片（关键词搜索，空则换词或 gallery_list 浏览）\n"
                "  2. 将编号填入 draw 的 reference_id（单张）或 references（多张）\n"
                "  3. 图暂存缓存池时用 pool:<key> 引用\n\n"
                "【references 参数完整格式】\n"
                "  数组每项支持：\n"
                "  - 图库编号：如 \"3\"（来自 gallery_list/gallery_search 返回的编号）\n"
                "  - 缓存池：\"pool:<key>\"\n"
                "  - 表情包：\"emoji:<编号>\"\n"
                "  - 外部链接：\"url:<URL>\"\n"
                "  - 本地文件：\"file:<路径>\"\n"
                "  - 聊天图片：\"chat:<message_id>\" 或 \"chat:<message_id>:<image_index>\"（index 默认 1）\n\n"
                "【提示词编写规范（精简指导）】\n"
                "  1. 结构顺序：场景/背景 → 主体 → 细节 → 约束\n"
                "  2. 用户描述已经很具体时，只做规范化整理，不要擅自添加新内容\n"
                "  3. 用户描述笼统时，可做克制增强（构图/风格/氛围），但不得添加未提及的角色、物件、品牌、文案\n"
                "  4. 参考绘图时，严禁在 prompt 中重复描述参考图的角色外观特征，只描述动作/场景/构图/风格\n"
                "     - 正确：'参考图中角色，坐在椅子上，背景为图书馆'\n"
                "     - 错误：'一个银发红瞳穿水手服的少女坐在椅子上' ← 外观由参考图决定\n"
                "  5. 多张参考图用'参考图一''参考图二'指定\n"
                "  6. 图片中需要精确文字时：文字加引号、生僻词逐字母拼写、要求逐字渲染且不添加多余字符\n"
                "  7. 编辑（图生图）时明确不变项：'只改 X，保持 Y 不变'，迭代时重复关键约束\n"
                "  8. 迭代原则：一次只改一个点，避免整段重写\n\n"
                "【透明背景策略】\n"
                "  - 从不请求原生透明背景（外接生图 API 的透明功能不可靠）\n"
                "  - 需要透明/抠图时：生成时用纯色背景（如纯绿 #00ff00，主体不用该色），"
                "再调用 process_image(operation=\"remove_background\") 本地去底\n\n"
                "【图片尺寸】\n"
                "  常用尺寸：512x512（方形头像）、1024x1024（方形）、768x1024（竖向）、1024x768（横向）\n"
                "  未指定时默认 1024x1024\n\n"
                "【process_image 用法】\n"
                "  参数 image 支持图片 ID（tmp_xxx / g_xxx）或来源描述符（gallery:<编号>/emoji:<编号>/file:<路径>/url:<URL>/chat:<消息ID>:<索引>）\n"
                "  操作：resize（等比缩放，传 width/height）、crop（crop_box=[左,上,右,下]）、"
                "to_png / to_jpeg（格式转换）、remove_background（去底透明，可指定 background_color）\n"
                "  处理结果保存到临时目录并返回新图片 ID，可直接发送或入库\n\n"
                "【重要提醒】\n"
                "  - draw 提交后立即返回，绘图在后台进行，不要等待，不要回复'正在生成中请稍等'后保持等待\n"
                "  - 告知用户'绘图已提交，完成后会通知'即可\n"
                "  - 如果用户要的是聊天图片而非图库图片，先用 image_pool__put 存入缓存池，再用 pool:key 引用",
            ]
        )
        return "\n\n".join(parts)

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        tools = [
            self._tool_def(
                "draw",
                "AI绘图。支持参考图/垫图/图生图。绘图为后台任务，提交后立即返回，完成后会通知主Agent。"
                "涉及角色时先查图库立绘并参考（见操作说明）。",
                {
                    "properties": {
                        "prompt": {"type": "string", "description": "绘图提示词（正向描述，编写规范见操作说明）"},
                        "negative_prompt": {"type": "string", "description": "可选，负面提示词"},
                        "image_size": {"type": "string", "description": "可选，图片尺寸，如 512x512、1024x1024"},
                        "reference_id": {"type": "integer", "description": "可选，参考图 ID（图库中已有图片）"},
                        "references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，参考图路径列表（图库编号/池/表情包/url/file/chat 格式）",
                        },
                        "seed": {"type": "integer", "description": "可选，随机种子"},
                        "requester": {"type": "string", "description": "可选，委托者描述"},
                        "requirements": {"type": "string", "description": "可选，绘图要求描述"},
                    },
                    "required": ["prompt"],
                },
            ),
            self._tool_def(
                "check_draw_status",
                "查询指定会话管线的后台绘图状态（冷却剩余、活跃任务、近期完成）。",
                {
                    "properties": {
                        "pipeline_key": {"type": "string", "description": "可选，管线标识，不填则使用当前会话"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "cancel_draw_cooldown",
                "取消当前管线的绘图冷却限制。",
                {
                    "properties": {
                        "pipeline_key": {"type": "string", "description": "可选，管线标识"},
                    },
                    "required": [],
                },
            ),
        ]
        if self._image_service is not None:
            tools.append(
                self._tool_def(
                    "process_image",
                    "本地图片后处理：缩放、裁切、格式转换、去底透明。"
                    "image 参数支持图片 ID（如 tmp_xxx / g_xxx）或来源描述符"
                    "（gallery:<编号>/emoji:<编号>/file:<路径>/url:<URL>/chat:<消息ID>:<索引>）。"
                    "处理结果保存到临时目录并返回新图片 ID。",
                    {
                        "properties": {
                            "image": {"type": "string", "description": "图片来源：图片 ID 或来源描述符"},
                            "operation": {
                                "type": "string",
                                "enum": ["resize", "crop", "to_png", "to_jpeg", "remove_background"],
                                "description": "操作：resize=等比缩放；crop=裁切；to_png/to_jpeg=格式转换；remove_background=纯色背景去底透明",
                            },
                            "width": {"type": "integer", "description": "可选，resize 目标宽度（只传一个时按单边等比）"},
                            "height": {"type": "integer", "description": "可选，resize 目标高度（只传一个时按单边等比）"},
                            "crop_box": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "可选，crop 裁切区域 [left, top, right, bottom]",
                            },
                            "quality": {"type": "integer", "description": "可选，to_jpeg 质量（1-100）"},
                            "background_color": {
                                "type": "string",
                                "description": "可选，remove_background 的键色（如 #00ff00），不指定则自动从边框采样",
                            },
                        },
                        "required": ["image", "operation"],
                    },
                )
            )
        if self._enable_image_inspect and self._image_service is not None:
            tools.append(
                self._tool_def(
                    "inspect_image",
                    "检查图片内容：返回图片尺寸与视觉模型描述。"
                    "用于绘图结果验证、图片内容确认等。需要视觉模型支持。",
                    {
                        "properties": {
                            "image": {"type": "string", "description": "图片来源：图片 ID 或来源描述符"},
                            "requirement": {
                                "type": "string",
                                "description": "可选，检查要求，默认描述图片内容",
                                "default": "请简洁描述这张图片的主要内容",
                            },
                        },
                        "required": ["image"],
                    },
                )
            )
        return tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None and tool_name in ("process_image", "inspect_image"):
            return await self._execute_image_tool(tool_name, args)
        if handler is None:
            return _json({"ok": False, "error": f"unknown drawing tool: {tool_name}"})
        return await handler(self, args)

    async def _execute_image_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """process_image / inspect_image 的统一执行(依赖 image_service)。"""
        if self._image_service is None:
            return _json({"ok": False, "error": "image_service 未配置"})
        image = str(args.get("image") or "").strip()
        if not image:
            return _json({"ok": False, "error": "缺少 image 参数"})
        try:
            if tool_name == "process_image":
                record = await self._image_service.process_image(
                    image=image,
                    operation=str(args.get("operation") or ""),
                    width=args.get("width"),
                    height=args.get("height"),
                    crop_box=args.get("crop_box"),
                    quality=args.get("quality"),
                    background_color=args.get("background_color"),
                    image_source="skill_process",
                )
                return _json({
                    "ok": True,
                    "image_id": record.image_id,
                    "source": record.source,
                    "file_path": record.file_path,
                    "width": record.original_width,
                    "height": record.original_height,
                    "message": "处理完成，图片已保存到临时目录，可直接发送或入库",
                })
            if tool_name == "inspect_image":
                return await self._inspect_image(image, args)
        except Exception as exc:
            return _json({"ok": False, "error": f"处理失败: {exc}"})
        return _json({"ok": False, "error": f"unknown drawing tool: {tool_name}"})

    async def _inspect_image(self, image: str, args: dict[str, Any]) -> str:
        """inspect_image 实现:解析图片 → 视觉模型描述(未配置视觉模型时返回尺寸信息)。"""
        path = await self._image_service._resolve_process_source(image)
        from PIL import Image

        with Image.open(path) as opened:
            width, height = opened.size
            size_info = {"width": width, "height": height}
        if self._vision_provider is None:
            return _json({
                "ok": False,
                "error": "视觉模型未配置，仅返回图片尺寸信息",
                "size": size_info,
            })
        from neobot_app.image.parser import _build_vision_image_part

        requirement = str(args.get("requirement") or "请简洁描述这张图片的主要内容")
        messages: list[dict] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": requirement},
                    _build_vision_image_part(path.read_bytes()),
                ],
            }
        ]
        response = await self._vision_provider.chat(messages)
        description = str(response.get("content") or "") if isinstance(response, dict) else ""
        return _json({
            "ok": True,
            "size": size_info,
            "description": description.strip() or "（无描述）",
        })

# ── Handlers ──

async def _handle_draw(self: DrawingSkill, args: dict) -> str:
    if self._drawing_manager is None:
        return _json({"ok": False, "error": "drawing_manager 未配置"})

    pipeline_key = str(args.get("pipeline_key", "") or "")
    conversation_kind = ""
    conversation_id = ""
    if ":" in pipeline_key:
        conversation_kind, conversation_id = pipeline_key.split(":", 1)

    prompt = str(args.get("prompt", "") or "")
    if not prompt.strip():
        return _json({"ok": False, "error": "prompt 不能为空"})

    reference_id = args.get("reference_id")
    if reference_id is not None:
        try:
            reference_id = int(reference_id)
        except (TypeError, ValueError):
            reference_id = None

    seed = args.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            seed = None

    return await self._drawing_manager.submit(
        pipeline_key=pipeline_key,
        conversation_kind=conversation_kind,
        conversation_id=conversation_id,
        prompt=prompt,
        requester=str(args.get("requester", "") or ""),
        requirements=str(args.get("requirements", "") or ""),
        references=_translate_chat_refs(args.get("references"), args),
        reference_id=reference_id,
        negative_prompt=str(args.get("negative_prompt", "") or "") or None,
        image_size=str(args.get("image_size", "") or "") or None,
        seed=seed,
    )

async def _handle_check_draw_status(self: DrawingSkill, args: dict) -> str:
    if self._drawing_manager is None:
        return _json({"ok": False, "error": "drawing_manager 未配置"})
    pipeline_key = args.get("pipeline_key", "")
    status = self._drawing_manager.get_pipeline_status(pipeline_key) if pipeline_key else {}
    return _json({"ok": True, "status": status})

async def _handle_cancel_draw_cooldown(self: DrawingSkill, args: dict) -> str:
    if self._drawing_manager is None:
        return _json({"ok": False, "error": "drawing_manager 未配置"})
    pipeline_key = args.get("pipeline_key", "")
    if pipeline_key:
        self._drawing_manager.cancel_cooldown(pipeline_key)
    return _json({"ok": True})

def _translate_chat_refs(references: Any, args: dict) -> Any:
    """将 references 中 chat:<msg_number> 的显示编号翻译为真实 message_id。"""
    if not references or not isinstance(references, list):
        return references

    def _translate_one(ref: str) -> str:
        if not isinstance(ref, str) or not ref.startswith("chat:"):
            return ref
        rest = ref[len("chat:"):]
        parts = rest.split(":")
        try:
            display_number = int(parts[0])
        except (ValueError, IndexError):
            return ref
        numbering_mapping = args.get("_numbering_mapping")
        if not isinstance(numbering_mapping, dict):
            return ref
        numbering_mapping = {int(k): int(v) for k, v in numbering_mapping.items()}
        real_id = numbering_mapping.get(display_number)
        if real_id is None:
            return ref
        img_idx = parts[1] if len(parts) > 1 else "1"
        return f"chat:{real_id}:{img_idx}"

    return [_translate_one(r) for r in references]


_HANDLERS = {
    "draw": _handle_draw,
    "check_draw_status": _handle_check_draw_status,
    "cancel_draw_cooldown": _handle_cancel_draw_cooldown,
}

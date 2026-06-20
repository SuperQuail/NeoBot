"""DrawingSkill — AI 绘图（提交/查询/冷却管理）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class DrawingSkill(SkillModule):
    """AI 绘图 Skill — 提交绘图任务、查询状态、取消冷却。"""

    @property
    def name(self) -> str:
        return "drawing"

    @property
    def description(self) -> str:
        return "AI绘图：提交绘图任务（支持参考图/垫图/图生图），查询状态，取消冷却"

    @property
    def instructions(self) -> str:
        return (
            "AI 绘图 Skill 提供以下能力：\n\n"
            "  draw — 提交绘图任务，后台异步完成\n"
            "  check_draw_status — 查询绘图状态和剩余冷却\n"
            "  cancel_draw_cooldown — 取消冷却期\n\n"

            "【参考绘图工作流（重要）】\n"
            "当用户要求参考图库中的某张图片来绘图时，按以下步骤操作：\n\n"
            "  1. 调用 gallery_search 查找目标图片\n"
            "     - 用关键词搜索（如角色名、图片描述等）\n"
            "     - 如果 gallery_search 返回空，尝试 gallery_list 浏览全部\n"
            "  2. 将搜索结果中的编号填入 draw 的 reference_id 参数\n"
            "     - 单张参考：reference_id=<编号>\n"
            "     - 多张参考：references=[\"<编号1>\", \"<编号2>\"]\n"
            "  3. 如果有参考图暂存在缓存池中，也可用 pool:<key> 格式引用\n"
            "  4. 编写绘图 prompt（见下方约束）\n\n"

            "【references 参数完整格式】\n"
            "references 数组中的每个字符串支持以下格式：\n"
            "  - 图库编号：直接写数字字符串，如 \"3\"（来自 gallery_list/gallery_search 返回的编号）\n"
            "  - 缓存池：\"pool:<key>\"，如 \"pool:a1b2c3d4\"\n"
            "  - 表情包：\"emoji:<编号>\"，如 \"emoji:5\"\n"
            "  - 外部链接：\"url:<URL>\"，如 \"url:https://example.com/img.jpg\"\n"
            "  - 本地文件：\"file:<路径>\"，如 \"file:/data/images/ref.png\"\n"
            "  - 聊天图片：\"chat:<message_id>\" 或 \"chat:<message_id>:<image_index>\"（index 默认 1）\n\n"

            "【提示词编写约束（必须遵守）】\n"
            "  1. 提示词使用自然语言，中文或英文均可\n"
            "  2. 参考绘图时，严禁在 prompt 中描述参考图中的角色特征\n"
            "     - 正确：'参考图中角色，坐在椅子上，背景为图书馆'\n"
            "     - 错误：'一个银发红瞳穿水手服的少女坐在椅子上' ← 这些特征来自参考图，不要重复描述\n"
            "  3. 多张参考图时，使用'参考图一'、'参考图二'的方式指定\n"
            "  4. prompt 只需描述你想要的动作/场景/构图/风格，角色外观由参考图决定\n\n"

            "【图片尺寸】\n"
            "  常用尺寸：512x512（方形头像）、1024x1024（方形）、768x1024（竖向）、1024x768（横向）\n"
            "  根据用户需求选择合适的尺寸，未指定时默认 1024x1024\n\n"

            "【重要提醒】\n"
            "  - draw 提交后立即返回，绘图在后台进行，不要等待\n"
            "  - 不要在回复中说'正在生成中请稍等'并保持等待状态\n"
            "  - 告知用户'绘图已提交，完成后会通知'即可\n"
            "  - 如果用户要的是聊天图片而非图库图片，先用 image_pool__put 存入缓存池，再用 pool:key 引用\n"
        )

    def __init__(self, drawing_manager: Any = None) -> None:
        self._drawing_manager = drawing_manager

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "draw",
                "AI绘图。支持参考图/垫图/图生图。绘图为后台任务，提交后立即返回，完成后会通知主Agent。",
                {
                    "properties": {
                        "prompt": {"type": "string", "description": "绘图提示词（正向描述）"},
                        "negative_prompt": {"type": "string", "description": "可选，负面提示词"},
                        "image_size": {"type": "string", "description": "可选，图片尺寸，如 512x512、1024x1024"},
                        "reference_id": {"type": "integer", "description": "可选，参考图 ID（图库中已有图片）"},
                        "references": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，参考图路径列表",
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

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown drawing tool: {tool_name}"})
        return await handler(self, args)

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

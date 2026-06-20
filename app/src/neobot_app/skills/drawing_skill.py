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
            "  draw — 提交绘图任务（支持参考图/垫图/图生图），后台异步完成\n"
            "  check_draw_status — 查询指定管线的绘图状态和剩余冷却\n"
            "  cancel_draw_cooldown — 取消当前管线的冷却期\n\n"
            "注意：绘图任务会加入后台任务，完成后会另外通知，不需要等待。"
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

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


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
        references=args.get("references"),
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


_HANDLERS = {
    "draw": _handle_draw,
    "check_draw_status": _handle_check_draw_status,
    "cancel_draw_cooldown": _handle_cancel_draw_cooldown,
}

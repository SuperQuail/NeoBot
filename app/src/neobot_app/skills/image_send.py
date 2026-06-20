"""ImageSendSkill — 图片发送。"""

from __future__ import annotations

import json
from pathlib import Path
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
            "注意：如果图片在图库中，提供 image_id；如果是本地文件，提供 file_path；"
            "如果是缓存池中的图片，提供 pool_key 和 pipeline_key。"
        )

    def __init__(
        self,
        adapter: Any = None,
        file_server: Any = None,
        image_pool: Any = None,
    ) -> None:
        self._adapter = adapter
        self._file_server = file_server
        self._image_pool = image_pool

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        tools = [
            self._tool_def(
                "send_image",
                "发送图片到指定群聊或私聊。支持图库图片 ID、本地文件路径或缓存池 key。",
                {
                    "properties": {
                        "image_id": {"type": "integer", "description": "可选，图库图片 ID"},
                        "file_path": {"type": "string", "description": "可选，本地图片路径（沙箱内路径）"},
                        "pool_key": {"type": "string", "description": "可选，缓存池中的图片 key（需配合 pipeline_key 使用）"},
                        "pipeline_key": {"type": "string", "description": "可选，管线标识（格式为 kind:id），使用 pool_key 时需提供"},
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

# ── Handlers ──

async def _handle_send_image(self: ImageSendSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    if self._file_server is None:
        return _json({"ok": False, "error": "file_server 未配置"})

    image_id = args.get("image_id")
    file_path = str(args.get("file_path", "")).strip()
    pool_key = str(args.get("pool_key", "")).strip()
    pipeline_key = str(args.get("pipeline_key", "")).strip()
    group_id = str(args.get("group_id", "")).strip()
    user_id = str(args.get("user_id", "")).strip()

    if not group_id and not user_id:
        return _json({"ok": False, "error": "缺少 group_id 或 user_id"})
    if not image_id and not file_path and not pool_key:
        return _json({"ok": False, "error": "缺少 image_id、file_path 或 pool_key"})

    try:
        from neobot_app.utils.media_sender import prepare_image_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        # 根据 pool_key / image_id / file_path 获取图片路径
        if pool_key:
            if self._image_pool is None:
                return _json({"ok": False, "error": "image_pool 未配置"})
            if not pipeline_key or ":" not in pipeline_key:
                return _json({"ok": False, "error": "使用 pool_key 时需要 pipeline_key（格式 kind:id）"})
            staged = self._image_pool.get(pipeline_key, pool_key)
            if staged is None:
                return _json({"ok": False, "error": f"缓存池中不存在 pool_key={pool_key}（可能已过期）"})
            path = staged.file_path
        elif file_path:
            path = Path(file_path)
            if not path.exists():
                return _json({"ok": False, "error": f"文件不存在: {file_path}"})
        elif image_id:
            from neobot_app.core import DATA_DIR
            gallery_dir = DATA_DIR / "creator" / "gallery"
            candidates = list(gallery_dir.glob(f"{image_id}.*"))
            if not candidates:
                return _json({"ok": False, "error": f"图库不存在 image_id={image_id}"})
            path = candidates[0]

        segment = prepare_image_segment(self._file_server, path)
        resp = await self._adapter.send(conv_ref, [segment])

        # 检查 go-cqhttp API 响应状态
        if resp is None:
            return _json({"ok": False, "error": "发送超时，无响应"})
        if hasattr(resp, "status") and hasattr(resp, "retcode"):
            if resp.status == "failed" or (resp.retcode is not None and resp.retcode != 0):
                msg = resp.message or resp.wording or str(resp.retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={resp.retcode}): {msg}"})
        elif isinstance(resp, dict):
            r_status = resp.get("status")
            r_retcode = resp.get("retcode")
            if r_status == "failed" or (r_retcode is not None and r_retcode != 0):
                msg = resp.get("message") or resp.get("wording") or str(r_retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={r_retcode}): {msg}"})
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": f"发送失败: {e}"})

_HANDLERS = {
    "send_image": _handle_send_image,
}

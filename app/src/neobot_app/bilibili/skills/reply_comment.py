"""BilibiliCommentSkill — 评论回复与取消工具。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BilibiliCommentSkill(SkillModule):
    """B站评论操作 Skill — 发送回复或跳过评论。"""

    @property
    def name(self) -> str:
        return "bilibili_comment"

    @property
    def description(self) -> str:
        return "B站评论操作：回复评论、跳过评论"

    @property
    def instructions(self) -> str:
        return (
            "B站评论操作 Skill 提供以下能力：\n\n"
            "  reply_comment — 向B站评论区发送回复。需提供稿件/动态oid、根评论root、父评论parent、回复文本text、内容类型type_(1=视频/12=专栏/17=动态)。\n"
            "  cancel_reply — 跳过当前评论不回复（需提供跳过原因）。\n\n"
            "使用 reply_comment 时：\n"
            "- oid 从评论区上下文获取（待回复评论所属的稿件/动态ID）\n"
            "- root 是被回复评论的根评论rpid，parent 是直接父评论rpid\n"
            "- 回复文本应当自然简短，不要使用markdown格式\n"
            "- 如果评论不值得回复（刷屏/无意义/已回复过），优先使用 cancel_reply 跳过"
        )

    def __init__(self, client: Any = None) -> None:
        self._client = client

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._client is None:
            return []
        return [
            self._tool_def(
                "reply_comment",
                "向B站评论发送回复。调用此工具前确保已确认需要回复该评论。",
                {
                    "properties": {
                        "oid": {
                            "type": "integer",
                            "description": "稿件/动态ID（oid）",
                        },
                        "root": {
                            "type": "integer",
                            "description": "根评论rpid（被回复的顶层评论ID）",
                        },
                        "parent": {
                            "type": "integer",
                            "description": "父评论rpid（直接父评论ID，回复顶层评论时等于root）",
                        },
                        "text": {
                            "type": "string",
                            "description": "回复文本内容，简短自然，不使用markdown格式",
                        },
                        "type_": {
                            "type": "integer",
                            "description": "内容类型: 1=视频, 12=专栏, 17=动态，默认1",
                        },
                    },
                    "required": ["oid", "root", "parent", "text"],
                },
            ),
            self._tool_def(
                "cancel_reply",
                "跳过当前评论不回复。当评论不值得回复（刷屏/无意义/已回复过）时使用此工具。",
                {
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "跳过原因简述",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": p},
        }


# ── Handlers ──

async def _handle_reply_comment(self: BilibiliCommentSkill, args: dict) -> str:
    if self._client is None:
        return _json({"ok": False, "error": "BilibiliClient 未配置"})

    oid = int(args.get("oid", 0))
    root = int(args.get("root", 0))
    parent = int(args.get("parent", 0))
    text = str(args.get("text", "")).strip()
    type_ = int(args.get("type_", 1))

    if not oid or not root or not parent or not text:
        return _json({"ok": False, "error": "缺少必要参数 (oid/root/parent/text)"})

    try:
        ok = await self._client.send_comment_reply(
            oid=oid, root=root, parent=parent, text=text, type_=type_
        )
        if ok:
            return _json({"ok": True, "message": f"回复成功 (oid={oid}, rpid={parent})"})
        return _json({"ok": False, "error": "API返回失败，可能被风控或评论已关闭"})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_cancel_reply(self: BilibiliCommentSkill, args: dict) -> str:
    reason = str(args.get("reason", "")).strip()
    return _json({"ok": True, "cancelled": True, "reason": reason or "agent 主动跳过"})


_HANDLERS = {
    "reply_comment": _handle_reply_comment,
    "cancel_reply": _handle_cancel_reply,
}

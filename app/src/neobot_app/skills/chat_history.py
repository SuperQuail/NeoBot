"""ChatHistorySkill — 历史消息拉取。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.message.process import history_message_to_text
from neobot_app.skills.base import SkillModule

#: 单次返回的总字符上限：工具结果会整体进入模型上下文，必须封顶。
_MAX_OUTPUT_CHARS = 6000
#: 单条消息的字符上限，避免一条超长转发吃掉全部预算。
_MAX_ITEM_CHARS = 600
#: 请求条数的上下限（与工具描述保持一致）。
_MIN_COUNT = 1
_MAX_COUNT = 50
_DEFAULT_COUNT = 20


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _coerce_int(value: Any, default: int, *, low: int, high: int | None = None) -> int:
    """把工具入参收敛到合法整数：非法值回落默认，越界钳制。"""
    if isinstance(value, bool) or value is None:
        parsed = default
    else:
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            parsed = default
    if parsed < low:
        parsed = low
    if high is not None and parsed > high:
        parsed = high
    return parsed


def _coerce_bool(value: Any) -> bool:
    """接受 bool 与 "true"/"false" 文本；其余一律按 False。

    模型经常把布尔参数写成字符串，直接 bool("false") 会得到 True。
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on"}
    return False


def _sender_name(item: Any) -> str:
    """优先群名片，其次昵称，最后回落到 QQ 号。"""
    sender = getattr(item, "sender", None)
    name = getattr(sender, "card", None) or getattr(sender, "nickname", None)
    if name:
        return str(name)
    user_id = getattr(item, "user_id", None)
    return f"QQ:{user_id}" if user_id else "未知用户"


class ChatHistorySkill(SkillModule):
    """历史消息 Skill — 读取更早的聊天记录。"""

    @property
    def name(self) -> str:
        return "chat_history"

    @property
    def description(self) -> str:
        return "历史消息：读取更早的聊天记录以获取上下文"

    @property
    def instructions(self) -> str:
        return (
            "历史消息 Skill 提供以下能力：\n\n"
            "  read_earlier_messages — 读取更早的聊天记录。"
            "自动记忆触发时，如果近期消息含义不明确，使用它拉取更多上下文后再决定是否写入记忆。"
        )

    def __init__(self, adapter: Any = None) -> None:
        self._adapter = adapter

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._adapter is None:
            return []
        return [
            self._tool_def(
                "read_earlier_messages",
                "读取更早的聊天记录（返回按时间排序的可读文本数组，不是原始 JSON）。"
                "message_seq=0 表示从最新一条往前取；count 默认 20、最大 50；"
                "总输出超过上限时会截断并置 truncated=true。",
                {
                    "properties": {
                        "conversation_kind": {
                            "type": "string",
                            "enum": ["group", "private"],
                            "description": "会话类型",
                        },
                        "conversation_id": {"type": "string", "description": "群号或好友QQ号"},
                        "message_seq": {
                            "type": "integer",
                            "description": "可选，历史起点 message_seq；0（默认）表示从最新一条往前取",
                            "default": 0,
                        },
                        "count": {
                            "type": "integer",
                            "description": "读取条数，默认20，最大50（越界会被钳制）",
                            "default": 20,
                        },
                        "reverse_order": {"type": "boolean", "description": "是否反向排序"},
                    },
                    "required": ["conversation_kind", "conversation_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown chat_history tool: {tool_name}"})
        return await handler(self, args)


# ── Handlers ──


async def _handle_read_earlier_messages(self: ChatHistorySkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    try:
        conv_kind = str(args.get("conversation_kind") or "").strip().casefold()
        if conv_kind not in {"group", "private"}:
            return _json({
                "ok": False,
                "error": f"conversation_kind 必须是 group 或 private，收到 {conv_kind!r}",
            })
        raw_id = str(args.get("conversation_id") or "").strip()
        if not raw_id.isdigit():
            return _json({"ok": False, "error": "conversation_id 必须是数字（群号或好友QQ号）"})
        conv_id = int(raw_id)
        count = _coerce_int(args.get("count"), _DEFAULT_COUNT, low=_MIN_COUNT, high=_MAX_COUNT)
        message_seq = _coerce_int(args.get("message_seq"), 0, low=0)
        reverse_order = _coerce_bool(args.get("reverse_order", False))

        if conv_kind == "private":
            response = await self._adapter.get_friend_msg_history(
                conv_id, message_seq=message_seq, count=count, reverse_order=reverse_order,
            )
        else:
            response = await self._adapter.get_group_msg_history(
                conv_id, message_seq=message_seq, count=count, reverse_order=reverse_order,
            )

        # 真实数据在 data.messages；API 失败时 safe_parse_model 会给出 data=None。
        payload = getattr(response, "data", None)
        items = list(getattr(payload, "messages", None) or [])
        if not items:
            detail = str(getattr(response, "wording", "") or getattr(response, "message", "") or "")
            return _json({
                "ok": False,
                "error": detail or "未取到历史消息（可能已到最早一条，或该会话不可读）",
            })

        # 昵称在本批数据里就能拿到, 不需要逐条调用 get_stranger_info。
        names = {
            getattr(item, "user_id", None): _sender_name(item) for item in items
        }

        async def _lookup(user_id: int) -> Any:
            name = names.get(user_id) or f"QQ:{user_id}"
            return SimpleNamespace(data=SimpleNamespace(nickname=name))

        rendered: list[str] = []
        budget = _MAX_OUTPUT_CHARS
        for item in items:
            text = await history_message_to_text(item, _lookup)
            if len(text) > _MAX_ITEM_CHARS:
                text = text[:_MAX_ITEM_CHARS] + "…"
            if rendered and budget - len(text) <= 0:
                break
            rendered.append(text)
            budget -= len(text)

        return _json({
            "ok": True,
            "count": len(rendered),
            "truncated": len(rendered) < len(items),
            "messages": rendered,
        })
    except Exception as e:
        return _json({"ok": False, "error": f"{type(e).__name__}: {e}"})


_HANDLERS = {
    "read_earlier_messages": _handle_read_earlier_messages,
}

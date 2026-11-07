"""直播回复可按需调用的工具：看画面 / 听语音 / 读历史。

与 send_reply/cancel 不同，这些工具不会结束本轮；它们只是把直播间的能力按需
放进上下文，模型想看画面就自己看，而不是每轮回都预注入。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.bilibili.live_parts.helpers import _to_int

#: 工具结果进上下文前的截断长度：画面描述/转写都可能很长，别把一轮撑爆。
_RESULT_CHARS = 4000

_SNAPSHOT = {
    "type": "function",
    "function": {
        "name": "snapshot",
        "description": "看一眼当前直播画面（截帧并让视觉模型描述）。想聊画面里在演什么时调用。",
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}
_TRANSCRIBE = {
    "type": "function",
    "function": {
        "name": "transcribe",
        "description": "听最近一段直播语音并转成文字（默认 10 秒）。想知道主播刚才说了什么时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "minimum": 5, "maximum": 30}
            },
            "additionalProperties": False,
        },
    },
}
_READ_HISTORY = {
    "type": "function",
    "function": {
        "name": "read_history",
        "description": "读最近的弹幕历史（默认 50 条，最多 500 条）。想确认之前聊过什么时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "minimum": 1, "maximum": 500}
            },
            "additionalProperties": False,
        },
    },
}

LIVE_TOOL_DEFS: tuple[dict[str, Any], ...] = (_SNAPSHOT, _TRANSCRIBE, _READ_HISTORY)


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)[:_RESULT_CHARS]


def build_live_executors(interactor: Any, room_id: int) -> dict[str, Any]:
    """把直播间能力绑到一次回复上；模型调用哪个就执行哪个。"""

    async def snapshot(_args: dict) -> str:
        return _dump(await interactor.snapshot(_to_int(room_id)))

    async def transcribe(args: dict) -> str:
        seconds = max(5, min(30, _to_int(args.get("seconds")) or 10))
        return _dump(await interactor.transcribe(_to_int(room_id), seconds=seconds))

    async def read_history(args: dict) -> str:
        count = max(1, min(500, _to_int(args.get("count")) or 50))
        text = interactor.format_history(_to_int(room_id), count)
        return (text or "(空)")[:_RESULT_CHARS]

    return {
        "snapshot": snapshot,
        "transcribe": transcribe,
        "read_history": read_history,
    }

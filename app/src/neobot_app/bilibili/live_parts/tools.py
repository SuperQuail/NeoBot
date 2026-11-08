"""直播回复可按需调用的工具：看画面 / 听语音。

历史弹幕本来就每轮整段注入，不再提供 read_history 之类重复能力。这些工具不会
结束本轮，只是把直播间的能力按需放进上下文。
"""

from __future__ import annotations

import json
import re
from typing import Any

from neobot_app.bilibili.live_parts.helpers import _to_int

#: 单个字段进上下文前的截断长度：画面描述/转写都可能很长，别把一轮撑爆。
_RESULT_CHARS = 1200
#: 错误信息只留一句：ffmpeg 的 stderr 里可能带本地路径或带签名的拉流地址。
_ERROR_CHARS = 200
_URL_RE = re.compile(r"https?://\S+")
_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+|/(?:[\w.-]+/)+[\w.-]+")

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

LIVE_TOOL_DEFS: tuple[dict[str, Any], ...] = (_SNAPSHOT, _TRANSCRIBE)


def _safe_error(value: Any) -> str:
    """错误只回一句：抹掉 URL 与本地路径，避免把内部信息带进上下文。"""
    text = " ".join(str(value or "").split())
    text = _URL_RE.sub("<url>", text)
    text = _PATH_RE.sub("<path>", text)
    return text[:_ERROR_CHARS]


def build_live_executors(interactor: Any, room_id: int) -> dict[str, Any]:
    """把直播间能力绑到一次回复上；模型调用哪个就执行哪个。"""

    async def snapshot(_args: dict) -> str:
        result = await interactor.snapshot(_to_int(room_id))
        description = (
            str(result.get("description") or "").strip()
            if isinstance(result, dict)
            else ""
        )
        # 没配置视觉模型时截帧仍然成功但描述为空：这时不能报 ok，否则模型会照着猜画面。
        ok = bool(isinstance(result, dict) and result.get("ok") and description)
        return json.dumps(
            {
                "ok": ok,
                "description": description[:_RESULT_CHARS],
                "error": ""
                if ok
                else _safe_error(
                    (result or {}).get("error") if isinstance(result, dict) else ""
                )
                or "没有画面描述（未配置视觉模型或截帧失败）",
            },
            ensure_ascii=False,
        )

    async def transcribe(args: dict) -> str:
        seconds = max(5, min(30, _to_int(args.get("seconds")) or 10))
        result = await interactor.transcribe(_to_int(room_id), seconds=seconds)
        if not isinstance(result, dict):
            return json.dumps(
                {"ok": False, "error": "转写失败", "text": ""}, ensure_ascii=False
            )
        text = str(result.get("text") or "").strip()
        ok = bool(result.get("ok") and text)
        return json.dumps(
            {
                "ok": ok,
                "text": text[:_RESULT_CHARS],
                "error": ""
                if ok
                else _safe_error(result.get("error")) or "没有听到可转写的内容",
            },
            ensure_ascii=False,
        )

    return {"snapshot": snapshot, "transcribe": transcribe}

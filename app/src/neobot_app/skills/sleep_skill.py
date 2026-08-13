"""SleepSkill — 让 Bot 自己开始睡觉 / 提前醒来 / 查看睡眠状态。

睡眠期间群聊消息正常接收并入队,但不触发自动回复;被@时会被叫醒并带
刚睡醒的状态回复;私聊不受睡眠影响。没有别人要求时尽量不要去睡觉。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.runtime.sleep_service import parse_sleep_duration
from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class SleepSkill(SkillModule):
    """睡眠管理 Skill — Bot 可以自己开始睡觉/醒来/查看睡眠状态。"""

    @property
    def name(self) -> str:
        return "sleep"

    @property
    def description(self) -> str:
        return "睡眠管理:让 Bot 自己开始睡觉/提前醒来/查看睡眠状态"

    @property
    def instructions(self) -> str:
        return """## 睡眠 Skill
提供让 Bot 自己开始睡觉、提前醒来、查看睡眠状态的能力:
  sleep__go_to_sleep — 开始睡眠,参数 duration(如 "2h" / "90m" / "3600s",裸数字按分钟,最多 12 小时)
  sleep__wake_up — 立即醒来
  sleep__get_sleep_status — 查看当前睡眠状态与剩余时间

## 使用原则
- 没有别人要求你睡觉的时候,尽量不要去睡觉
- 睡眠期间:群聊消息正常接收并入队,但不会自动回复;被@时会被叫醒并回复(带刚睡醒的状态)
- 私聊不受睡眠影响,始终正常回复
- 睡眠时间到、执行 wake_up 或被@都会结束睡眠
- 睡眠时长最多 12 小时,无冷却限制"""

    def __init__(self, sleep_service: Any = None) -> None:
        self._sleep = sleep_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "go_to_sleep",
                "让 Bot 开始睡眠。睡眠期间群聊消息只接收不回复,被@会被叫醒;"
                "私聊不受影响。没有别人要求时尽量不要使用。",
                {
                    "properties": {
                        "duration": {
                            "type": "string",
                            "description": (
                                "睡眠时长,如 \"2h\" / \"90m\" / \"3600s\","
                                "裸数字按分钟,最多 12 小时"
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "可选,睡觉的理由",
                        },
                    },
                    "required": ["duration"],
                },
            ),
            self._tool_def(
                "wake_up",
                "立即结束睡眠,恢复所有群聊的自动回复。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "get_sleep_status",
                "查看 Bot 当前是否在睡觉、剩余睡眠时间与预计醒来时间。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown sleep tool: {tool_name}"})
        return await handler(self, args)


# ── Handlers ──


async def _handle_go_to_sleep(self: SleepSkill, args: dict) -> str:
    if self._sleep is None:
        return _json({"ok": False, "error": "sleep_service 未配置"})
    duration = str(args.get("duration", "")).strip()
    seconds, error = parse_sleep_duration(duration)
    if error is not None:
        return _json({"ok": False, "error": error})
    ok, message = self._sleep.sleep(seconds)
    return _json(
        {
            "ok": ok,
            "message": message,
            "duration_seconds": int(seconds),
        }
    )


async def _handle_wake_up(self: SleepSkill, args: dict) -> str:
    if self._sleep is None:
        return _json({"ok": False, "error": "sleep_service 未配置"})
    was_sleeping = self._sleep.wake()
    return _json({"ok": True, "was_sleeping": was_sleeping})


async def _handle_get_sleep_status(self: SleepSkill, args: dict) -> str:
    if self._sleep is None:
        return _json({"ok": True, "sleeping": False, "note": "sleep_service 未配置"})
    return _json(
        {
            "ok": True,
            "sleeping": self._sleep.is_sleeping(),
            "remaining_seconds": self._sleep.remaining_seconds(),
            "wake_up_at_text": self._sleep.wake_up_time_text(),
        }
    )


_HANDLERS = {
    "go_to_sleep": _handle_go_to_sleep,
    "wake_up": _handle_wake_up,
    "get_sleep_status": _handle_get_sleep_status,
}

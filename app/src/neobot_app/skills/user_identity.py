"""UserIdentitySkill — 官方合成用户 ID 与真实 QQ 号的人工映射。

官方通道只给 openid，NeoBot 内部映射成 13 位合成 ID，和真实 QQ 号没有 API
可以互转。Agent 在提示词里看到 `ID:9000…` 且能从对话判断其真实 QQ 号时，
用这里的工具写入同一份映射文件；管理员命令 /linkqq 也写这份文件。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule
from neobot_app.user_identity import link_user_qq, qq_for_user, unlink_user_qq


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class UserIdentitySkill(SkillModule):
    """把通道本地用户 ID 映射到真实 QQ 号。"""

    @property
    def name(self) -> str:
        return "user_identity"

    @property
    def description(self) -> str:
        return "官方合成用户 ID 与真实 QQ 号的人工映射（提示词显示、管理员识别共用）"

    @property
    def instructions(self) -> str:
        return (
            "官方通道的用户 ID 是开放平台合成 ID（提示词里显示为 ID:9000…），不是真实 QQ 号。\n"
            "如果你从对话中确认了某位官方用户的真实 QQ 号，用 link_user_qq 建立映射：\n"
            "  - user_id：提示词/消息里的用户 ID（ID: 后面那串数字）；\n"
            "  - qq_number：真实 QQ 号（5~11 位纯数字）。\n"
            "映射后该用户会显示为 QQ:<真实号>，管理员列表与权限也会按真实 QQ 号识别。\n"
            "不要猜测或编造 QQ 号；不确定时用 get_user_qq 查询是否已有映射。"
        )

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "link_user_qq",
                "把某个用户 ID 与真实 QQ 号映射（官方合成 ID → QQ 号）。仅在能确认二者属于同一个人时调用。",
                {
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "用户 ID（提示词里的 ID:9000… 那串数字，或普通 QQ 号）",
                        },
                        "qq_number": {
                            "type": "string",
                            "description": "真实 QQ 号，5~11 位纯数字",
                        },
                        "channel": {
                            "type": "string",
                            "enum": ["auto", "onebot", "official"],
                            "description": "可选，用户 ID 所属通道；auto 按 ID 位数推断（13 位合成 ID 视为官方）",
                        },
                    },
                    "required": ["user_id", "qq_number"],
                },
            ),
            self._tool_def(
                "get_user_qq",
                "查询某个用户 ID 当前映射到的真实 QQ 号；没有映射时返回 null。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "要查询的用户 ID"},
                    },
                    "required": ["user_id"],
                },
            ),
            self._tool_def(
                "unlink_user_qq",
                "移除某个用户 ID 的 QQ 号映射（发现映射错误时使用）。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "要移除映射的用户 ID"},
                    },
                    "required": ["user_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        user_id = str(args.get("user_id", "")).strip()
        if not user_id:
            return _json({"ok": False, "error": "缺少 user_id"})

        if tool_name == "link_user_qq":
            raw_channel = str(args.get("channel") or "auto").strip().lower()
            if raw_channel not in ("auto", "onebot", "official"):
                return _json({"ok": False, "error": "channel 必须为 auto/onebot/official"})
            channel = None if raw_channel == "auto" else raw_channel
            ok, message = link_user_qq(user_id, args.get("qq_number"), channel=channel)
            return _json({"ok": ok, "message": message})

        if tool_name == "get_user_qq":
            qq = qq_for_user(user_id)
            return _json({"ok": True, "user_id": user_id, "qq_number": qq})

        if tool_name == "unlink_user_qq":
            ok, message = unlink_user_qq(user_id)
            return _json({"ok": ok, "message": message})

        return _json({"ok": False, "error": f"未知工具: {tool_name}"})

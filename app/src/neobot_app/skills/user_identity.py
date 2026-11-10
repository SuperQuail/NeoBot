"""UserIdentitySkill — 官方合成用户 ID 与真实 QQ 号的人工映射。

官方通道只给 openid，NeoBot 内部映射成 13 位合成 ID，和真实 QQ 号没有 API
可以互转。Agent 在提示词里看到 `ID:9000…` 且能从对话判断其真实 QQ 号时，
用这里的工具写入同一份映射文件；管理员命令 /linkqq 也写这份文件。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule
from neobot_app.user_identity import (
    group_number_for,
    link_group_number,
    link_user_qq,
    qq_for_user,
    unlink_group_number,
    unlink_user_qq,
)


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
            "映射后该用户会显示为 QQ:<真实号>，好友/回复名单也按真实 QQ 号识别。\n"
            "官方通道的群 ID 是 13 位合成 ID（提示词里显示为 群 ID:800…）；确认真实群号后可用\n"
            "link_group_number 建立群号映射，之后显示为 群号:<真实群号>，群黑白名单按真实群号识别。\n"
            "注意：本技能写入的用户映射只影响展示，**不会授予管理员权限**；管理员/次级管理员\n"
            "身份映射必须由人类管理员在面板/群里用 /linkqq 命令建立，agent 无权自行把用户映射成管理员。\n"
            "不要猜测或编造 QQ 号/群号；不确定时用 get_user_qq / get_group_number 查询已有映射。"
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
            self._tool_def(
                "link_group_number",
                "把官方群的合成群 ID 映射到真实 QQ 群号（官方群 ID 显示为 群 ID:800…）。",
                {
                    "properties": {
                        "group_id": {
                            "type": "string",
                            "description": "群 ID（提示词里的 群 ID:800… 那串数字，或普通群号）",
                        },
                        "group_number": {
                            "type": "string",
                            "description": "真实 QQ 群号，5~12 位纯数字",
                        },
                        "channel": {
                            "type": "string",
                            "enum": ["auto", "onebot", "official"],
                            "description": "可选，群 ID 所属通道；auto 按 ID 位数推断",
                        },
                    },
                    "required": ["group_id", "group_number"],
                },
            ),
            self._tool_def(
                "get_group_number",
                "查询某个群 ID 当前映射到的真实 QQ 群号；没有映射时返回 null。",
                {
                    "properties": {
                        "group_id": {"type": "string", "description": "要查询的群 ID"},
                    },
                    "required": ["group_id"],
                },
            ),
            self._tool_def(
                "unlink_group_number",
                "移除某个群 ID 的群号映射（发现映射错误时使用）。",
                {
                    "properties": {
                        "group_id": {"type": "string", "description": "要移除映射的群 ID"},
                    },
                    "required": ["group_id"],
                },
            ),
        ]

    @staticmethod
    def _channel(args: dict[str, Any]) -> tuple[str | None, str | None]:
        raw = str(args.get("channel") or "auto").strip().lower()
        if raw not in ("auto", "onebot", "official"):
            return None, "channel 必须为 auto/onebot/official"
        return (None if raw == "auto" else raw), None

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name in ("link_user_qq", "get_user_qq", "unlink_user_qq"):
            user_id = str(args.get("user_id", "")).strip()
            if not user_id:
                return _json({"ok": False, "error": "缺少 user_id"})
            if tool_name == "get_user_qq":
                return _json({"ok": True, "user_id": user_id, "qq_number": qq_for_user(user_id)})
            if tool_name == "unlink_user_qq":
                ok, message = unlink_user_qq(user_id)
                return _json({"ok": ok, "message": message})
            channel, error = self._channel(args)
            if error:
                return _json({"ok": False, "error": error})
            # agent 写入的映射只用于展示，不授予管理员权限（管理员映射必须用 /linkqq 命令）
            ok, message = link_user_qq(
                user_id, args.get("qq_number"), channel=channel, trusted=False
            )
            return _json({"ok": ok, "message": message})

        if tool_name in ("link_group_number", "get_group_number", "unlink_group_number"):
            group_id = str(args.get("group_id", "")).strip()
            if not group_id:
                return _json({"ok": False, "error": "缺少 group_id"})
            if tool_name == "get_group_number":
                return _json(
                    {"ok": True, "group_id": group_id, "group_number": group_number_for(group_id)}
                )
            if tool_name == "unlink_group_number":
                ok, message = unlink_group_number(group_id)
                return _json({"ok": ok, "message": message})
            channel, error = self._channel(args)
            if error:
                return _json({"ok": False, "error": error})
            ok, message = link_group_number(
                group_id, args.get("group_number"), channel=channel, trusted=False
            )
            return _json({"ok": ok, "message": message})

        return _json({"ok": False, "error": f"未知工具: {tool_name}"})

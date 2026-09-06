"""CredentialSkill — 风险操作凭据申请/查询。

申请流程:
1. bot 调用 credential__request(action, credential_type, duration_minutes)
2. 生成凭据文本,在聊天中请求管理员发送该文本
3. 管理员发送后凭据签发,风险操作(kick/quit_group 等)方可执行
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.credentials.model import (
    CRED_TYPE_ONE_TIME,
)
from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


# 仅群聊会话可用的动作(私聊申请这些动作没有意义,凭据无法在群内使用)
_GROUP_ONLY_ACTIONS = frozenset({"kick", "quit_group"})


class CredentialSkill(SkillModule):
    """凭据 Skill — 申请/查看风险操作凭据。"""

    def __init__(self, credential_manager: Any = None) -> None:
        self._credential_manager = credential_manager

    @property
    def name(self) -> str:
        return "credential"

    @property
    def description(self) -> str:
        return "风险操作凭据：申请凭据（一次性/时间凭据），供踢人/退群/全局回复意愿等管理操作使用"

    @property
    def instructions(self) -> str:
        return (
            "凭据 Skill 提供以下能力：\n\n"
            "  credential__request — 申请风险操作凭据\n"
            "  credential__check — 查看当前会话的凭据状态\n\n"
            "【申请流程（重要）】\n"
            "  1. 执行踢人/退群/全局回复意愿等需要凭据的操作前，先调用 credential__request 申请凭据\n"
            "  2. 把返回的 code 文本告诉用户：『我需要凭据来做{action}，发送 {code} 让我获得凭据』\n"
            "  3. 管理员在群内发送该文本后，凭据自动签发（必须单独发送该文本，不要夹带其他文字）\n"
            "  4. 签发后再次执行原操作即可（凭据校验通过）\n"
            "  5. 凭据与当前会话绑定：在哪个会话申请，就必须在哪个会话发送确认；"
            "踢人/退群等群动作必须在目标群内申请（私聊申请无法使用）\n\n"
            "【凭据类型】\n"
            "  - one_time：一次性凭据，使用一次后失效\n"
            "  - timed：时间凭据，签发后持续有效（默认 5 分钟，最长 30 分钟）\n\n"
            "【当前需要凭据的操作】\n"
            "  - kick：踢人（需超级管理员签发）\n"
            "  - quit_group：退群（需超级管理员签发）\n"
            "  - willing_global：设置全局回复意愿（运行时，影响所有群聊；私聊固定百分百"
            "不受影响；需次级管理员签发；临时调整一次用 one_time，反复调整可申请 timed）\n"
            "  - willing_config：查看/编辑 config 中的全局回复意愿系数（持久化+热重载；"
            "需超级管理员签发）\n"
            "  - agent_execute：Python/命令/持久终端执行（宿主进程权限，需超级管理员）\n"
            "  - agent_shared_write：修改共享持久目录（需超级管理员）\n"
            "  - agent_plan：批准计划进入执行（需超级管理员）\n"
            "  - agent_goal：创建或恢复多轮目标（需超级管理员）\n"
            "  - agent_ralph：启动有预算的独立尝试循环（需超级管理员）"
        )

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._credential_manager is None:
            return []
        return [
            self._tool_def(
                "request",
                "申请风险操作凭据。生成凭据文本,需由管理员在聊天中发送该文本后才生效。"
                "返回凭据文本后,请向用户说明:『我需要凭据来做{action},发送 {code} 让我获得凭据』",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "凭据用途,如 kick(踢人)、quit_group(退群)",
                        },
                        "credential_type": {
                            "type": "string",
                            "enum": ["one_time", "timed"],
                            "default": "one_time",
                            "description": "凭据类型:one_time=一次性;timed=时间凭据(持续有效一段时间)",
                        },
                        "duration_minutes": {
                            "type": "integer",
                            "description": "可选,time 凭据有效时长(分钟),默认 5,最长 30;one_time 忽略",
                        },
                    },
                    "required": ["action"],
                },
            ),
            self._tool_def(
                "check",
                "查看当前会话的凭据状态(待确认/已签发/已使用)。",
                {
                    "properties": {},
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "request":
            return await self._handle_request(args)
        if tool_name == "check":
            return await self._handle_check(args)
        return _json({"ok": False, "error": f"unknown credential tool: {tool_name}"})

    async def _handle_request(self, args: dict[str, Any]) -> str:
        if self._credential_manager is None:
            return _json({"ok": False, "error": "credential_manager 未配置"})
        action = str(args.get("action") or "").strip()
        if not action:
            return _json({"ok": False, "error": "缺少 action 参数"})
        pipeline_key = str(args.get("pipeline_key") or "")
        if ":" not in pipeline_key:
            return _json({"ok": False, "error": "无法确定当前会话(缺少 pipeline_key)"})
        # 群动作必须绑定群会话(私聊申请无法在群内使用)
        if action in _GROUP_ONLY_ACTIONS and not pipeline_key.startswith("group:"):
            return _json({
                "ok": False,
                "error": (
                    f"动作 {action} 需要群内凭据:请在目标群内申请,"
                    "由管理员在群内发送凭据文本后使用。"
                ),
            })
        chat_flow = pipeline_key
        cred_type = str(args.get("credential_type") or CRED_TYPE_ONE_TIME)
        duration = args.get("duration_minutes")
        requester_id = int(args.get("_requester_id") or 0)
        try:
            credential = self._credential_manager.create(
                chat_flow=chat_flow,
                action=action,
                requester_id=requester_id,
                cred_type=cred_type,
                duration_minutes=duration,
            )
        except ValueError as exc:
            return _json({"ok": False, "error": str(exc)})
        return _json({
            "ok": True,
            "code": credential.code,
            "action": credential.action,
            "credential_type": credential.cred_type,
            "duration_minutes": credential.duration_minutes,
            "status": credential.status,
            "message": (
                f"凭据已生成。请在聊天中说明:『我需要凭据来做{credential.action},"
                f"发送 {credential.code} 让我获得凭据』。"
                f"管理员发送该文本后凭据生效,届时再执行原操作。"
            ),
        })

    async def _handle_check(self, args: dict[str, Any]) -> str:
        if self._credential_manager is None:
            return _json({"ok": False, "error": "credential_manager 未配置"})
        pipeline_key = str(args.get("pipeline_key") or "")
        if ":" not in pipeline_key:
            return _json({"ok": False, "error": "无法确定当前会话(缺少 pipeline_key)"})
        credentials = self._credential_manager.list(chat_flow=pipeline_key)
        return _json({
            "ok": True,
            "items": [credential.as_dict() for credential in credentials],
        })

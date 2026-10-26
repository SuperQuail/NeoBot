"""回复意愿配置工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import inspect

from neobot_app.agent_tools.review import review_action
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def


class _WillingnessToolsMixin:
    async def _execute_adjust_willingness(self, args: dict) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        action = str(args.get("action") or "")
        if action == "set_global":
            return await self._execute_set_global_willing(args)
        current_conv_id = str(self._conv_id or "").strip()
        requested_conv_id = str(args.get("conv_id") or current_conv_id).strip()
        if action in {
            "set_conversation",
            "remove_conversation",
            "add_blacklist",
            "remove_blacklist",
        }:
            if not current_conv_id:
                return "错误：无法确定当前会话 ID"
            if requested_conv_id != current_conv_id:
                return "错误：只能调整当前会话的回复意愿"
        if action == "set_conversation":
            value = args.get("value")
            if value is None:
                return "错误：set_conversation 需要提供 value 参数"
            return self._willing.set_runtime_conversation_coefficient(
                current_conv_id, float(value)
            )
        if action == "remove_conversation":
            return self._willing.remove_runtime_conversation_coefficient(
                current_conv_id
            )
        if action == "add_blacklist":
            return self._willing.add_runtime_blacklist(current_conv_id)
        if action == "remove_blacklist":
            return self._willing.remove_runtime_blacklist(current_conv_id)
        return f"错误：未知操作 {action}"

    async def _execute_set_global_willing(self, args: dict) -> str:
        """设置全局回复意愿系数(运行时):需 willing_global 凭据。

        凭据类型由 agent 在凭据 skill 申请时决定:临时调整用 one_time,
        需要反复调整可申请 timed(签发后持续有效)。
        """
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        value = args.get("value")
        if value is None:
            return "错误：set_global 需要提供 value 参数"
        try:
            coefficient = float(value)
        except (TypeError, ValueError):
            return "错误：value 必须是数字"
        if not 0.0 <= coefficient <= 1.0:
            return "错误：value 必须在 0.0 到 1.0 之间"
        chat_flow = self._credential_chat_flow()
        if chat_flow is None:
            return "错误：无法确定当前会话"
        missing = await self._credential_missing_message(
            chat_flow, "willing_global", "全局回复意愿"
        )
        if missing is not None:
            return missing
        return self._willing.set_runtime_global_coefficient(coefficient)

    async def _execute_manage_willing_config(self, args: dict) -> str:
        """查看/编辑 config 中的全局回复意愿系数(持久化+热重载):需超级管理员凭据。"""
        action = str(args.get("action") or "")
        chat_flow = self._credential_chat_flow()
        if chat_flow is None:
            return "错误：无法确定当前会话"
        missing = await self._credential_missing_message(
            chat_flow, "willing_config", "修改全局回复意愿配置"
        )
        if missing is not None:
            return missing

        if self._config is None:
            return "错误：配置未注入,无法读取全局回复意愿系数"
        chat = getattr(self._config, "chat", None)
        if chat is None:
            return "错误：配置缺少 chat 段"
        reply_mode = str(getattr(chat, "reply_mode", "agent") or "agent")
        agent_coeff = getattr(chat, "willing_agent_global_coefficient", 1.0)
        common_coeff = getattr(chat, "willing_global_coefficient", 1.0)

        if action == "get":
            effective = "agent" if reply_mode == "agent" else "common"
            return (
                "当前全局回复意愿系数配置:\n"
                f"- 回复模式: {reply_mode}(生效项: {effective})\n"
                f"- agent 模式系数(willing_agent_global_coefficient): {agent_coeff}\n"
                f"- common 模式系数(willing_global_coefficient): {common_coeff}"
            )
        if action != "set":
            return f"错误：未知操作 {action}(可选值: get / set)"

        target = str(args.get("target") or reply_mode or "agent").strip().casefold()
        if target not in ("agent", "common"):
            return "错误：target 必须是 agent 或 common"
        value = args.get("value")
        if value is None:
            return "错误：set 需要提供 value 参数"
        try:
            coefficient = float(value)
        except (TypeError, ValueError):
            return "错误：value 必须是数字"
        if not 0.0 <= coefficient <= 1.0:
            return "错误：value 必须在 0.0 到 1.0 之间"
        key = (
            "willing_agent_global_coefficient"
            if target == "agent"
            else "willing_global_coefficient"
        )
        callback = self._config_update_callback
        if callback is None:
            return "错误：配置更新能力未注入"
        try:
            result = callback(key, coefficient)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            return f"错误：配置更新失败: {exc}"
        if isinstance(result, str) and result.startswith("错误"):
            return result
        return (
            f"已更新全局回复意愿系数: chat.{key} = {coefficient:.3f}"
            "(已写回 config.toml 并热重载,立即生效;重启不丢失)"
        )

    def _credential_chat_flow(self) -> str | None:
        conv_kind = str(self._conv_kind or "").strip()
        conv_id = str(self._conv_id or "").strip()
        if not conv_kind or not conv_id:
            return None
        return f"{conv_kind}:{conv_id}"

    async def _credential_missing_message(
        self, chat_flow: str, action: str, purpose: str
    ) -> str | None:
        """检查并消费凭据;无可用凭据时返回引导文案,否则返回 None。"""
        if self._credential_manager is None:
            return (
                f"错误：凭据服务未配置,无法执行{purpose}。"
                "请联系管理员检查配置"
            )
        credential = self._credential_manager.consume(
            chat_flow=chat_flow, action=action, commit=True
        )
        if credential is not None:
            return None
        if self._auto_review and self._reviewer is not None:
            allowed, reason, code = await review_action(
                self._reviewer,
                action=action,
                tool_name="manage_willing",
                params={"purpose": purpose, "chat_flow": chat_flow},
                timeout=self._review_timeout,
                domain="QQ bot reply willingness",
            )
            if allowed:
                return None
            if code == "AUTO_REVIEW_UNAVAILABLE":
                return f"错误：自动审查不可用（{reason}），请先申请管理员凭据后再试。"
            return (
                f"错误：{purpose}被自动审查拒绝：{reason}。"
                f"若认为审查器误判，可调用 credential__request 申请管理员凭据覆盖。"
            )
        return (
            f"需要管理员凭据才能执行{purpose}。\n"
            f"请调用凭据 skill 的 request 工具申请凭据: action={action}\n"
            "- 临时调整一次: credential_type=one_time(默认)\n"
            "- 需要反复调整: credential_type=timed(签发后持续有效,可多次使用)\n"
            "管理员在聊天中发送凭据文本后,凭据即生效,届时再执行原操作。"
        )

    def _execute_get_willingness_config(self) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        return self._willing.get_runtime_config_summary()

    def _define_willingness_tools(self, tools: list[ToolDefinition]) -> None:
        if self._willing is not None:
            tools.extend(
                [
                    _tool_def(
                        "adjust_reply_willingness",
                        "调整运行时回复意愿设置。\n"
                        "- set_conversation 等动作仅允许作用于当前会话\n"
                        "- set_global 设置全局回复意愿系数(影响所有群聊;私聊固定百分百"
                        "不受影响),需要管理员凭据:先调用凭据 skill 的 request 工具申请"
                        "凭据(action=willing_global,临时调整用 one_time,需要反复调整"
                        "可申请 timed),管理员在聊天中发送凭据文本后重试",
                        {
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "set_global",
                                        "set_conversation",
                                        "remove_conversation",
                                        "add_blacklist",
                                        "remove_blacklist",
                                    ],
                                    "description": "调整动作。set_global 为全局(需凭据);"
                                    "其余仅允许作用于当前会话。",
                                },
                                "conv_id": {
                                    "type": "string",
                                    "description": "可选，会话 ID；不填时使用当前会话。若提供，必须等于当前会话 ID。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "数值系数（set_global / set_conversation 必填）。",
                                },
                            },
                            "required": ["action"],
                        },
                    ),
                    _tool_def(
                        "get_willingness_config",
                        "查看当前运行时回复意愿设置。",
                        {"properties": {}, "required": []},
                    ),
                    _tool_def(
                        "manage_willing_config",
                        "查看/编辑 config.toml 中的全局回复意愿系数(agent 模式生效项为 "
                        "willing_agent_global_coefficient,common 模式为 "
                        "willing_global_coefficient)。编辑后写回配置文件并热重载,立即生效"
                        "并持久化(重启不丢失)。需要超级管理员凭据:先调用凭据 skill 的 "
                        "request 工具申请凭据(action=willing_config),管理员签发后重试。",
                        {
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["get", "set"],
                                    "description": "get=查看当前配置值;set=修改(需 value)",
                                },
                                "target": {
                                    "type": "string",
                                    "enum": ["agent", "common"],
                                    "description": "可选，编辑哪个模式下的系数；"
                                    "默认使用当前回复模式对应的系数。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "set 时必填，新的系数值（0.0-1.0）。",
                                },
                            },
                            "required": ["action"],
                        },
                    ),
                ]
            )

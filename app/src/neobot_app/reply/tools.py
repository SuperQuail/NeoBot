"""Reply-related tools exposed to the main reply agent."""

from __future__ import annotations

from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolAccessPolicy, ToolAccessRule, ToolDefinition, ToolGuardContext
from neobot_chat.tools import AgentRegistry
from neobot_chat.tools.toolset import ToolSpec, Toolset


def _default_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _tool_def(name: str, description: str, parameters: dict) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


class ReplyToolExecutor(ToolExecutor):
    """Executor for reply-mode tools."""

    def __init__(
        self,
        *,
        send_reply_handler: Any = None,
        willing_service: Any = None,
        numbering: Any = None,
        send_emoji_handler: Any = None,
        emoji_service: Any = None,
        agent_registry: AgentRegistry | None = None,
    ) -> None:
        self._send_reply = send_reply_handler
        self._willing = willing_service
        self._numbering = numbering
        self._send_emoji = send_emoji_handler
        self._emoji = emoji_service
        self._agent_registry = agent_registry

    def definitions(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = [
            _tool_def(
                "send_reply",
                "向当前会话发送回复。调用后本轮回复视为完成。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "回复内容，尽量自然简洁。",
                        },
                        "reply_to": {
                            "type": "integer",
                            "description": "可选，要回复的消息编号。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        ]
        if self._willing is not None:
            tools.extend(
                [
                    _tool_def(
                        "adjust_reply_willingness",
                        "调整运行时回复意愿设置。",
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
                                    "description": "调整动作。",
                                },
                                "conv_id": {
                                    "type": "string",
                                    "description": "会话级操作对应的会话 ID。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "数值系数。",
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
                ]
            )
        if self._send_emoji is not None or self._emoji is not None:
            tools.append(
                _tool_def(
                    "send_emoji",
                    "向当前会话发送一个表情包图片。",
                    {
                        "properties": {
                            "number": {
                                "type": "integer",
                                "description": "提示词列表中的表情包编号。",
                            },
                            "text": {
                                "type": "string",
                                "description": "可选，随表情包一起发送的文字。",
                            },
                        },
                        "required": ["number"],
                    },
                )
            )
        if self._agent_registry:
            tools.extend(
                [
                    _tool_def(
                        "list_agents",
                        "列出可用的子代理，或查看某个子代理的简介。",
                        {
                            "properties": {
                                "agent": {
                                    "type": "string",
                                    "enum": self._agent_registry.names,
                                    "description": "可选，子代理名称。",
                                },
                            },
                            "required": [],
                        },
                    ),
                    _tool_def(
                        "delegate",
                        "把任务委托给子代理。涉及档案记忆操作时应使用这个工具。",
                        {
                            "properties": {
                                "agent": {
                                    "type": "string",
                                    "enum": self._agent_registry.names,
                                    "description": "子代理名称。",
                                },
                                "task": {
                                    "type": "string",
                                    "description": "传给子代理的自然语言任务或结构化任务。",
                                },
                                "tasks": {
                                    "type": "array",
                                    "description": "可选，批量委托任务列表。",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "agent": {
                                                "type": "string",
                                                "enum": self._agent_registry.names,
                                            },
                                            "task": {"type": "string"},
                                        },
                                        "required": ["agent", "task"],
                                    },
                                },
                            },
                            "required": [],
                        },
                    ),
                ]
            )
        return tools

    async def execute(self, name: str, args: dict) -> str:
        if name == "send_reply":
            return await self._execute_send_reply(args)
        if name == "adjust_reply_willingness":
            return self._execute_adjust_willingness(args)
        if name == "get_willingness_config":
            return self._execute_get_willingness_config()
        if name == "send_emoji":
            return await self._execute_send_emoji(args)
        if name == "list_agents":
            return self._execute_list_agents(args)
        if name == "delegate":
            return await self._execute_delegate(args)
        raise ToolError(f"Unknown reply tool: {name}")

    async def _execute_send_reply(self, args: dict) -> str:
        if self._send_reply is None:
            return "错误：send_reply 处理器未配置"
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return f"错误：reply_to 必须为整数，收到 {reply_to}"
        await self._send_reply(text=text, reply_to=reply_to)
        return "回复已发送"

    def _execute_adjust_willingness(self, args: dict) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        action = str(args.get("action") or "")
        if action == "set_global":
            value = args.get("value")
            if value is None:
                return "错误：set_global 需要提供 value 参数"
            return self._willing.set_runtime_global_coefficient(float(value))
        if action == "set_conversation":
            conv_id = str(args.get("conv_id") or "")
            value = args.get("value")
            if not conv_id:
                return "错误：set_conversation 需要提供 conv_id 参数"
            if value is None:
                return "错误：set_conversation 需要提供 value 参数"
            return self._willing.set_runtime_conversation_coefficient(conv_id, float(value))
        if action == "remove_conversation":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：remove_conversation 需要提供 conv_id 参数"
            return self._willing.remove_runtime_conversation_coefficient(conv_id)
        if action == "add_blacklist":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：add_blacklist 需要提供 conv_id 参数"
            return self._willing.add_runtime_blacklist(conv_id)
        if action == "remove_blacklist":
            conv_id = str(args.get("conv_id") or "")
            if not conv_id:
                return "错误：remove_blacklist 需要提供 conv_id 参数"
            return self._willing.remove_runtime_blacklist(conv_id)
        return f"错误：未知操作 {action}"

    def _execute_get_willingness_config(self) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        return self._willing.get_runtime_config_summary()

    async def _execute_send_emoji(self, args: dict) -> str:
        handler = self._send_emoji
        if handler is None:
            return "错误：send_emoji 处理器未配置"
        try:
            number = int(args.get("number", -1))
        except (ValueError, TypeError):
            return "错误：number 必须为整数"
        if self._emoji is not None:
            entry = self._emoji.get_entry(number)
            if entry is None:
                total = self._emoji.emoji_count
                return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"
        text = str(args.get("text") or "")
        await handler(number=number, text=text)
        return f"表情包 #{number} 已发送"

    def _execute_list_agents(self, args: dict) -> str:
        if self._agent_registry is None:
            return "No agents available"
        agent = args.get("agent")
        if agent is None:
            return self._agent_registry.list_agents()
        return self._agent_registry.list_agents(str(agent))

    async def _execute_delegate(self, args: dict) -> str:
        if self._agent_registry is None:
            return "No agents available"
        agent = args.get("agent")
        task = args.get("task")
        tasks = args.get("tasks")
        normalized_tasks = tasks if isinstance(tasks, list) else None
        return await self._agent_registry.delegate(
            agent=str(agent) if agent is not None else None,
            task=str(task) if task is not None else None,
            tasks=normalized_tasks,
        )

    async def close(self) -> None:
        return None


def build_reply_toolset(
    *,
    send_reply_handler: Any = None,
    willing_service: Any = None,
    numbering: Any = None,
    send_emoji_handler: Any = None,
    emoji_service: Any = None,
    agent_registry: AgentRegistry | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = ReplyToolExecutor(
        send_reply_handler=send_reply_handler,
        willing_service=willing_service,
        numbering=numbering,
        send_emoji_handler=send_emoji_handler,
        emoji_service=emoji_service,
        agent_registry=agent_registry,
    )
    definitions = executor.definitions()
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in definitions
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())

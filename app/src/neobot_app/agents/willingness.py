"""Willingness control agent — 回复意愿控制子代理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    from neobot_app.willing.service import WillingService

EXPOSED_TO_MAIN_AGENT_NAME = "willingness"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "回复意愿控制代理。可根据当前对话情况调整Bot的回复意愿系数、会话系数或临时黑名单。"
    "所有调整仅存在于内存中，重启Bot后自动重置为默认值。"
)

_WILLINGNESS_CONTEXT: ContextVar[str] = ContextVar("willingness_context", default="")

PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片到群聊/私聊。\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注、查看聊天记录、解析用户头像。\n"
    "- image_parse: 按需求解析图片内容（不保存、不导入、不管理图库/表情包）。\n"
    "- chat_interaction: 群管理、好友管理、聊天互动操作。\n"
    "如果收到的任务明显属于其他 agent 的职责，直接告知主Agent该委托给对应的 agent，不要尝试越权处理。"
)


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


class WillingnessControlToolExecutor(ToolExecutor):
    """Tool executor for willingness control operations."""

    def __init__(
        self,
        willing_service: "WillingService",
        logger: Logger | None = None,
    ) -> None:
        self._willing = willing_service
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        return [
            _tool_def(
                "get_willingness_status",
                "查看当前运行时回复意愿设置，包括全局系数、各会话系数和临时黑名单。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "set_global_coefficient",
                "设置全局运行时回复概率系数。0.0 表示完全不想回复，1.0 表示正常回复概率。",
                {
                    "properties": {
                        "value": {
                            "type": "number",
                            "description": "全局回复概率系数，范围 0.0~1.0。0.0=完全不想回复，1.0=正常。",
                        },
                    },
                    "required": ["value"],
                },
            ),
            _tool_def(
                "set_conversation_coefficient",
                "设置指定会话的运行时回复概率系数。用于针对特定群聊或私聊调整回复概率。",
                {
                    "properties": {
                        "conv_id": {
                            "type": "string",
                            "description": "会话 ID，群聊为群号，私聊为 QQ 号。",
                        },
                        "value": {
                            "type": "number",
                            "description": "回复概率系数，范围 0.0~1.0。",
                        },
                    },
                    "required": ["conv_id", "value"],
                },
            ),
            _tool_def(
                "remove_conversation_coefficient",
                "移除指定会话的运行时回复概率系数，恢复为默认行为。",
                {
                    "properties": {
                        "conv_id": {
                            "type": "string",
                            "description": "会话 ID。",
                        },
                    },
                    "required": ["conv_id"],
                },
            ),
            _tool_def(
                "add_blacklist",
                "将指定会话加入临时黑名单，Bot 将不再回复该会话的消息。重启后自动清除。",
                {
                    "properties": {
                        "conv_id": {
                            "type": "string",
                            "description": "会话 ID。",
                        },
                    },
                    "required": ["conv_id"],
                },
            ),
            _tool_def(
                "remove_blacklist",
                "将指定会话从临时黑名单中移除，恢复 Bot 对该会话的回复。",
                {
                    "properties": {
                        "conv_id": {
                            "type": "string",
                            "description": "会话 ID。",
                        },
                    },
                    "required": ["conv_id"],
                },
            ),
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射。仅在需要了解当前对话情况时调用。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_willingness_status":
            return self._willing.get_runtime_config_summary()
        if name == "set_global_coefficient":
            value = float(args.get("value", 1.0))
            return self._willing.set_runtime_global_coefficient(value)
        if name == "set_conversation_coefficient":
            conv_id = str(args.get("conv_id", ""))
            value = float(args.get("value", 1.0))
            return self._willing.set_runtime_conversation_coefficient(conv_id, value)
        if name == "remove_conversation_coefficient":
            conv_id = str(args.get("conv_id", ""))
            return self._willing.remove_runtime_conversation_coefficient(conv_id)
        if name == "add_blacklist":
            conv_id = str(args.get("conv_id", ""))
            return self._willing.add_runtime_blacklist(conv_id)
        if name == "remove_blacklist":
            conv_id = str(args.get("conv_id", ""))
            return self._willing.remove_runtime_blacklist(conv_id)
        if name == "get_chat_context":
            ctx = _WILLINGNESS_CONTEXT.get()
            if not ctx:
                return "当前无主Agent上下文。"
            return ctx
        return f"未知工具: {name}"

    async def close(self) -> None:
        return None


def build_willingness_control_toolset(
    willing_service: "WillingService",
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = WillingnessControlToolExecutor(
        willing_service=willing_service,
        logger=logger,
    )
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


def _build_system_prompt() -> str:
    return (
        "你是回复意愿控制代理。负责根据当前对话情况调整Bot的回复意愿。\n"
        "你有以下工具可用：\n"
        "- get_willingness_status: 查看当前回复意愿设置\n"
        "- set_global_coefficient: 设置全局回复系数（0.0~1.0）\n"
        "- set_conversation_coefficient: 设置指定会话的回复系数\n"
        "- remove_conversation_coefficient: 移除指定会话的回复系数\n"
        "- add_blacklist: 将指定会话加入临时黑名单\n"
        "- remove_blacklist: 将指定会话从临时黑名单移除\n"
        "- get_chat_context: 读取主Agent的聊天上下文\n\n"
        "调整策略指引：\n"
        "1. 当Bot在某个会话中过于活跃、频繁插话、或被要求闭嘴时，降低该会话的系数或加入黑名单。\n"
        "2. 当用户明确表示希望Bot回复或积极参与时，适当提高系数。\n"
        "3. 如果Bot整体表现过于活跃或过于沉默，可调整全局系数。\n"
        "4. 所有调整仅存在于内存中，重启Bot后自动重置，无需担心永久性影响。\n"
        "5. 调整前先查看当前状态，避免无意义的重复设置。\n"
        "6. 默认全局系数为 1.0，默认会话系数为 1.0。值越小回复概率越低。\n\n"
        "注意：你修改的是运行时参数，系统配置中的默认值不会改变。\n"
        f"{PEER_AGENT_DESCRIPTIONS}\n"
        "任务完成后，只返回简短纯文本结果（说明做了什么调整即可）。"
    )


class WillingnessControlAgent:
    """LLM-backed agent dedicated to willingness control."""

    def __init__(
        self,
        provider: Provider,
        willing_service: "WillingService",
        logger: Logger | None = None,
    ) -> None:
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_willingness_control_toolset(
            willing_service=willing_service,
            logger=logger,
        )
        self.tool_definitions = self._toolset.definitions()
        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(),
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        token = _WILLINGNESS_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            return await self._agent.invoke(state)
        finally:
            _WILLINGNESS_CONTEXT.reset(token)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _WILLINGNESS_CONTEXT.set(str(state.get("_delegate_context") or ""))
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _WILLINGNESS_CONTEXT.reset(token)

    async def close(self) -> None:
        await self._agent.close()


def build_willingness_control_agent(
    provider: Provider,
    willing_service: "WillingService",
    logger: Logger | None = None,
) -> WillingnessControlAgent:
    return WillingnessControlAgent(
        provider=provider,
        willing_service=willing_service,
        logger=logger,
    )

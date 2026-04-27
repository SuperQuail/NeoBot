"""Willingness control agent — 回复意愿控制子代理。"""

from __future__ import annotations

import re
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
    "回复意愿控制。仅可调整当前会话的运行时回复意愿：设置/移除当前会话的回复系数（0.0~1.0）、"
    "管理当前会话的临时黑名单（禁言/恢复）。不允许修改全局系数或其他会话。"
    "所有调整仅存于内存，重启后重置为默认值。"
)

_WILLINGNESS_CONTEXT: ContextVar[str] = ContextVar("willingness_context", default="")
_CONV_KIND: ContextVar[str] = ContextVar("willingness_conv_kind", default="")
_CONV_ID: ContextVar[str] = ContextVar("willingness_conv_id", default="")

PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- creator: 绘图、导入聊天图片、管理图库/表情包、发送图片。\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注/聊天记录、解析用户头像、调整好感度。\n"
    "- image_parse: 仅按需求解析图片内容，不保存、不导入、不管理图库/表情包。\n"
    "- chat_interaction: 聊天互动、群管理、好友管理、发送表情包。\n"
    "如果收到的任务明显属于其他 agent 的职责，直接告知主Agent该委托给对应的 agent，不要越权处理。"
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


def _parse_conv_from_context(context: str) -> tuple[str, str]:
    """Extract (kind, id) from a [当前会话] block in the delegate context."""
    m = re.search(r"\[当前会话\]\s*\nkind=(\w+)\s*\nid=(\S+)", context)
    if m:
        return m.group(1), m.group(2)
    return "", ""


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
                "查看当前运行时回复意愿设置，包括当前会话系数、全局系数和临时黑名单。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "set_session_coefficient",
                "设置当前会话的运行时回复概率系数（0.0~1.0）。仅允许修改当前会话，不可修改其他会话。",
                {
                    "properties": {
                        "value": {
                            "type": "number",
                            "description": "回复概率系数，范围 0.0~1.0。0.0=完全不想回复，1.0=正常。",
                        },
                    },
                    "required": ["value"],
                },
            ),
            _tool_def(
                "remove_session_coefficient",
                "移除当前会话的运行时回复概率系数，恢复默认行为。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "add_session_blacklist",
                "将当前会话加入临时黑名单，Bot 将不再回复该会话的消息。重启后自动清除。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "remove_session_blacklist",
                "将当前会话从临时黑名单中移除，恢复 Bot 对该会话的回复。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射。仅在需要了解当前对话情况时调用。",
                {"properties": {}, "required": []},
            ),
        ]

    def _get_conv_id(self) -> str:
        return _CONV_ID.get()

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_willingness_status":
            return self._willing.get_runtime_config_summary()
        if name == "set_session_coefficient":
            conv_id = self._get_conv_id()
            if not conv_id:
                return "错误：无法确定当前会话 ID"
            value = float(args.get("value", 1.0))
            return self._willing.set_runtime_conversation_coefficient(conv_id, value)
        if name == "remove_session_coefficient":
            conv_id = self._get_conv_id()
            if not conv_id:
                return "错误：无法确定当前会话 ID"
            return self._willing.remove_runtime_conversation_coefficient(conv_id)
        if name == "add_session_blacklist":
            conv_id = self._get_conv_id()
            if not conv_id:
                return "错误：无法确定当前会话 ID"
            return self._willing.add_runtime_blacklist(conv_id)
        if name == "remove_session_blacklist":
            conv_id = self._get_conv_id()
            if not conv_id:
                return "错误：无法确定当前会话 ID"
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
        "你是回复意愿控制代理。"
        "只能操作当前会话（群聊或私聊）的回复意愿，不允许修改全局系数或其他会话的配置。\n"
        "先通过 get_chat_context 查看当前会话信息，确认操作目标。\n"
        "你有以下工具可用：\n"
        "- get_willingness_status: 查看当前回复意愿设置\n"
        "- set_session_coefficient: 设置当前会话的回复概率系数（0.0~1.0）\n"
        "- remove_session_coefficient: 移除当前会话的回复系数，恢复默认\n"
        "- add_session_blacklist: 将当前会话加入临时黑名单\n"
        "- remove_session_blacklist: 将当前会话从临时黑名单移除\n"
        "- get_chat_context: 读取主Agent的聊天上下文\n\n"
        "调整策略指引：\n"
        "1. 当Bot在当前会话中过于活跃、频繁插话、或被要求闭嘴时，降低系数或加入黑名单。\n"
        "2. 当用户明确表示希望Bot回复或积极参与时，适当提高系数。\n"
        "3. 所有调整仅存在于内存中，重启Bot后自动重置，无需担心永久性影响。\n"
        "4. 调整前先查看当前状态，避免无意义的重复设置。\n"
        "5. 默认会话系数为 1.0，值越小回复概率越低。\n\n"
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
        delegate_context = str(state.get("_delegate_context") or "")
        kind, conv_id = _parse_conv_from_context(delegate_context)
        tk = _CONV_KIND.set(kind)
        ti = _CONV_ID.set(conv_id)
        tw = _WILLINGNESS_CONTEXT.set(delegate_context)
        try:
            return await self._agent.invoke(state)
        finally:
            _WILLINGNESS_CONTEXT.reset(tw)
            _CONV_ID.reset(ti)
            _CONV_KIND.reset(tk)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        delegate_context = str(state.get("_delegate_context") or "")
        kind, conv_id = _parse_conv_from_context(delegate_context)
        tk = _CONV_KIND.set(kind)
        ti = _CONV_ID.set(conv_id)
        tw = _WILLINGNESS_CONTEXT.set(delegate_context)
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _WILLINGNESS_CONTEXT.reset(tw)
            _CONV_ID.reset(ti)
            _CONV_KIND.reset(tk)

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

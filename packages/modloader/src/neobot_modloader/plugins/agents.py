from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from neobot_modloader.agent import AgentRequest
from neobot_modloader.message import Message, MessageChain, MessageSegment, normalize_message_payload
from neobot_modloader.plugins.registration import AgentRegistration, validate_agent_name


class PluginAgentRegistrar:
    def __init__(
        self,
        *,
        plugin_name: str,
        registry: Any | None,
        record_registration: Any | None,
    ) -> None:
        self._plugin_name = plugin_name
        self._registry = registry
        self._record_registration = record_registration
        self._registered: dict[str, Any] = {}

    @property
    def names(self) -> list[str]:
        return list(self._registered)

    def register(self, name: str, agent: Any) -> str:
        if self._registry is None:
            raise RuntimeError("Agent registry is not available")
        local_name = validate_agent_name(name)
        self._validate_agent(agent)
        registered_name = f"{self._plugin_name}.{local_name}"
        if registered_name in self._registered:
            raise ValueError(f"插件 Agent 已注册: {registered_name}")
        registry_names = getattr(self._registry, "names", [])
        if registered_name in registry_names:
            raise ValueError(f"Agent 已注册: {registered_name}")
        self._registry.register(registered_name, agent)
        self._registered[registered_name] = agent
        if self._record_registration is not None:
            self._record_registration(registered_name, agent)
        return registered_name

    def unregister(self, registered_name: str) -> Any | None:
        agent = self._registered.pop(registered_name, None)
        unregister = getattr(self._registry, "unregister", None)
        if callable(unregister):
            removed = unregister(registered_name)
            return removed if removed is not None else agent
        return agent

    def snapshot(self) -> list[dict[str, str]]:
        return [
            {"name": name, "description": str(getattr(agent, "description", ""))}
            for name, agent in self._registered.items()
        ]

    def list_agents(self, name: str | None = None) -> str:
        if name is not None:
            registered_name = f"{self._plugin_name}.{validate_agent_name(name)}"
            agent = self._registered.get(registered_name)
            if agent is None:
                return f"Agent '{registered_name}' not found"
            return f"Agent {registered_name}: {getattr(agent, 'description', '')}"
        if not self._registered:
            return "No agents available"
        lines = [
            f"- {registered_name}: {getattr(agent, 'description', '')}"
            for registered_name, agent in self._registered.items()
        ]
        return "Available agents:\n" + "\n".join(lines)

    @staticmethod
    def _validate_agent(agent: Any) -> None:
        missing: list[str] = []
        for attr in ("description", "tool_definitions"):
            if not hasattr(agent, attr):
                missing.append(attr)
        for method in ("invoke", "stream_invoke", "close"):
            if not callable(getattr(agent, method, None)):
                missing.append(method)
        if missing:
            raise TypeError(f"Plugin agent is missing required attributes: {', '.join(missing)}")


async def bind_agents(plugin: Any, registrations: Sequence[AgentRegistration], context: Any) -> None:
    for registration in registrations:
        if registration.factory:
            # factory=True 在插件加载时构建一次，之后复用同一个 runnable target。
            target = await plugin._call_handler(registration.handler, context, {}, Message({}), {})
            agent = RunnableAgentAdapter(target, registration)
        else:
            agent = HandlerAgentAdapter(plugin, registration, context)
        context.agents.register(registration.name, agent)


class HandlerAgentAdapter:
    def __init__(self, plugin: Any, registration: AgentRegistration, context: Any) -> None:
        self._plugin = plugin
        self._registration = registration
        self._context = context
        self.description = registration.description
        self.tool_definitions = [dict(tool) for tool in (registration.tools or [])]

    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        state_dict = dict(state or {})
        messages = _state_messages(state_dict)
        request = AgentRequest(
            task=_last_user_task(messages),
            messages=messages,
            delegate_context=str(state_dict.get("_delegate_context") or ""),
            state=state_dict,
        )
        result = await self._plugin._call_agent_handler(self._registration.handler, self._context, request)
        return normalize_agent_result(result, state_dict)

    async def stream_invoke(self, state: dict[str, Any]) -> AsyncIterator[Any]:
        yield _chat_chunk(await self.invoke(state))

    async def close(self) -> None:
        return None


class RunnableAgentAdapter:
    def __init__(self, target: Any, registration: AgentRegistration) -> None:
        if not callable(getattr(target, "invoke", None)):
            raise TypeError(f"Agent factory {registration.handler.__qualname__} must return an object with invoke(state)")
        self._target = target
        self.description = _agent_description(target, registration)
        self.tool_definitions = _agent_tools(target, registration)

    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        result = self._target.invoke(state)
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, Mapping):
            raise TypeError("Agent invoke(state) must return a State mapping")
        return dict(result)

    async def stream_invoke(self, state: dict[str, Any]) -> AsyncIterator[Any]:
        stream_invoke = getattr(self._target, "stream_invoke", None)
        if callable(stream_invoke):
            async for chunk in stream_invoke(state):
                yield chunk
            return
        yield _chat_chunk(await self.invoke(state))

    async def close(self) -> None:
        close = getattr(self._target, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result


def _agent_description(target: Any, registration: AgentRegistration) -> str:
    if registration.description:
        return registration.description
    return str(getattr(target, "description", ""))


def _agent_tools(target: Any, registration: AgentRegistration) -> list[dict[str, Any]]:
    if registration.tools is not None:
        return [dict(tool) for tool in registration.tools]
    tool_definitions = getattr(target, "tool_definitions", None)
    if isinstance(tool_definitions, list):
        return [dict(tool) for tool in tool_definitions]
    toolset = getattr(target, "toolset", None)
    definitions = getattr(toolset, "definitions", None)
    if callable(definitions):
        value = definitions()
        if isinstance(value, list):
            return [dict(tool) for tool in value]
    return []


def _state_messages(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_messages = state.get("messages", [])
    if not isinstance(raw_messages, list):
        return []
    return [dict(message) for message in raw_messages if isinstance(message, Mapping)]


def _last_user_task(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return _content_text(message.get("content"))
    if messages:
        return _content_text(messages[-1].get("content"))
    return ""


def _content_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(content)


def normalize_agent_result(result: Any, state: Mapping[str, Any]) -> dict[str, Any]:
    # 插件 handler 可以返回多种友好类型；对外统一收敛成 chat State。
    if result is None:
        raise TypeError("Agent handler must return str, chat message dict, State dict, or message payload")
    if isinstance(result, str):
        return _append_assistant_content(state, result)
    if isinstance(result, MessageChain | MessageSegment):
        return _append_assistant_content(state, normalize_message_payload(result))
    if isinstance(result, Mapping):
        result_dict = dict(result)
        if "messages" in result_dict:
            return result_dict
        if _is_chat_message(result_dict):
            return _append_chat_message(state, result_dict)
        raise TypeError("Agent handler returned a dict that is neither State nor chat message")
    if isinstance(result, list):
        if all(isinstance(item, Mapping) for item in result):
            return _append_assistant_content(state, normalize_message_payload(result))
        raise TypeError("Agent handler returned an unsupported list payload")
    raise TypeError(f"Unsupported agent handler return type: {type(result).__name__}")


def _is_chat_message(value: Mapping[str, Any]) -> bool:
    return isinstance(value.get("role"), str) and "content" in value


def _append_chat_message(state: Mapping[str, Any], message: Mapping[str, Any]) -> dict[str, Any]:
    next_state = dict(state)
    messages = _state_messages(next_state)
    messages.append(dict(message))
    next_state["messages"] = messages
    return next_state


def _append_assistant_content(state: Mapping[str, Any], content: Any) -> dict[str, Any]:
    return _append_chat_message(state, {"role": "assistant", "content": content})


def _chat_chunk(state: dict[str, Any]) -> Any:
    try:
        from neobot_chat.schema.types import ChatChunk
    except Exception as exc:
        raise RuntimeError("neobot_chat is required for fallback agent streaming") from exc
    return ChatChunk(state=state)

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel

from neobot_adapter.model.response import SendMsgResponse
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_modloader.events import PluginEventBus

MessagePayload = str | list[dict[str, Any]]


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
        local_name = self._validate_name(name)
        self._validate_agent(agent)
        registered_name = self._registered_name(local_name)
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
        if self._registry is None:
            return agent
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
            local_name = self._validate_name(name)
            registered_name = self._registered_name(local_name)
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

    def _registered_name(self, local_name: str) -> str:
        return f"plugin:{self._plugin_name}:{local_name}"

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str):
            raise TypeError("Agent name must be a string")
        if not name:
            raise ValueError("Agent name cannot be empty")
        if name != name.strip():
            raise ValueError("Agent name cannot contain leading or trailing whitespace")
        if ":" in name:
            raise ValueError("Agent name cannot contain ':'")
        return name

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


class PluginContext:
    def __init__(
        self,
        *,
        plugin_name: str,
        plugin_dir: Path,
        data_dir: Path,
        config: Mapping[str, Any] | None,
        logger: Logger | None,
        adapter: Any,
        record_subscription: Any,
        agent_registry: Any | None = None,
        record_agent_registration: Any | None = None,
        record_ai_reply_block: Any | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._plugin_dir = plugin_dir
        self._data_dir = data_dir
        self._config = dict(config or {})
        self._logger = logger or NullLogger()
        self._adapter = adapter
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.agents = PluginAgentRegistrar(
            plugin_name=plugin_name,
            registry=agent_registry,
            record_registration=record_agent_registration,
        )
        self.on = PluginEventBus(
            adapter=adapter,
            logger=self._logger,
            record_subscription=record_subscription,
            record_ai_reply_block=record_ai_reply_block,
        )

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def plugin_dir(self) -> Path:
        return self._plugin_dir

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def config(self) -> Mapping[str, Any]:
        return self._config

    @property
    def logger(self) -> Logger:
        return self._logger

    async def send_private(self, user_id: int, message: MessagePayload) -> SendMsgResponse:
        return await self._adapter.send_private_msg(user_id, message)

    async def send_group(self, group_id: int, message: MessagePayload) -> SendMsgResponse:
        return await self._adapter.send_group_msg(group_id, message)

    async def send(
        self,
        conversation: ConversationRef,
        message: MessagePayload,
    ) -> SendMsgResponse:
        return await self._adapter.send(conversation, message)

    async def reply(self, event: dict[str, Any] | BaseModel, message: MessagePayload) -> SendMsgResponse:
        return await self.send(self.conversation_from_event(event), message)

    def message_text(self, event: dict[str, Any] | BaseModel) -> str:
        data = self._event_to_dict(event)
        raw_message = data.get("raw_message")
        if raw_message is not None:
            return str(raw_message)

        message = data.get("message")
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            return "".join(self._segment_text(segment) for segment in message)
        if message is None:
            return ""
        return str(message)

    def conversation_from_event(self, event: dict[str, Any] | BaseModel) -> ConversationRef:
        data = self._event_to_dict(event)
        message_type = data.get("message_type")
        if message_type == "private" and data.get("user_id") is not None:
            return ConversationRef(kind="private", id=str(data["user_id"]))
        if message_type == "group" and data.get("group_id") is not None:
            return ConversationRef(kind="group", id=str(data["group_id"]))
        if data.get("group_id") is not None:
            return ConversationRef(kind="group", id=str(data["group_id"]))
        if data.get("user_id") is not None:
            return ConversationRef(kind="private", id=str(data["user_id"]))
        raise ValueError(f"无法从事件推断会话: plugin={self.plugin_name}")

    def require_config(self, key: str) -> Any:
        if key not in self._config:
            raise KeyError(f"插件 {self.plugin_name!r} 缺少配置项 {key!r}")
        return self._config[key]

    def _event_to_dict(self, event: dict[str, Any] | BaseModel) -> dict[str, Any]:
        if isinstance(event, BaseModel):
            return event.model_dump(mode="python")
        return dict(event)

    def _segment_text(self, segment: Any) -> str:
        if isinstance(segment, BaseModel):
            segment = segment.model_dump(mode="python")
        if not isinstance(segment, Mapping):
            return str(segment)
        if segment.get("type") != "text":
            return ""
        data = segment.get("data")
        if isinstance(data, Mapping):
            return str(data.get("text", ""))
        return ""

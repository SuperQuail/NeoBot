from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel

from neobot_adapter.model.response import SendMsgResponse
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort

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
        registered_name = f"plugin:{self._plugin_name}:{local_name}"
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
            registered_name = f"plugin:{self._plugin_name}:{self._validate_name(name)}"
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
    def _validate_name(name: str) -> str:
        if not isinstance(name, str):
            raise TypeError("Agent name must be a string")
        if not name or name != name.strip() or ":" in name:
            raise ValueError("Agent name cannot be empty, padded, or contain ':'")
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


class RuntimePluginContext:
    """Internal runtime context for the new Plugin API."""

    def __init__(
        self,
        *,
        plugin_name: str,
        plugin_dir: Path,
        data_dir: Path,
        config: Mapping[str, Any] | None,
        logger: Logger | None,
        adapter: Any,
        hook_bus: Any | None = None,
        record_subscription: Any | None = None,
        agent_registry: Any | None = None,
        record_agent_registration: Any | None = None,
        plugin_registry: Any | None = None,
        output: OutputPort | None = None,
        host: Any | None = None,
        file_server: Any | None = None,
        media_sender: Any | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._plugin_dir = plugin_dir
        self._data_dir = data_dir
        self._config = dict(config or {})
        self._logger = logger or NullLogger()
        self._adapter = adapter
        self._hook_bus = hook_bus
        self._record_subscription = record_subscription or (lambda _subscription: None)
        self._plugins = plugin_registry
        self._output = output or NullOutput()
        self._host = host
        self._file_server = file_server
        self._media_sender = media_sender
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.agents = PluginAgentRegistrar(
            plugin_name=plugin_name,
            registry=agent_registry,
            record_registration=record_agent_registration,
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

    @property
    def adapter(self) -> Any:
        return self._adapter

    @property
    def hook_bus(self) -> Any:
        return self._hook_bus

    @property
    def plugins(self) -> Any:
        return self._plugins

    @property
    def plugin_host(self) -> Any:
        return self._host

    @property
    def output(self) -> OutputPort:
        return self._output

    def record_subscription(self, subscription: Any) -> None:
        self._record_subscription(subscription)

    async def send_private(self, user_id: int, message: MessagePayload) -> SendMsgResponse:
        return await self._adapter.send_private_msg(user_id, message)

    async def send_group(self, group_id: int, message: MessagePayload) -> SendMsgResponse:
        return await self._adapter.send_group_msg(group_id, message)

    async def send(self, conversation: ConversationRef, message: MessagePayload) -> SendMsgResponse:
        return await self._adapter.send(conversation, message)

    async def send_image(
        self,
        conversation: ConversationRef,
        *,
        path: Path | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> SendMsgResponse:
        if self._media_sender is None:
            raise RuntimeError("MediaSender not configured")
        if path is not None:
            return await self._media_sender.send_image(self._adapter, conversation, path=path)
        if data is not None:
            if self._file_server is None:
                raise RuntimeError("FileServer not configured")
            if not filename:
                raise ValueError("filename is required when sending raw data")
            if len(data) > 30_000_000:
                raise ValueError(f"Image data exceeds 30MB limit: {len(data)} bytes")
            suffix = Path(filename).suffix
            temp_path = self._data_dir / ".media_cache" / f"{uuid4().hex}{suffix}"
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                temp_path.write_bytes(data)
                return await self._media_sender.send_image(self._adapter, conversation, path=temp_path)
            finally:
                temp_path.unlink(missing_ok=True)
        raise ValueError("Must provide path or data+filename")

    async def send_audio(self, conversation: ConversationRef, *, path: Path) -> SendMsgResponse:
        if self._media_sender is None:
            raise RuntimeError("MediaSender not configured")
        return await self._media_sender.send_audio(self._adapter, conversation, path=Path(path))

    async def reply(self, event: dict[str, Any] | BaseModel, message: MessagePayload) -> SendMsgResponse:
        return await self.send(self.conversation_from_event(event), message)

    def conversation_from_event(self, event: dict[str, Any] | BaseModel) -> ConversationRef:
        data = event.model_dump(mode="python") if isinstance(event, BaseModel) else dict(event)
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

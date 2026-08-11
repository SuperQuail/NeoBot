from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel

from neobot_adapter.model.response import SendMsgResponse
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.screenshot import ScreenshotPort
from neobot_modloader.management import PluginControlFacade
from neobot_modloader.plugins.agents import PluginAgentRegistrar
from neobot_modloader.users import UserDirectory

MessagePayload = str | list[dict[str, Any]]


class MarkdownSkillRegistrar:
    """插件 Markdown Skill 注册器（owner 为插件名，卸载时自动清理）。"""

    def __init__(
        self,
        *,
        plugin_name: str,
        registry: Any | None,
        record_cleanup: Any | None,
    ) -> None:
        self._plugin_name = plugin_name
        self._registry = registry
        self._record_cleanup = record_cleanup
        self._registered = False

    @property
    def available(self) -> bool:
        """共享 Skill 注册表是否已注入。"""
        return self._registry is not None

    def register(self, skills: list[Any]) -> None:
        if self._registry is None:
            raise RuntimeError("Markdown skill registry is not available")
        if not skills:
            return
        self._registry.register_many(self._plugin_name, skills)
        self._registered = True
        if self._record_cleanup is not None:
            self._record_cleanup(self.unregister_all)

    def unregister_all(self) -> None:
        if self._registry is None or not self._registered:
            return
        self._registry.unregister_owner(self._plugin_name)
        self._registered = False


class PluginCommandRegistrar:
    """插件命令注册器:自动加插件名前缀,卸载时清理。

    用法::

        @ctx.app_commands.register("ping", description="响应测试")
        async def _ping(ctx: Any) -> str:
            return "pong"

    或::

        ctx.app_commands.register(
            Command(name="ping", description="响应测试", handler=_ping)
        )
    """

    def __init__(
        self,
        *,
        plugin_name: str,
        registry: Any | None,
        record_cleanup: Any | None,
    ) -> None:
        self._plugin_name = plugin_name
        self._registry = registry
        self._record_cleanup = record_cleanup
        self._registered: set[str] = set()

    @property
    def available(self) -> bool:
        return self._registry is not None

    def _command_name(self, name: str) -> str:
        return f"{self._plugin_name}__{name}"

    def register(self, command: Any) -> None:
        """注册命令(自动加 {plugin_name}__ 前缀)。"""
        if self._registry is None:
            raise RuntimeError("命令注册表不可用(未注入 app_commands)")
        command.name = self._command_name(command.name)
        self._registry.register(command)
        self._registered.add(command.name)
        if self._record_cleanup is not None:
            self._record_cleanup(self.unregister_all)

    def __call__(self, name: str, **kwargs: Any):
        """装饰器用法:@ctx.app_commands.register("ping", description=...)。"""
        from types import SimpleNamespace

        def _decorate(handler: Any) -> Any:
            self.register(
                SimpleNamespace(
                    name=name,
                    description=str(kwargs.get("description") or ""),
                    usage=str(kwargs.get("usage") or ""),
                    permission=int(kwargs.get("permission", 0)),
                    sync_reply=bool(kwargs.get("sync_reply", False)),
                    aliases=tuple(kwargs.get("aliases") or ()),
                    handler=handler,
                )
            )
            return handler

        return _decorate

    def unregister_all(self) -> None:
        if self._registry is None:
            return
        for name in list(self._registered):
            self._registry.unregister(name)
        self._registered.clear()


class RuntimePluginContext:
    """新 Plugin API 的内部运行时上下文。"""

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
        plugin_control: PluginControlFacade | None = None,
        markdown_skill_registry: Any | None = None,
        record_skill_cleanup: Any | None = None,
        screenshots: ScreenshotPort | None = None,
        app_commands: Any | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._plugin_dir = plugin_dir
        self._data_dir = data_dir
        self._config = dict(config or {})
        self._logger = logger or NullLogger()
        self._adapter = adapter
        self.users = UserDirectory(adapter)
        self._hook_bus = hook_bus
        self._record_subscription = record_subscription or (lambda _subscription: None)
        self._plugins = plugin_registry
        self._output = output or NullOutput()
        self._host = host
        self._file_server = file_server
        self._media_sender = media_sender
        self._plugin_control = plugin_control
        self.screenshots = screenshots
        self._app_commands = app_commands
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.agents = PluginAgentRegistrar(
            plugin_name=plugin_name,
            registry=agent_registry,
            record_registration=record_agent_registration,
        )
        self.markdown_skills = MarkdownSkillRegistrar(
            plugin_name=plugin_name,
            registry=markdown_skill_registry,
            record_cleanup=record_skill_cleanup,
        )
        self.app_commands = PluginCommandRegistrar(
            plugin_name=plugin_name,
            registry=app_commands,
            record_cleanup=record_skill_cleanup,
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
    def plugin_control(self) -> PluginControlFacade | None:
        return self._plugin_control

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

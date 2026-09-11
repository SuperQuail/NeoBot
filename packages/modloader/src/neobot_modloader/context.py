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
from neobot_modloader.generation import RuntimeGeneration
from neobot_modloader.loading.models import OFFICIAL_SOURCE, THIRD_PARTY_SOURCE
from neobot_modloader.management import PluginControlFacade
from neobot_modloader.plugins.agents import PluginAgentRegistrar
from neobot_modloader.users import UserDirectory

MessagePayload = str | list[dict[str, Any]]


class MarkdownSkillRegistrar:
    """插件 Markdown Skill 注册器（owner 为插件名，卸载时自动清理）。

    注册表由组合根在软重启时整体替换，因此这里保存"注册批次"而不只保存注册表
    引用：代际切换时把同一批 Skill 重放到新注册表，插件无需重新加载。
    """

    def __init__(
        self,
        *,
        plugin_name: str,
        registry: Any | None = None,
        registry_provider: Any | None = None,
        record_cleanup: Any | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._static_registry = registry
        self._registry_provider = registry_provider
        self._registrations: list[tuple[Any, list[Any]]] = []
        self._record_cleanup = record_cleanup

    def _current_registry(self) -> Any | None:
        if self._registry_provider is not None:
            return self._registry_provider()
        return self._static_registry

    @property
    def available(self) -> bool:
        """共享 Skill 注册表是否已注入。"""
        return self._current_registry() is not None

    @property
    def _registered(self) -> bool:
        """是否仍有已注册批次（注册失败不置位；清理失败保留以便重试）。"""
        return bool(self._registrations)

    def register(self, skills: list[Any]) -> None:
        registry = self._current_registry()
        if registry is None:
            raise RuntimeError("Markdown skill registry is not available")
        if not skills:
            return
        batch = list(skills)
        registry.register_many(self._plugin_name, batch)
        self._registrations.append((registry, batch))
        if self._record_cleanup is not None:
            self._record_cleanup(self.unregister_all)

    def rebind(self, previous: Any, current: Any) -> None:
        """代际切换：把旧注册表上的注册批次迁到新注册表。"""
        if current is None or current is previous:
            return
        moved: list[list[Any]] = []
        updated: list[tuple[Any, list[Any]]] = []
        for registry, batch in self._registrations:
            if registry is previous:
                registry.unregister_owner(self._plugin_name)
                moved.append(batch)
                updated.append((current, batch))
            else:
                updated.append((registry, batch))
        self._registrations = updated
        for batch in moved:
            current.register_many(self._plugin_name, list(batch))

    def unregister_all(self) -> None:
        for registry, _batch in self._registrations:
            unregister = getattr(registry, "unregister_owner", None)
            if callable(unregister):
                unregister(self._plugin_name)
        self._registrations.clear()


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
        source: str = THIRD_PARTY_SOURCE,
        generation_provider: Any | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._source = str(source or THIRD_PARTY_SOURCE)
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
        if generation_provider is None:
            # 兼容直接构造上下文的测试/旧调用：静态代际，不参与重绑。
            static_generation = RuntimeGeneration(
                agent_registry=agent_registry,
                skills_registry=markdown_skill_registry,
                screenshots=screenshots,
            )
            self._generation_provider = lambda: static_generation
        else:
            self._generation_provider = generation_provider
        self._app_commands = app_commands
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.agents = PluginAgentRegistrar(
            plugin_name=plugin_name,
            registry=agent_registry,
            registry_provider=lambda: self._generation_provider().agent_registry,
            record_registration=record_agent_registration,
        )
        self.markdown_skills = MarkdownSkillRegistrar(
            plugin_name=plugin_name,
            registry=markdown_skill_registry,
            registry_provider=lambda: self._generation_provider().skills_registry,
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
    def source(self) -> str:
        """插件来源：official（随本体分发）/ third_party（数据目录安装）。"""
        return self._source

    @property
    def official(self) -> bool:
        return self._source == OFFICIAL_SOURCE

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
    def screenshots(self) -> ScreenshotPort | None:
        """当前代际的截图端口；软重启后自动指向新对象。"""
        return self._generation_provider().screenshots

    def on_generation_change(
        self, previous: RuntimeGeneration, current: RuntimeGeneration
    ) -> None:
        """代际切换：把插件注册的 Agent / Markdown Skill 迁到新对象上。

        截图端口等"读时解析"的依赖无需迁移；命令注册表属核心对象也不迁移。
        """
        if current.agent_registry is not previous.agent_registry:
            self.agents.rebind(previous.agent_registry, current.agent_registry)
        if current.skills_registry is not previous.skills_registry:
            self.markdown_skills.rebind(
                previous.skills_registry, current.skills_registry
            )

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

    def require_plugin(self, name: str, specifier: str = "") -> Any:
        """取得前置插件句柄（依赖它的功能时使用）。

        ::

            handle = ctx.require_plugin("dashboard", ">=1.0.0")
            await handle.call("web.register_extension", {"extension": extension})

        前置插件不存在 / 未就绪 / 版本不满足时抛 PluginDependencyError。
        """
        if self._plugins is None:
            raise RuntimeError("插件注册表不可用")
        return self._plugins.require(name, specifier)

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

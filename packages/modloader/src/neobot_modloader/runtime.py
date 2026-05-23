from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort

from neobot_modloader.context import PluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import TrackedPluginHostFacade
from neobot_modloader.loader import FilesystemPluginLoader, LoadedPlugin, PluginLoadError
from neobot_modloader.manager import DefaultPluginManager


class PluginRuntime:
    def __init__(
        self,
        *,
        plugin_dir: Path,
        data_dir: Path,
        adapter: Any,
        logger_factory: Any,
        loader: FilesystemPluginLoader | None = None,
        manager: DefaultPluginManager | None = None,
        logger: Logger | None = None,
        agent_registry: Any | None = None,
        hook_bus: PluginHookBus | None = None,
        record_ai_reply_block: Any | None = None,
        output: OutputPort | None = None,
        host: Any | None = None,
    ) -> None:
        self.plugin_dir = plugin_dir.resolve()
        self.data_dir = data_dir.resolve()
        self.adapter = adapter
        self.logger_factory = logger_factory
        self.agent_registry = agent_registry
        self.record_ai_reply_block = record_ai_reply_block
        self.output = output or NullOutput()
        self.logger = logger or self._get_logger("modloader.runtime")
        self.hook_bus = hook_bus or PluginHookBus(
            logger=self._get_logger("modloader.hooks"),
            record_ai_reply_block=record_ai_reply_block,
            output=self.output,
        )
        self.host = host
        self.loader = loader or FilesystemPluginLoader(
            logger=self._get_logger("modloader.loader")
        )
        self.manager = manager or DefaultPluginManager(
            logger=self._get_logger("modloader.manager")
        )

    def load_all(self) -> None:
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"插件目录: {self.plugin_dir}")

        results = self.loader.load_all(self.plugin_dir)
        loaded_count = 0
        error_count = 0
        for result in results:
            if isinstance(result, PluginLoadError):
                error_count += 1
                self.logger.error(f"插件加载跳过 ({result.name}): {result.error}")
                continue
            self._register(result)
            loaded_count += 1
        self.logger.info(f"插件扫描完成: loaded={loaded_count}, errors={error_count}")

    async def load_registered(self) -> None:
        await self.manager.load_all()

    async def start_all(self) -> None:
        await self.manager.start_all()

    async def stop_all(self) -> None:
        await self.manager.stop_all()

    def _register(self, loaded: LoadedPlugin) -> None:
        logger = self._get_logger(f"plugin.{loaded.name}")
        tracked_host = (
            TrackedPluginHostFacade(
                self.host,
                lambda cleanup, name=loaded.name: self.manager.record_cleanup(name, cleanup),
            )
            if self.host is not None
            else None
        )
        context = PluginContext(
            plugin_name=loaded.name,
            plugin_dir=loaded.plugin_dir,
            data_dir=self.data_dir / loaded.name,
            config=loaded.config,
            logger=logger,
            adapter=self.adapter,
            hook_bus=self.hook_bus,
            record_subscription=lambda subscription, name=loaded.name: self.manager.record_subscription(
                name, subscription
            ),
            agent_registry=self.agent_registry,
            record_agent_registration=lambda registered_name, agent, name=loaded.name: self.manager.record_agent_registration(
                name, registered_name, agent
            ),
            plugin_registry=self.manager.registry_view,
            output=self.output,
            host=tracked_host,
        )
        try:
            self.manager.register(loaded.plugin, context)
        except Exception as exc:
            self.logger.exception(f"插件注册失败 ({loaded.name}): {exc}")

    def _get_logger(self, name: str) -> Logger:
        get_logger = getattr(self.logger_factory, "get_logger", None)
        if callable(get_logger):
            return get_logger(name)
        return NullLogger()

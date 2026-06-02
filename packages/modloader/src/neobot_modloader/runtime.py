from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.dependencies import PythonDependencyInstaller
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import TrackedPluginHostFacade
from neobot_modloader.loader import (
    DiscoveredPlugin,
    FilesystemPluginLoader,
    LoadedPlugin,
    PluginLoadError,
    missing_python_dependencies,
)
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
        file_server: Any | None = None,
        media_sender: Any | None = None,
        dependency_installer: PythonDependencyInstaller | None = None,
        auto_install_dependencies: bool = False,
    ) -> None:
        self.plugin_dir = plugin_dir.resolve()
        self.data_dir = data_dir.resolve()
        self.adapter = adapter
        self.logger_factory = logger_factory
        self.agent_registry = agent_registry
        self._file_server = file_server
        self._media_sender = media_sender
        self.record_ai_reply_block = record_ai_reply_block
        self.output = output or NullOutput()
        self.logger = logger or self._get_logger("modloader.runtime")
        self.hook_bus = hook_bus or PluginHookBus(
            logger=self._get_logger("modloader.hooks"),
            record_ai_reply_block=record_ai_reply_block,
            output=self.output,
        )
        self.host = host
        self.loader = loader or FilesystemPluginLoader(logger=self._get_logger("modloader.loader"))
        self.manager = manager or DefaultPluginManager(logger=self._get_logger("modloader.manager"))
        self.dependency_installer = dependency_installer or PythonDependencyInstaller(logger=self.logger)
        self.auto_install_dependencies = auto_install_dependencies
        self._loaded_modules: dict[str, tuple[str, ...]] = {}
        self._loaded_paths: dict[str, Path] = {}

    def discover_all(self) -> list[DiscoveredPlugin | PluginLoadError]:
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        return self.loader.discover_all(self.plugin_dir)

    def load_all(self, *, auto_install_dependencies: bool | None = None) -> None:
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"插件目录: {self.plugin_dir}")

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        if install:
            self._confirm_and_install_missing_dependencies()

        results = self.loader.load_all(self.plugin_dir)
        loaded_count = 0
        error_count = 0
        for result in results:
            if isinstance(result, PluginLoadError):
                error_count += 1
                self.logger.error(f"插件加载跳过 ({result.name}): {result.error}")
                continue
            missing = missing_python_dependencies(result.python_dependencies)
            if missing:
                error_count += 1
                self.logger.error(f"插件加载跳过 ({result.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
                self.loader.clear_module_cache(result.module_names)
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

    async def reload_plugin(self, name: str, *, start: bool = True, auto_install_dependencies: bool | None = None) -> bool:
        plugin_path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        if plugin_path is None:
            raise KeyError(f"插件未找到: {name}")

        old_modules = self._loaded_modules.get(name, ())

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        if install:
            discovered = self.loader.discover_all(self.plugin_dir)
            missing = []
            for item in discovered:
                if isinstance(item, DiscoveredPlugin) and item.name == name:
                    missing.extend(item.missing_python_dependencies)
            if missing:
                self.dependency_installer.confirm_and_install(missing)

        result = self.loader.load_one(plugin_path)
        if result is None:
            return False
        if isinstance(result, PluginLoadError):
            self.logger.error(f"插件重载失败 ({result.name}): {result.error}")
            self.loader.clear_module_cache(getattr(result, "module_names", ()))
            return False
        missing = missing_python_dependencies(result.python_dependencies)
        if missing:
            self.logger.error(f"插件重载失败 ({result.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
            self.loader.clear_module_cache(result.module_names)
            return False
        await self.manager.remove_plugin(name)
        self.loader.clear_module_cache(old_modules)
        self._loaded_modules.pop(name, None)
        self._loaded_paths.pop(name, None)
        self._register(result)
        await self.manager.load_plugin(result.name)
        if start:
            await self.manager.start_plugin(result.name)
        return True

    async def reload_all(self, *, start: bool = True, auto_install_dependencies: bool | None = None) -> None:
        names = list(self.manager.names())
        for name in names:
            await self.reload_plugin(name, start=start, auto_install_dependencies=auto_install_dependencies)

    def _confirm_and_install_missing_dependencies(self) -> None:
        missing: list[str] = []
        for result in self.discover_all():
            if isinstance(result, DiscoveredPlugin) and result.enabled:
                missing.extend(result.missing_python_dependencies)
        if missing:
            self.dependency_installer.confirm_and_install(missing)

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
        context = RuntimePluginContext(
            plugin_name=loaded.name,
            plugin_dir=loaded.plugin_dir,
            data_dir=self.data_dir / loaded.name,
            config=loaded.config,
            logger=logger,
            adapter=self.adapter,
            hook_bus=self.hook_bus,
            record_subscription=lambda subscription, name=loaded.name: self.manager.record_subscription(name, subscription),
            agent_registry=self.agent_registry,
            record_agent_registration=lambda registered_name, agent, name=loaded.name: self.manager.record_agent_registration(
                name, registered_name, agent
            ),
            plugin_registry=self.manager.registry_view,
            output=self.output,
            host=tracked_host,
            file_server=self._file_server,
            media_sender=self._media_sender,
        )
        try:
            self.manager.register(loaded.plugin, context)
            self._loaded_modules[loaded.name] = loaded.module_names
            self._loaded_paths[loaded.name] = self._path_for_loaded(loaded)
        except Exception as exc:
            self.logger.exception(f"插件注册失败 ({loaded.name}): {exc}")

    def _find_plugin_path(self, name: str) -> Path | None:
        for result in self.discover_all():
            if isinstance(result, DiscoveredPlugin) and result.name == name:
                return self._path_for_discovered(result)
        return None

    def _path_for_loaded(self, loaded: LoadedPlugin) -> Path:
        if loaded.source_path is not None:
            return loaded.source_path
        package_init = loaded.plugin_dir / "__init__.py"
        if package_init.is_file():
            return loaded.plugin_dir
        return loaded.plugin_dir / f"{loaded.name}.py"

    def _path_for_discovered(self, discovered: DiscoveredPlugin) -> Path:
        if discovered.source_path is not None:
            return discovered.source_path
        package_init = discovered.plugin_dir / "__init__.py"
        if package_init.is_file():
            return discovered.plugin_dir
        return discovered.plugin_dir / f"{discovered.name}.py"

    def _get_logger(self, name: str) -> Logger:
        get_logger = getattr(self.logger_factory, "get_logger", None)
        if callable(get_logger):
            return get_logger(name)
        return NullLogger()

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.plugin import PluginState

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.dependencies import PythonDependencyInstaller
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import TrackedPluginHostFacade
from neobot_modloader.loading.manifest import read_dependencies, read_manifest, read_python_dependencies
from neobot_modloader.loader import (
    DiscoveredPlugin,
    FilesystemPluginLoader,
    LoadedPlugin,
    PluginLoadError,
    missing_python_dependencies,
)
from neobot_modloader.management import PluginControlFacade, PluginOperationResult, PluginSnapshot
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
        self.control = PluginControlFacade(self)

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
            if self._register(result):
                loaded_count += 1
            else:
                error_count += 1
        self.logger.info(f"插件扫描完成: loaded={loaded_count}, errors={error_count}")

    async def load_registered(self) -> None:
        await self.manager.load_all()

    async def start_all(self) -> None:
        await self.manager.start_all()

    async def stop_all(self) -> None:
        await self.manager.stop_all()

    async def load_plugin_path(
        self,
        path: Path,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        plugin_path = Path(path).resolve()
        if not self._is_path_under_plugin_dir(plugin_path):
            return PluginOperationResult(
                ok=False,
                name=plugin_path.stem,
                error=f"插件路径不在插件目录内: {plugin_path}",
                path=plugin_path,
            )

        result = self.loader.load_one(plugin_path)
        if result is None:
            return PluginOperationResult(ok=False, name=plugin_path.stem, error=f"插件未找到: {plugin_path}", path=plugin_path)
        if isinstance(result, PluginLoadError):
            self.logger.error(f"插件加载失败 ({result.name}): {result.error}")
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=PluginState.ERROR.value,
                error=str(result.error),
                path=result.plugin_dir,
            )

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        return await self._activate_loaded_plugin(result, start=start, auto_install_dependencies=install)

    async def unload_plugin(self, name: str) -> PluginOperationResult:
        path = self._loaded_paths.get(name)
        modules = self._loaded_modules.get(name, ())
        record = await self.manager.remove_plugin(name)
        if modules:
            self.loader.clear_module_cache(modules)
        self._loaded_modules.pop(name, None)
        self._loaded_paths.pop(name, None)
        if record is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=f"插件未注册: {name}",
                path=path,
            )
        return PluginOperationResult(ok=True, name=name, state=PluginState.UNLOADED.value, path=path)

    async def start_plugin(self, name: str) -> PluginOperationResult:
        record = self.manager.get_record(name)
        path = self._loaded_paths.get(name)
        if record is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=f"插件未注册: {name}",
                path=path,
            )
        await self.manager.start_plugin(name)
        return self._operation_result_from_record(name, path=path)

    async def stop_plugin(self, name: str) -> PluginOperationResult:
        record = self.manager.get_record(name)
        path = self._loaded_paths.get(name)
        if record is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=f"插件未注册: {name}",
                path=path,
            )
        await self.manager.stop_plugin(name)
        return self._operation_result_from_record(name, path=path)

    async def reload_plugin_result(
        self,
        name: str,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        plugin_path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        if plugin_path is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=f"插件未找到: {name}",
            )

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
            return PluginOperationResult(ok=False, name=name, error=f"插件未找到: {plugin_path}", path=plugin_path)
        if isinstance(result, PluginLoadError):
            self.logger.error(f"插件重载失败 ({result.name}): {result.error}")
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=PluginState.ERROR.value,
                error=str(result.error),
                path=result.plugin_dir,
            )
        missing = missing_python_dependencies(result.python_dependencies)
        if missing:
            self.logger.error(f"插件重载失败 ({result.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
            self.loader.clear_module_cache(result.module_names)
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=PluginState.ERROR.value,
                error=f"缺少 PyPI 依赖: {', '.join(missing)}",
                path=self._path_for_loaded(result),
            )
        await self.manager.remove_plugin(name)
        self.loader.clear_module_cache(old_modules)
        self._loaded_modules.pop(name, None)
        self._loaded_paths.pop(name, None)
        if not self._register(result):
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=PluginState.ERROR.value,
                error=f"插件注册失败: {result.name}",
                path=self._path_for_loaded(result),
            )
        await self.manager.load_plugin(result.name)
        if start:
            await self.manager.start_plugin(result.name)
        return self._operation_result_from_record(result.name, path=self._path_for_loaded(result))

    async def reload_plugin(self, name: str, *, start: bool = True, auto_install_dependencies: bool | None = None) -> bool:
        result = await self.reload_plugin_result(
            name,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )
        if not result.ok and result.state == PluginState.UNLOADED.value and result.path is None:
            raise KeyError(f"插件未找到: {name}")
        return result.ok

    async def reload_all(self, *, start: bool = True, auto_install_dependencies: bool | None = None) -> None:
        names = list(self.manager.names())
        for name in names:
            await self.reload_plugin(name, start=start, auto_install_dependencies=auto_install_dependencies)

    def snapshot_plugins(self) -> list[PluginSnapshot]:
        snapshots: list[PluginSnapshot] = []
        seen_names: set[str] = set()
        seen_paths: set[Path] = set()

        for result in self.discover_all():
            if isinstance(result, PluginLoadError):
                path = result.plugin_dir
                snapshots.append(
                    PluginSnapshot(
                        name=result.name,
                        state=PluginState.ERROR.value,
                        enabled=True,
                        path=path,
                        kind=self._kind_for_path(path),
                        error=str(result.error),
                    )
                )
                seen_names.add(result.name)
                seen_paths.add(path.resolve())
                continue

            path = self._path_for_discovered(result)
            state = self._state_value(result.name)
            if state == PluginState.UNLOADED.value and result.missing_python_dependencies:
                state = PluginState.ERROR.value
            snapshots.append(
                PluginSnapshot(
                    name=result.name,
                    version=result.version,
                    state=state,
                    enabled=result.enabled,
                    path=path,
                    kind=self._kind_for_path(path),
                    error=str(result.error) if result.error is not None else None,
                    description=result.description,
                    author=result.author,
                    dependencies=result.dependencies,
                    python_dependencies=result.python_dependencies,
                    missing_python_dependencies=result.missing_python_dependencies,
                )
            )
            seen_names.add(result.name)
            seen_paths.add(path.resolve())

        for snapshot in self._disabled_prefix_snapshots(seen_paths):
            snapshots.append(snapshot)
            seen_names.add(snapshot.name)

        for name in self.manager.names():
            if name in seen_names:
                continue
            record = self.manager.get_record(name)
            plugin = record.plugin if record is not None else None
            path = self._loaded_paths.get(name)
            snapshots.append(
                PluginSnapshot(
                    name=name,
                    version=str(getattr(plugin, "version", "0.1.0") or "0.1.0"),
                    state=self._state_value(name),
                    enabled=True,
                    path=path,
                    kind=self._kind_for_path(path),
                    error=str(record.error) if record is not None and record.error is not None else None,
                    description=str(getattr(plugin, "description", "") or ""),
                    author=str(getattr(plugin, "author", "") or ""),
                    dependencies=tuple(getattr(plugin, "dependencies", ()) or ()),
                    python_dependencies=tuple(getattr(plugin, "python_dependencies", ()) or ()),
                )
            )

        return sorted(snapshots, key=lambda item: item.name.lower())

    def _confirm_and_install_missing_dependencies(self) -> None:
        missing: list[str] = []
        for result in self.discover_all():
            if isinstance(result, DiscoveredPlugin) and result.enabled:
                missing.extend(result.missing_python_dependencies)
        if missing:
            self.dependency_installer.confirm_and_install(missing)

    async def _activate_loaded_plugin(
        self,
        loaded: LoadedPlugin,
        *,
        start: bool,
        auto_install_dependencies: bool,
    ) -> PluginOperationResult:
        missing = list(missing_python_dependencies(loaded.python_dependencies))
        if missing and auto_install_dependencies:
            self.dependency_installer.confirm_and_install(missing)
            missing = list(missing_python_dependencies(loaded.python_dependencies))
        if missing:
            self.logger.error(f"插件加载失败 ({loaded.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
            self.loader.clear_module_cache(loaded.module_names)
            return PluginOperationResult(
                ok=False,
                name=loaded.name,
                state=PluginState.ERROR.value,
                error=f"缺少 PyPI 依赖: {', '.join(missing)}",
                path=self._path_for_loaded(loaded),
            )

        if self.manager.get_record(loaded.name) is not None:
            await self.unload_plugin(loaded.name)

        if not self._register(loaded):
            return PluginOperationResult(
                ok=False,
                name=loaded.name,
                state=PluginState.ERROR.value,
                error=f"插件注册失败: {loaded.name}",
                path=self._path_for_loaded(loaded),
            )

        await self.manager.load_plugin(loaded.name)
        if start:
            await self.manager.start_plugin(loaded.name)
        return self._operation_result_from_record(loaded.name, path=self._path_for_loaded(loaded))

    def _operation_result_from_record(self, name: str, *, path: Path | None = None) -> PluginOperationResult:
        record = self.manager.get_record(name)
        state = self._state_value(name)
        error = str(record.error) if record is not None and record.error is not None else None
        return PluginOperationResult(
            ok=record is not None and record.error is None and state != PluginState.ERROR.value,
            name=name,
            state=state,
            error=error,
            path=path,
        )

    def _state_value(self, name: str) -> str:
        state = self.manager.get_state(name)
        if isinstance(state, PluginState):
            return state.value
        return str(state)

    def _is_path_under_plugin_dir(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.plugin_dir)
        except ValueError:
            return False
        return True

    def _kind_for_path(self, path: Path | None) -> str:
        if path is None:
            return "unknown"
        if path.is_file() and path.suffix == ".py":
            return "single-file"
        if path.is_dir():
            return "package"
        return "unknown"

    def _disabled_prefix_snapshots(self, seen_paths: set[Path]) -> list[PluginSnapshot]:
        if not self.plugin_dir.exists() or not self.plugin_dir.is_dir():
            return []
        snapshots: list[PluginSnapshot] = []
        for entry in sorted(self.plugin_dir.iterdir(), key=lambda item: item.name.lower()):
            if not entry.name.startswith("_") or entry.name == "__pycache__":
                continue
            if entry.resolve() in seen_paths:
                continue
            real_name = entry.name[1:]
            if not real_name:
                continue
            if entry.is_dir():
                snapshots.append(self._disabled_package_snapshot(entry, real_name))
            elif entry.is_file() and entry.suffix == ".py":
                snapshots.append(
                    PluginSnapshot(
                        name=real_name,
                        state=PluginState.UNLOADED.value,
                        enabled=False,
                        path=entry,
                        kind="single-file",
                    )
                )
        return snapshots

    def _disabled_package_snapshot(self, path: Path, fallback_name: str) -> PluginSnapshot:
        metadata: dict[str, Any] = {}
        error: str | None = None
        try:
            metadata = read_manifest(path / "plugin.toml")
            dependencies = read_dependencies(metadata.get("dependencies") or [])
            python_dependencies = read_python_dependencies(metadata)
            missing = missing_python_dependencies(python_dependencies)
        except Exception as exc:
            dependencies = ()
            python_dependencies = ()
            missing = ()
            error = str(exc)
        return PluginSnapshot(
            name=str(metadata.get("name") or fallback_name),
            version=str(metadata.get("version") or "0.1.0"),
            state=PluginState.ERROR.value if error else PluginState.UNLOADED.value,
            enabled=False,
            path=path,
            kind="package",
            error=error,
            description=str(metadata.get("description") or ""),
            author=str(metadata.get("author") or ""),
            dependencies=dependencies,
            python_dependencies=python_dependencies,
            missing_python_dependencies=missing,
        )

    def _register(self, loaded: LoadedPlugin) -> bool:
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
            plugin_control=self.control,
        )
        try:
            self.manager.register(loaded.plugin, context)
            self._loaded_modules[loaded.name] = loaded.module_names
            self._loaded_paths[loaded.name] = self._path_for_loaded(loaded)
            return True
        except Exception as exc:
            self.logger.exception(f"插件注册失败 ({loaded.name}): {exc}")
            return False

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

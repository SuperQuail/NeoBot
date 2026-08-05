from __future__ import annotations

import asyncio
import inspect
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.plugin import PluginState
from neobot_contracts.ports.screenshot import ScreenshotPort

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
from neobot_modloader.manager import DefaultPluginManager, ReentrantLock
from neobot_modloader.plugins.registration import validate_plugin_name


class OperationBusy(Exception):
    """在锁顺序约束下无法安全等待的嵌套操作（避免互卸载死锁）。"""

    def __init__(self, name: str) -> None:
        super().__init__(f"插件 {name!r} 正被其他任务的事务占用，无法按锁顺序等待")
        self.name = name


class _RuntimePluginControlFacade(PluginControlFacade):
    async def unload(self, name: str, *, force: bool = False) -> PluginOperationResult:
        return await self._runtime.unload_plugin(name, force=force)

    async def force_unload(self, name: str) -> PluginOperationResult:
        return await self._runtime.force_unload_plugin(name)


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
        skills_registry: Any | None = None,
        hook_bus: PluginHookBus | None = None,
        record_ai_reply_block: Any | None = None,
        output: OutputPort | None = None,
        host: Any | None = None,
        file_server: Any | None = None,
        media_sender: Any | None = None,
        screenshots: ScreenshotPort | None = None,
        dependency_installer: PythonDependencyInstaller | None = None,
        auto_install_dependencies: bool = False,
    ) -> None:
        self.plugin_dir = plugin_dir.resolve()
        self.data_dir = data_dir.resolve()
        self.adapter = adapter
        self.logger_factory = logger_factory
        self.agent_registry = agent_registry
        self.skills_registry = skills_registry
        self._file_server = file_server
        self._media_sender = media_sender
        self.screenshots = screenshots
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
        self._operation_gate = asyncio.Lock()
        self._operation_locks: dict[str, ReentrantLock] = {}
        self._operation_paths: dict[Path, str] = {}
        self._operation_path_users: dict[Path, int] = {}
        self._committed_operation_paths: set[Path] = set()
        self._scan_guard = threading.RLock()
        self.control = _RuntimePluginControlFacade(self)

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
        # 同步扫描整体无 await，检查-注册在事件循环内原子；scan guard 防止多线程重复进入。
        with self._scan_guard:
            existing = set(self.manager.names())
            for result in results:
                if isinstance(result, PluginLoadError):
                    error_count += 1
                    self.logger.error(f"插件加载跳过 ({result.name}): {result.error}")
                    continue
                if result.name in existing:
                    # 已注册（例如上次 load_all / 在途操作）时跳过，避免重注册复活与误报错误；
                    # 该次导入的模块无人持有，立即清除。
                    self.logger.warning(f"插件已注册，跳过重复注册: {result.name}")
                    self.loader.clear_module_cache(result.module_names)
                    continue
                missing = missing_python_dependencies(result.python_dependencies)
                if missing:
                    error_count += 1
                    self.logger.error(f"插件加载跳过 ({result.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
                    self.loader.clear_module_cache(result.module_names)
                    continue
                if self._register(result):
                    loaded_count += 1
                    existing.add(result.name)
                else:
                    error_count += 1
        self.logger.info(f"插件扫描完成: loaded={loaded_count}, errors={error_count}")

    async def load_registered(self) -> None:
        for name in list(self.manager.names()):
            async with self._named_operation(name):
                await self.manager.load_plugin(name)

    async def start_all(self) -> None:
        for name in list(self.manager.names()):
            async with self._named_operation(name):
                await self.manager.start_plugin(name)

    async def stop_all(self) -> None:
        for name in reversed(list(self.manager.names())):
            async with self._named_operation(name):
                await self.manager.stop_plugin(name)

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

        result: LoadedPlugin | PluginLoadError | None = None
        try:
            async with self._path_operation(plugin_path) as operation:
                result = self.loader.load_one(plugin_path)
                if isinstance(result, LoadedPlugin):
                    await operation.bind(result.name)
                outcome = await self._load_plugin_path_locked(
                    plugin_path,
                    result,
                    start=start,
                    auto_install_dependencies=auto_install_dependencies,
                )
                if outcome.ok:
                    operation.commit()
        except asyncio.CancelledError:
            if isinstance(result, LoadedPlugin):
                record = self.manager.get_record(result.name)
                if record is None or record.plugin is not result.plugin:
                    self.loader.clear_module_cache(result.module_names)
            raise
        except OperationBusy as exc:
            # bind 前已完成导入：失败路径必须清除刚导入的模块代，避免 sys.modules 孤儿
            if isinstance(result, LoadedPlugin):
                self.loader.clear_module_cache(result.module_names)
            self._prune_operation_lock(exc.name)
            return PluginOperationResult(ok=False, name=exc.name, error=str(exc), path=plugin_path)
        if not outcome.ok:
            self._prune_operation_lock(outcome.name)
        return outcome

    async def _load_plugin_path_locked(
        self,
        plugin_path: Path,
        result: LoadedPlugin | PluginLoadError | None,
        *,
        start: bool,
        auto_install_dependencies: bool | None,
    ) -> PluginOperationResult:
        if result is None:
            return PluginOperationResult(ok=False, name=plugin_path.stem, error=f"插件未找到: {plugin_path}", path=plugin_path)
        if isinstance(result, PluginLoadError):
            self.logger.error(f"插件加载失败 ({result.name}): {result.error}")
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=PluginState.ERROR.value,
                error=_error_text(result.error),
                path=result.plugin_dir,
            )

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        return await self._activate_loaded_plugin(result, start=start, auto_install_dependencies=install)

    async def unload_plugin(self, name: str, *, force: bool = False) -> PluginOperationResult:
        try:
            async with self._named_operation(name):
                result = await self._unload_plugin_locked(name, force=force)
        except OperationBusy as exc:
            self._prune_operation_lock(name)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=str(exc),
                path=self._loaded_paths.get(name),
            )
        # 成功与失败路径都剪枝：ghost/未注册操作不得累积名字锁
        self._prune_operation_lock(name)
        return result

    async def force_unload_plugin(self, name: str) -> PluginOperationResult:
        return await self.unload_plugin(name, force=True)

    async def _unload_plugin_locked(self, name: str, *, force: bool = False) -> PluginOperationResult:
        path = self._loaded_paths.get(name)
        modules = self._loaded_modules.get(name, ())
        expected = self.manager.get_record(name)
        if expected is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=f"插件未注册: {name}",
                path=path,
            )
        previous_error = expected.error
        try:
            record = await self._remove_manager_record(name, expected=expected, force=force)
        except asyncio.CancelledError:
            if self.manager.get_record(name) is not expected:
                self._clear_plugin_tracking(name, path=path, modules=modules)
            raise
        current = self.manager.get_record(name)
        if current is expected:
            incomplete = self._operation_result_from_record(name, path=path)
            if not incomplete.ok:
                return incomplete
            return PluginOperationResult(
                ok=False,
                name=name,
                state=incomplete.state,
                error=f"插件卸载尚未完成: {name} ({incomplete.state})",
                path=path,
            )
        if record is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=f"插件已被并发替换或未注册: {name}",
                path=path,
            )
        if current is not None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=f"插件已被并发替换: {name}",
                path=path,
            )

        self._clear_plugin_tracking(name, path=path, modules=modules)
        removed_error = getattr(record, "error", None)
        if force:
            bypassed_error = removed_error or previous_error
            return PluginOperationResult(
                ok=True,
                name=name,
                state=PluginState.UNLOADED.value,
                error=(
                    f"插件已强制卸载，停止错误被绕过: {_error_text(bypassed_error)}"
                    if bypassed_error is not None
                    else None
                ),
                requires_restart=True,
                path=path,
            )
        if removed_error is not None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=PluginState.UNLOADED.value,
                error=_error_text(removed_error),
                path=path,
            )
        return PluginOperationResult(ok=True, name=name, state=PluginState.UNLOADED.value, path=path)

    async def start_plugin(self, name: str) -> PluginOperationResult:
        try:
            async with self._named_operation(name):
                result = await self._start_plugin_locked(name)
        except OperationBusy as exc:
            self._prune_operation_lock(name)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=str(exc),
                path=self._loaded_paths.get(name),
            )
        if not result.ok:
            self._prune_operation_lock(name)
        return result

    async def _start_plugin_locked(self, name: str) -> PluginOperationResult:
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
        if record.state is PluginState.RUNNING and record.error is None:
            return PluginOperationResult(ok=True, name=name, state=PluginState.RUNNING.value, path=path)
        if record.state is PluginState.UNLOADED:
            await self.manager.load_plugin(name)
            loaded = self._operation_result_from_record(
                name,
                path=path,
                expected_states={PluginState.LOADED},
            )
            if not loaded.ok:
                return loaded
        await self.manager.start_plugin(name)
        return self._operation_result_from_record(
            name,
            path=path,
            expected_states={PluginState.RUNNING},
        )

    async def stop_plugin(self, name: str) -> PluginOperationResult:
        try:
            async with self._named_operation(name):
                result = await self._stop_plugin_locked(name)
        except OperationBusy as exc:
            self._prune_operation_lock(name)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=str(exc),
                path=self._loaded_paths.get(name),
            )
        if not result.ok:
            self._prune_operation_lock(name)
        return result

    async def _stop_plugin_locked(self, name: str) -> PluginOperationResult:
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
        if record.state is PluginState.UNLOADED and record.error is None:
            return PluginOperationResult(ok=True, name=name, state=PluginState.UNLOADED.value, path=path)
        if record.state is PluginState.STOPPED and not record.stop_failed and record.error is None:
            return PluginOperationResult(ok=True, name=name, state=PluginState.STOPPED.value, path=path)
        await self.manager.stop_plugin(name)
        return self._operation_result_from_record(
            name,
            path=path,
            expected_states={PluginState.STOPPED, PluginState.UNLOADED},
        )

    async def reload_plugin_result(
        self,
        name: str,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        try:
            async with self._named_operation(name):
                result = await self._reload_plugin_result_locked(
                    name,
                    start=start,
                    auto_install_dependencies=auto_install_dependencies,
                )
        except OperationBusy as exc:
            self._prune_operation_lock(name)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=str(exc),
                path=self._loaded_paths.get(name),
            )
        if not result.ok:
            self._prune_operation_lock(name)
        return result

    async def _reload_plugin_result_locked(
        self,
        name: str,
        *,
        start: bool,
        auto_install_dependencies: bool | None,
    ) -> PluginOperationResult:
        plugin_path = self._loaded_paths.get(name)
        if plugin_path is None or not plugin_path.exists():
            plugin_path = self._find_plugin_path(name)
        if plugin_path is None:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=f"插件未找到: {name}",
                path=self._loaded_paths.get(name),
            )

        old_record = self.manager.get_record(name)
        old_modules = self._loaded_modules.get(name, ())
        old_path = self._loaded_paths.get(name) or plugin_path
        old_state = old_record.state if old_record is not None else PluginState.UNLOADED
        old_error = old_record.error if old_record is not None else None
        old_stop_failed = bool(getattr(old_record, "stop_failed", False))

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
                state=self._state_value(name) if old_record is not None else PluginState.ERROR.value,
                error=_error_text(result.error),
                path=result.plugin_dir,
            )
        if old_record is not None and result.name != name:
            self.loader.clear_module_cache(result.module_names)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=f"插件重载不能更改名称: {name!r} -> {result.name!r}",
                path=plugin_path,
            )
        missing = missing_python_dependencies(result.python_dependencies)
        if missing:
            self.logger.error(f"插件重载失败 ({result.name}): 缺少 PyPI 依赖: {', '.join(missing)}")
            self.loader.clear_module_cache(result.module_names)
            return PluginOperationResult(
                ok=False,
                name=result.name,
                state=self._state_value(name) if old_record is not None else PluginState.ERROR.value,
                error=f"缺少 PyPI 依赖: {', '.join(missing)}",
                path=self._path_for_loaded(result),
            )

        if old_record is None:
            return await self._activate_loaded_plugin(result, start=start, auto_install_dependencies=False)

        try:
            removed = await self._remove_manager_record(name, expected=old_record, force=False)
        except asyncio.CancelledError:
            self.loader.clear_module_cache(result.module_names)
            raise

        current = self.manager.get_record(name)
        if current is old_record or removed is None:
            self.loader.clear_module_cache(result.module_names)
            error = current.error if current is not None else getattr(removed, "error", None)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=_error_text(error) if error is not None else f"插件已被并发替换: {name}",
                path=plugin_path,
            )
        if current is not None:
            self.loader.clear_module_cache(result.module_names)
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error=f"插件已被并发替换: {name}",
                path=plugin_path,
            )

        removed_error = getattr(removed, "error", None)
        if removed_error is not None:
            self.loader.clear_module_cache(result.module_names)
            rollback_error = await self._restore_old_generation(
                name,
                old_record=old_record,
                old_state=old_state,
                old_error=old_error,
                old_stop_failed=old_stop_failed,
                old_modules=old_modules,
                old_path=old_path,
            )
            return self._failed_reload_result(
                name,
                path=plugin_path,
                error=_error_text(removed_error),
                rollback_error=rollback_error,
            )

        if not self._register(result):
            rollback_error = await self._restore_old_generation(
                name,
                old_record=old_record,
                old_state=old_state,
                old_error=old_error,
                old_stop_failed=old_stop_failed,
                old_modules=old_modules,
                old_path=old_path,
            )
            return self._failed_reload_result(
                name,
                path=plugin_path,
                error=f"插件注册失败: {result.name}",
                rollback_error=rollback_error,
            )

        candidate_record = self.manager.get_record(name)
        try:
            await self.manager.load_plugin(name)
            if start and self.manager.get_state(name) is PluginState.LOADED:
                await self.manager.start_plugin(name)
        except asyncio.CancelledError:
            rollback_error = await self._rollback_failed_generation(
                name,
                candidate_record=candidate_record,
                candidate_modules=result.module_names,
                old_record=old_record,
                old_state=old_state,
                old_error=old_error,
                old_stop_failed=old_stop_failed,
                old_modules=old_modules,
                old_path=old_path,
            )
            if rollback_error is not None:
                self.logger.error(f"插件重载取消后的回滚失败 ({name}): {rollback_error}")
            raise

        expected_states = {PluginState.RUNNING} if start else {PluginState.LOADED}
        outcome = self._operation_result_from_record(
            name,
            path=self._path_for_loaded(result),
            expected_states=expected_states,
        )
        if outcome.ok:
            retained = set(result.module_names)
            stale_modules = tuple(module for module in old_modules if module not in retained)
            if stale_modules:
                self.loader.clear_module_cache(stale_modules)
            return outcome

        rollback_error = await self._rollback_failed_generation(
            name,
            candidate_record=candidate_record,
            candidate_modules=result.module_names,
            old_record=old_record,
            old_state=old_state,
            old_error=old_error,
            old_stop_failed=old_stop_failed,
            old_modules=old_modules,
            old_path=old_path,
        )
        return self._failed_reload_result(
            name,
            path=plugin_path,
            error=outcome.error or f"插件新版本未进入预期状态: {outcome.state}",
            rollback_error=rollback_error,
        )

    async def reload_plugin(self, name: str, *, start: bool = True, auto_install_dependencies: bool | None = None) -> bool:
        result = await self.reload_plugin_result(
            name,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )
        if not result.ok and result.state == PluginState.UNLOADED.value and result.path is None:
            raise KeyError(f"插件未找到: {name}")
        return result.ok

    async def _rollback_failed_generation(
        self,
        name: str,
        *,
        candidate_record: Any,
        candidate_modules: tuple[str, ...],
        old_record: Any,
        old_state: PluginState,
        old_error: Exception | None,
        old_stop_failed: bool,
        old_modules: tuple[str, ...],
        old_path: Path,
    ) -> str | None:
        errors: list[str] = []
        discard_error = await self._discard_candidate_generation(
            name,
            candidate_record=candidate_record,
            candidate_modules=candidate_modules,
        )
        if discard_error is not None:
            errors.append(discard_error)
        restore_error = await self._restore_old_generation(
            name,
            old_record=old_record,
            old_state=old_state,
            old_error=old_error,
            old_stop_failed=old_stop_failed,
            old_modules=old_modules,
            old_path=old_path,
        )
        if restore_error is not None:
            errors.append(restore_error)
        return "; ".join(errors) if errors else None

    async def _discard_candidate_generation(
        self,
        name: str,
        *,
        candidate_record: Any,
        candidate_modules: tuple[str, ...],
    ) -> str | None:
        errors: list[str] = []
        current = self.manager.get_record(name)
        if candidate_record is not None and current is candidate_record:
            if candidate_record.state is PluginState.ERROR:
                removed = await self._remove_manager_record(name, expected=candidate_record, force=True)
                if self.manager.get_record(name) is candidate_record or removed is None:
                    errors.append(f"无法移除失败的新版本: {candidate_record.error or name}")
            else:
                removed = await self._remove_manager_record(name, expected=candidate_record, force=False)
                current = self.manager.get_record(name)
                if current is candidate_record:
                    cleanup_error = current.error
                    forced = await self._remove_manager_record(name, expected=candidate_record, force=True)
                    if self.manager.get_record(name) is candidate_record or forced is None:
                        errors.append(f"无法移除失败的新版本: {cleanup_error or name}")
                    elif cleanup_error is not None:
                        errors.append(f"新版本清理失败并已强制移除: {cleanup_error}")
                elif removed is None and current is not None:
                    errors.append(f"清理新版本时插件已被并发替换: {name}")
        elif current is not None:
            errors.append(f"清理新版本时插件已被并发替换: {name}")

        if self.manager.get_record(name) is None:
            if self._loaded_modules.get(name) == candidate_modules:
                self._loaded_modules.pop(name, None)
                self._loaded_paths.pop(name, None)
            self.loader.clear_module_cache(candidate_modules)
        return "; ".join(errors) if errors else None

    async def _restore_old_generation(
        self,
        name: str,
        *,
        old_record: Any,
        old_state: PluginState,
        old_error: Exception | None,
        old_stop_failed: bool,
        old_modules: tuple[str, ...],
        old_path: Path,
    ) -> str | None:
        if self.manager.get_record(name) is not None:
            return f"旧版本名称已被占用: {name}"
        try:
            self.manager.register(old_record.plugin, old_record.context)
        except Exception as exc:
            self._loaded_modules.pop(name, None)
            self._loaded_paths.pop(name, None)
            self._prune_operation_state(name, old_path)
            self.loader.clear_module_cache(old_modules)
            return f"旧版本重新注册失败: {exc}"

        self._loaded_modules[name] = old_modules
        self._loaded_paths[name] = old_path
        restored = self.manager.get_record(name)
        if restored is None:
            self._clear_plugin_tracking(name, path=old_path, modules=old_modules)
            return f"旧版本重新注册后记录丢失: {name}"

        try:
            if old_state is PluginState.RUNNING:
                await self.manager.load_plugin(name)
                if restored.state is PluginState.LOADED and restored.error is None:
                    await self.manager.start_plugin(name)
                if restored.state is not PluginState.RUNNING or restored.error is not None:
                    return f"旧版本重新启动失败: {restored.error or restored.state.value}"
            elif old_state is PluginState.LOADED:
                await self.manager.load_plugin(name)
                if restored.state is not PluginState.LOADED or restored.error is not None:
                    return f"旧版本重新加载失败: {restored.error or restored.state.value}"
            else:
                restored.state = old_state
                restored.error = old_error
                restored.stop_failed = old_stop_failed
        except Exception as exc:
            return f"旧版本生命周期恢复失败: {exc}"
        return None

    def _failed_reload_result(
        self,
        name: str,
        *,
        path: Path,
        error: str,
        rollback_error: str | None,
    ) -> PluginOperationResult:
        detail = f"插件新版本激活失败: {error}"
        if rollback_error is None:
            detail = f"{detail}; 已恢复旧版本"
        else:
            detail = f"{detail}; 旧版本回滚失败: {rollback_error}"
        return PluginOperationResult(
            ok=False,
            name=name,
            state=self._state_value(name),
            error=detail,
            path=path,
        )

    async def reload_all(
        self,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> list[PluginOperationResult]:
        discovered = self.discover_all()
        initial_names = list(self.manager.names())
        present_names: set[str] = set()
        disabled_names = self._disabled_prefix_names()
        enabled: list[DiscoveredPlugin] = []
        outcomes: list[PluginOperationResult] = []

        for item in discovered:
            present_names.add(item.name)
            if isinstance(item, PluginLoadError):
                outcomes.append(
                    PluginOperationResult(
                        ok=False,
                        name=item.name,
                        state=(
                            self._state_value(item.name)
                            if self.manager.get_record(item.name) is not None
                            else PluginState.ERROR.value
                        ),
                        error=_error_text(item.error),
                        path=item.plugin_dir,
                    )
                )
                for loaded_name, loaded_path in self._loaded_paths.items():
                    if loaded_path == item.plugin_dir or (
                        loaded_path.parent == item.plugin_dir and loaded_path.stem == item.name
                    ):
                        present_names.add(loaded_name)
                continue
            if item.enabled:
                enabled.append(item)
            else:
                disabled_names.add(item.name)

        present_names.update(disabled_names)
        handled: set[str] = set()
        for name in initial_names:
            if name not in disabled_names and name in present_names:
                continue
            handled.add(name)
            outcomes.append(await self.unload_plugin(name))

        for item in enabled:
            if item.name in handled:
                continue
            handled.add(item.name)
            outcomes.append(
                await self.reload_plugin_result(
                    item.name,
                    start=start,
                    auto_install_dependencies=auto_install_dependencies,
                )
            )

        for outcome in outcomes:
            if not outcome.ok:
                self.logger.error(f"插件批量重载失败 ({outcome.name}): {outcome.error}")
        return outcomes

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
                        error=_error_text(result.error),
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
                    error=_error_text(result.error) if result.error is not None else None,
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
                    error=_error_text(record.error) if record is not None and record.error is not None else None,
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
            unload_result = await self._unload_plugin_locked(loaded.name)
            if not unload_result.ok:
                self.loader.clear_module_cache(loaded.module_names)
                return unload_result

        if not self._register(loaded):
            return PluginOperationResult(
                ok=False,
                name=loaded.name,
                state=PluginState.ERROR.value,
                error=f"插件注册失败: {loaded.name}",
                path=self._path_for_loaded(loaded),
            )

        await self.manager.load_plugin(loaded.name)
        loaded_result = self._operation_result_from_record(
            loaded.name,
            path=self._path_for_loaded(loaded),
            expected_states={PluginState.LOADED},
        )
        if not loaded_result.ok or not start:
            return loaded_result
        await self.manager.start_plugin(loaded.name)
        return self._operation_result_from_record(
            loaded.name,
            path=self._path_for_loaded(loaded),
            expected_states={PluginState.RUNNING},
        )

    def _operation_result_from_record(
        self,
        name: str,
        *,
        path: Path | None = None,
        expected_states: set[PluginState] | None = None,
    ) -> PluginOperationResult:
        record = self.manager.get_record(name)
        state = self._state_value(name)
        error = _error_text(record.error) if record is not None and record.error is not None else None
        state_matches = (
            record is not None
            and (expected_states is None or record.state in expected_states)
            and record.state is not PluginState.ERROR
        )
        if record is None:
            error = f"插件操作期间已被移除: {name}"
        elif not state_matches and error is None:
            expected = ", ".join(sorted(item.value for item in expected_states or ()))
            error = (
                f"插件未进入预期状态 ({expected}): {state}"
                if expected
                else f"插件处于失败状态: {state}"
            )
        return PluginOperationResult(
            ok=state_matches and record.error is None,
            name=name,
            state=state,
            error=error,
            path=path,
        )

    async def _remove_manager_record(self, name: str, *, expected: Any, force: bool) -> Any:
        if not force:
            return await self.manager.remove_plugin(name, expected=expected)

        force_remove = getattr(self.manager, "force_remove_plugin", None)
        if callable(force_remove):
            return await self._call_manager_remove(force_remove, name, expected=expected, force=None)

        remove = self.manager.remove_plugin
        try:
            parameters = inspect.signature(remove).parameters.values()
        except (TypeError, ValueError):
            parameters = ()
        accepts_force = any(
            parameter.name == "force" or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
        if accepts_force:
            return await self._call_manager_remove(remove, name, expected=expected, force=True)

        records = getattr(self.manager, "_records", None)
        if isinstance(records, dict) and records.get(name) is expected:
            records.pop(name, None)
            return expected
        return None

    async def _call_manager_remove(
        self,
        method: Any,
        name: str,
        *,
        expected: Any,
        force: bool | None,
    ) -> Any:
        try:
            parameters = inspect.signature(method).parameters.values()
        except (TypeError, ValueError):
            parameters = ()
        accepts_kwargs = any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters)
        parameter_names = {parameter.name for parameter in parameters}
        kwargs: dict[str, Any] = {}
        if "expected" in parameter_names or accepts_kwargs:
            kwargs["expected"] = expected
        if force is not None and ("force" in parameter_names or accepts_kwargs):
            kwargs["force"] = force
        value = method(name, **kwargs)
        if inspect.isawaitable(value):
            value = await value
        if value is None and self.manager.get_record(name) is not expected:
            return expected
        if value is True:
            return expected
        if value is False:
            return None
        return value

    def _clear_plugin_tracking(self, name: str, *, path: Path | None, modules: tuple[str, ...]) -> None:
        if modules:
            self.loader.clear_module_cache(modules)
        if self._loaded_modules.get(name) == modules or self.manager.get_record(name) is None:
            self._loaded_modules.pop(name, None)
        if self._loaded_paths.get(name) == path or self.manager.get_record(name) is None:
            self._loaded_paths.pop(name, None)
        self._prune_operation_state(name, path)
        self._prune_operation_lock(name)

    @asynccontextmanager
    async def _named_operation(self, name: str) -> AsyncIterator[None]:
        async with self._operation_gate:
            lock = self._operation_locks.setdefault(name, ReentrantLock())
        # gate 只在字典操作期间持有，不跨锁等待，避免整运行时头阻塞。
        if not lock.is_owned_by_current_task() and lock.held_by_other_task():
            held = self._held_lock_names()
            if held and name < max(held):
                raise OperationBusy(name)
        try:
            await lock.acquire()
        except BaseException:
            self._prune_operation_lock(name, expected_lock=lock)
            raise
        try:
            yield
        finally:
            lock.release()
            self._prune_operation_lock(name, expected_lock=lock)

    @asynccontextmanager
    async def _path_operation(self, path: Path) -> AsyncIterator[_PathOperation]:
        operation = _PathOperation(self, path)
        async with self._operation_gate:
            operation.resolve_known_name()
            operation.enter()
        try:
            await operation.acquire_known_name()
            yield operation
        finally:
            operation.release()

    def _held_lock_names(self) -> list[str]:
        return [
            held_name
            for held_name, held_lock in self._operation_locks.items()
            if held_lock.is_owned_by_current_task()
        ]

    def _prune_operation_state(self, name: str, path: Path | None) -> None:
        if path is not None and self._operation_paths.get(path) == name:
            self._operation_paths.pop(path, None)
            self._committed_operation_paths.discard(path)
        for stale_path in [p for p, bound in self._operation_paths.items() if bound == name]:
            self._operation_paths.pop(stale_path, None)
            self._committed_operation_paths.discard(stale_path)
        self._prune_operation_lock(name)

    def _prune_operation_lock(
        self,
        name: str,
        *,
        expected_lock: ReentrantLock | None = None,
    ) -> None:
        lock = self._operation_locks.get(name)
        if lock is None:
            return
        if expected_lock is not None and lock is not expected_lock:
            return
        if lock.is_free() and name not in self._operation_paths.values():
            self._operation_locks.pop(name, None)

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

    def _disabled_prefix_names(self) -> set[str]:
        names = {snapshot.name for snapshot in self._disabled_prefix_snapshots(set())}
        if not self.plugin_dir.exists() or not self.plugin_dir.is_dir():
            return names
        for entry in self.plugin_dir.iterdir():
            if not entry.name.startswith("_") or entry.name == "__pycache__":
                continue
            original_name = entry.name[1:]
            if not original_name:
                continue
            original_path = entry.with_name(original_name).resolve()
            for loaded_name, loaded_path in self._loaded_paths.items():
                if loaded_path.resolve() == original_path:
                    names.add(loaded_name)
        return names

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
        try:
            validate_plugin_name(loaded.name)
            plugin_data_dir = self._plugin_data_dir(loaded.name)
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
                data_dir=plugin_data_dir,
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
                markdown_skill_registry=self.skills_registry,
                record_skill_cleanup=lambda cleanup, name=loaded.name: self.manager.record_cleanup(name, cleanup),
                plugin_registry=self.manager.registry_view,
                output=self.output,
                host=tracked_host,
                file_server=self._file_server,
                media_sender=self._media_sender,
                screenshots=self.screenshots,
                plugin_control=self.control,
            )
            self.manager.register(loaded.plugin, context)
            self._loaded_modules[loaded.name] = loaded.module_names
            self._loaded_paths[loaded.name] = self._path_for_loaded(loaded)
            return True
        except Exception as exc:
            self.logger.exception(f"插件注册失败 ({loaded.name}): {exc}")
            # 注册失败的模块不清出 sys.modules 会滞留旧代码，热重载时复用导致修复不生效
            self.loader.clear_module_cache(loaded.module_names)
            return False

    def _plugin_data_dir(self, name: str) -> Path:
        candidate = (self.data_dir / name).resolve()
        try:
            candidate.relative_to(self.data_dir)
        except ValueError as exc:
            raise ValueError(f"插件数据目录越界: {name!r} -> {candidate}") from exc
        if candidate == self.data_dir:
            raise ValueError(f"插件数据目录必须是独立子目录: {name!r}")
        return candidate

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


def _error_text(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup):
        details = "; ".join(_error_text(item) for item in error.exceptions)
        return f"{error.message}: {details}"
    return str(error)


_NO_PATH_BINDING = object()


class _PathOperation:
    def __init__(self, runtime: PluginRuntime, path: Path) -> None:
        self._runtime = runtime
        self._path = path
        self._lock: ReentrantLock | None = None
        self._held_name: str | None = None
        self._known_name: str | None = None
        self._original_binding: str | object = _NO_PATH_BINDING
        self._original_binding_committed = False
        self._bound_name: str | None = None
        self._binding_changed = False
        self._committed = False
        self._entered = False
        self._transition_names: set[str] = set()

    def resolve_known_name(self) -> None:
        """在 gate 内同步解析路径当前绑定的插件名（无锁等待）。"""
        name = self._runtime._operation_paths.get(self._path)
        if name is None:
            name = next(
                (
                    loaded_name
                    for loaded_name, loaded_path in self._runtime._loaded_paths.items()
                    if loaded_path == self._path
                ),
                None,
            )
        self._known_name = name

    def enter(self) -> None:
        self._runtime._operation_path_users[self._path] = (
            self._runtime._operation_path_users.get(self._path, 0) + 1
        )
        self._entered = True

    async def acquire_known_name(self) -> None:
        if self._known_name is not None:
            await self._acquire(self._known_name)

    async def bind(self, name: str) -> None:
        if not self._binding_changed:
            self._original_binding = self._runtime._operation_paths.get(self._path, _NO_PATH_BINDING)
            self._original_binding_committed = self._path in self._runtime._committed_operation_paths
            self._binding_changed = True
        self._bound_name = name
        self._transition_names.add(name)
        self._runtime._operation_paths[self._path] = name
        try:
            await self._acquire(name)
        except BaseException:
            self._rollback_binding()
            self._runtime._prune_operation_lock(name)
            raise

    def commit(self) -> None:
        if self._bound_name is not None:
            self._runtime._operation_paths[self._path] = self._bound_name
            self._runtime._committed_operation_paths.add(self._path)
        self._committed = True

    async def _acquire(self, name: str) -> None:
        if self._held_name == name and self._lock is not None:
            return
        lock = self._runtime._operation_locks.setdefault(name, ReentrantLock())
        if lock.is_owned_by_current_task():
            if self._lock is not None and self._lock is not lock:
                self._release_current_lock()
            await lock.acquire()
            self._lock = lock
            self._held_name = name
            return
        if lock.held_by_other_task():
            held = self._runtime._held_lock_names()
            if held and name < max(held):
                raise OperationBusy(name)
        # 名字变化（如重命名/陈旧映射）时先释放旧锁再取新锁，绝不持有旧锁等待新锁。
        if self._lock is not None:
            self._release_current_lock()
        await lock.acquire()
        self._lock = lock
        self._held_name = name

    def release(self) -> None:
        try:
            if self._lock is not None:
                self._release_current_lock()
            if not self._committed:
                if self._binding_changed:
                    self._rollback_binding()
                else:
                    self._cleanup_uncommitted_reservation()
            for name in self._transition_names:
                self._runtime._prune_operation_lock(name)
        finally:
            self._leave()

    def _release_current_lock(self) -> None:
        lock = self._lock
        name = self._held_name
        if lock is None:
            return
        lock.release()
        self._lock = None
        self._held_name = None
        if name is not None:
            self._transition_names.add(name)
            self._runtime._prune_operation_lock(name, expected_lock=lock)

    def _rollback_binding(self) -> None:
        if not self._binding_changed or self._bound_name is None:
            return
        if self._runtime._operation_paths.get(self._path) != self._bound_name:
            return
        users = self._runtime._operation_path_users.get(self._path, 0)
        if self._original_binding_committed:
            self._runtime._operation_paths[self._path] = str(self._original_binding)
            self._runtime._committed_operation_paths.add(self._path)
        elif users > 1:
            if self._original_binding is not _NO_PATH_BINDING:
                self._runtime._operation_paths[self._path] = str(self._original_binding)
            self._runtime._committed_operation_paths.discard(self._path)
        else:
            self._runtime._operation_paths.pop(self._path, None)
            self._runtime._committed_operation_paths.discard(self._path)

    def _cleanup_uncommitted_reservation(self) -> None:
        if self._path in self._runtime._committed_operation_paths:
            return
        if self._runtime._operation_path_users.get(self._path, 0) > 1:
            return
        if self._runtime._operation_paths.get(self._path) == self._known_name:
            self._runtime._operation_paths.pop(self._path, None)

    def _leave(self) -> None:
        if not self._entered:
            return
        users = self._runtime._operation_path_users.get(self._path, 0)
        if users <= 1:
            self._runtime._operation_path_users.pop(self._path, None)
        else:
            self._runtime._operation_path_users[self._path] = users - 1
        self._entered = False

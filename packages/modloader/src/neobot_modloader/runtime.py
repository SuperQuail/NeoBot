from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import NullOutput, OutputPort
from neobot_contracts.ports.plugin import PluginState
from neobot_contracts.ports.screenshot import ScreenshotPort

from neobot_modloader.config_store import PluginConfigStore
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.dependency import (
    PluginDependency,
    PluginDependencyError,
    parse_dependencies,
    version_satisfies,
)
from neobot_modloader.dependencies import PythonDependencyInstaller
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import TrackedPluginHostFacade
from neobot_modloader.installer import PluginInstaller, PluginUpdateCheck
from neobot_modloader.loading.manifest import (
    read_dependencies,
    read_manifest,
    read_optional_bool,
    read_python_dependencies,
)
from neobot_modloader.loading.models import (
    OFFICIAL_SOURCE,
    THIRD_PARTY_SOURCE,
    DisabledPlugin,
)
from neobot_modloader.loading.ordering import order_discovery_results
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
from neobot_modloader.state import PluginStateStore
from neobot_modloader.version import version_at_least

#: 前置插件处于这些状态才算「就绪」，依赖方才能加载
_READY_STATES = frozenset({PluginState.LOADED, PluginState.RUNNING})


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
        app_commands: Any | None = None,
        dependency_installer: PythonDependencyInstaller | None = None,
        auto_install_dependencies: bool = False,
        builtin_plugin_dirs: Sequence[Path] | None = None,
        state_store: PluginStateStore | None = None,
        installer: PluginInstaller | None = None,
        user_plugins_enabled: bool = True,
        host_version: str | None = None,
    ) -> None:
        self.plugin_dir = plugin_dir.resolve()
        self.data_dir = data_dir.resolve()
        self.user_plugins_enabled = bool(user_plugins_enabled)
        #: 当前 NeoBot 版本，用于校验插件声明的 min_neobot_version（None 跳过检查）
        self.host_version = host_version
        self._official_dirs = tuple(
            Path(path).resolve() for path in (builtin_plugin_dirs or ())
        )
        self._state_store = state_store
        self.installer = installer
        self.adapter = adapter
        self.logger_factory = logger_factory
        self.agent_registry = agent_registry
        self.skills_registry = skills_registry
        self._file_server = file_server
        self._media_sender = media_sender
        self.screenshots = screenshots
        self._app_commands = app_commands
        self.record_ai_reply_block = record_ai_reply_block
        self.output = output or NullOutput()
        self.logger = logger or self._get_logger("modloader.runtime")
        self.hook_bus = hook_bus or PluginHookBus(
            logger=self._get_logger("modloader.hooks"),
            record_ai_reply_block=record_ai_reply_block,
            output=self.output,
        )
        self.host = host
        enabled_resolver = self._resolve_enabled_state if self._state_store is not None else None
        self.loader = loader or FilesystemPluginLoader(
            logger=self._get_logger("modloader.loader"),
            source=THIRD_PARTY_SOURCE,
            enabled_resolver=enabled_resolver,
        )
        self.official_loader = FilesystemPluginLoader(
            logger=self._get_logger("modloader.loader.official"),
            source=OFFICIAL_SOURCE,
            namespace="neobot_builtin_plugins",
            enabled_resolver=enabled_resolver,
        )
        self.manager = manager or DefaultPluginManager(logger=self._get_logger("modloader.manager"))
        self.dependency_installer = dependency_installer or PythonDependencyInstaller(logger=self.logger)
        self.auto_install_dependencies = auto_install_dependencies
        self._loaded_modules: dict[str, tuple[str, ...]] = {}
        self._loaded_paths: dict[str, Path] = {}
        self._loaded_sources: dict[str, str] = {}
        #: 已加载插件解析后的热重载能力（plugin.toml 优先，其次 Plugin() 声明）
        self._loaded_flags: dict[str, tuple[bool, bool]] = {}
        #: 插件打包默认配置（plugin.toml 的 [config]），作为插件数据配置的兜底
        self._manifest_configs: dict[str, dict[str, Any]] = {}
        self._operation_gate = asyncio.Lock()
        self._operation_locks: dict[str, ReentrantLock] = {}
        self._operation_paths: dict[Path, str] = {}
        self._operation_path_users: dict[Path, int] = {}
        self._committed_operation_paths: set[Path] = set()
        self._scan_guard = threading.RLock()
        #: 因前置插件不满足而被自动禁用的插件: 插件名 -> (前置插件名, 原因)
        #: 前置插件恢复后运行时会自动把这些插件重新拉起来。
        self._auto_disabled: dict[str, tuple[str, str]] = {}
        #: 未注入 PluginStateStore 时的进程内启停记录（装配期测试/嵌入式用法）。
        #: 没有它，set_enabled 会「报告成功但什么都没变」，面板上的启停按钮看起来失灵。
        self._memory_enabled: dict[str, bool] = {}
        self.control = _RuntimePluginControlFacade(self)

    def _resolve_enabled_state(self, name: str, default: bool) -> bool:
        store = self._state_store
        if store is None:
            return self._memory_enabled.get(name, default)
        return store.is_enabled(name, default)

    def _persist_enabled_state(self, name: str, enabled: bool) -> None:
        """记录启停状态：有持久化存储就落盘，否则退化为进程内记录。"""
        if self._state_store is not None:
            self._state_store.set_enabled(name, enabled)
            return
        self._memory_enabled[name] = bool(enabled)

    @property
    def builtin_plugin_dirs(self) -> tuple[Path, ...]:
        return self._official_dirs

    @property
    def state_store(self) -> PluginStateStore | None:
        return self._state_store

    def scan_dirs(self) -> list[tuple[Path, FilesystemPluginLoader]]:
        """按优先级返回 (目录, 加载器)：官方插件目录在前，第三方插件目录在后。"""
        directories: list[tuple[Path, FilesystemPluginLoader]] = [
            (path, self.official_loader) for path in self._official_dirs
        ]
        if self.user_plugins_enabled:
            directories.append((self.plugin_dir, self.loader))
        return directories

    def _host_version_error(self, name: str, minimum: str | None) -> str | None:
        """插件声明的 min_neobot_version 高于当前版本时返回错误文本。

        这个字段以前只被解析、随插件元数据一路传递，从来没有被比较过：
        插件写着 ``min_neobot_version = "9.0"`` 也会照常加载，然后在调用
        运行时不存在的 API 时炸掉。
        """
        if not minimum:
            return None
        satisfied = version_at_least(self.host_version, minimum)
        if satisfied is None:
            self.logger.warning(
                f"无法比较 NeoBot 版本，已跳过最低版本检查 ({name}): "
                f"要求 {minimum}, 当前 {self.host_version or '未知'}"
            )
            return None
        if satisfied:
            return None
        return f"插件要求 NeoBot >= {minimum}，当前为 {self.host_version or '未知'}"

    def discover_all(self) -> list[DiscoveredPlugin | PluginLoadError]:
        results: list[DiscoveredPlugin | PluginLoadError] = []
        official_names: set[str] = set()
        for directory, loader in self.scan_dirs():
            for result in loader.discover_all(directory):
                if isinstance(result, PluginLoadError):
                    results.append(result)
                    continue
                incompatible = (
                    self._host_version_error(result.name, result.min_neobot_version)
                    if result.enabled
                    else None
                )
                if incompatible is not None:
                    # 不做成 PluginLoadError：面板的「停用 / 重载 / 卸载」与
                    # plugin_source 都依赖 discover 结果，把它替换成错误条目会让
                    # 这些操作报「插件未找到」，来源也被误判成第三方。这里保留
                    # 条目（面板仍能看到、能停用/卸载），真实原因记日志；加载路径
                    # （load_all / 面板安装）依旧会拒绝。
                    self.logger.error(f"插件不兼容当前 NeoBot 版本: {incompatible}")
                if result.source == OFFICIAL_SOURCE:
                    official_names.add(result.name)
                elif result.name in official_names:
                    self.logger.warning(
                        f"第三方插件与官方插件同名，已忽略第三方副本: {result.name}"
                    )
                    continue
                results.append(result)
        # 跨目录（官方 / 第三方）统一再做一次依赖解析：官方插件与第三方插件可以互相
        # 依赖，依赖未满足的插件在这里被标注「自动禁用」原因，供面板与加载路径复用。
        return order_discovery_results(results)

    def _disabled_plugin_names(self) -> set[str]:
        """当前被用户停用的插件名（用于区分「依赖缺失」与「前置插件已停用」）。

        只读启停状态存储，不做目录扫描：这里处在加载/启动热路径上，扫描目录
        既昂贵又会依赖 loader 的 discover 能力。
        """
        store = self._state_store
        if store is None:
            return set()
        return {
            name
            for name, entry in store.entries().items()
            if entry.enabled is False
        }

    def _dependency_issues(
        self,
        name: str,
        dependencies: Sequence[str],
        *,
        disabled_names: set[str] | None = None,
    ) -> list[str]:
        """检查某个插件声明的依赖当前是否满足，返回问题清单（空表示满足）。"""
        issues: list[str] = []
        try:
            parsed = parse_dependencies(dependencies)
        except (TypeError, ValueError) as exc:
            return [f"依赖声明非法: {exc}"]
        if disabled_names is None:
            disabled_names = self._disabled_plugin_names()
        for dependency in parsed:
            record = self.manager.get_record(dependency.name)
            if record is None:
                if dependency.name in disabled_names:
                    issues.append(
                        f"前置插件不可用: {dependency.describe()}（插件已停用）"
                    )
                else:
                    issues.append(f"缺少前置插件: {dependency.describe()}")
                continue
            if record.state not in _READY_STATES:
                issues.append(
                    f"前置插件未就绪: {dependency.describe()}（{record.state.value}）"
                )
                continue
            version = str(getattr(record.plugin, "version", "") or "")
            if dependency.matches(version) is False:
                issues.append(
                    f"前置插件版本不满足: 需要 {dependency.describe()}，当前 {version}"
                )
        return issues

    def _dependency_presence_issues(
        self, dependencies: Sequence[str]
    ) -> list[str]:
        """注册阶段只检查前置插件「在不在」，不要求它已经加载完成。

        load_all() 只做扫描与注册，各插件的 on_load 发生在之后的
        load_registered()：此时要求前置插件 READY 会把所有依赖插件误判成
        自动禁用。
        """
        issues: list[str] = []
        try:
            parsed = parse_dependencies(dependencies)
        except (TypeError, ValueError) as exc:
            return [f"依赖声明非法: {exc}"]
        disabled_names = self._disabled_plugin_names()
        for dependency in parsed:
            if self.manager.get_record(dependency.name) is not None:
                continue
            if dependency.name in disabled_names:
                issues.append(f"前置插件不可用: {dependency.describe()}（插件已停用）")
            else:
                issues.append(f"缺少前置插件: {dependency.describe()}")
        return issues

    @staticmethod
    def _primary_dependency(dependencies: Sequence[str]) -> str:
        try:
            parsed = parse_dependencies(dependencies)
        except (TypeError, ValueError):
            return ""
        return parsed[0].name if parsed else ""

    def _remember_auto_disabled(
        self, name: str, dependencies: Sequence[str], reason: str
    ) -> None:
        self._auto_disabled[name] = (self._primary_dependency(dependencies), reason)

    def dependency_report(self, name: str) -> dict[str, Any]:
        """插件依赖现状（供面板展示：声明、问题、反向依赖）。"""
        registry = self.manager.registry_view
        record = self.manager.get_record(name)
        raw: Sequence[str] = ()
        if record is not None:
            raw = tuple(getattr(record.plugin, "dependencies", ()) or ())
        else:
            try:
                for item in self.discover_all():
                    if isinstance(item, DiscoveredPlugin) and item.name == name:
                        raw = item.dependencies
                        break
            except Exception:
                raw = ()
        auto = self._auto_disabled.get(name)
        return {
            "name": name,
            "dependencies": [str(item) for item in raw],
            "issues": self._dependency_issues(name, raw) if record is not None else [],
            "dependents": registry.dependents_of(name),
            "auto_disabled": auto is not None,
            "disabled_reason": auto[1] if auto else None,
        }

    def load_all(self, *, auto_install_dependencies: bool | None = None) -> None:
        if self.user_plugins_enabled:
            self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for path in self._official_dirs:
            if not path.exists():
                self.logger.warning(f"官方插件目录不存在: {path}")
        self.logger.info(f"插件目录: {self.plugin_dir}")

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        if install:
            self._confirm_and_install_missing_dependencies()

        results = []
        official_names: set[str] = set()
        for directory, loader in self.scan_dirs():
            for result in loader.load_all(directory):
                if isinstance(result, LoadedPlugin) and result.source == OFFICIAL_SOURCE:
                    official_names.add(result.name)
                results.append(result)
        deduped = []
        for result in results:
            if (
                isinstance(result, LoadedPlugin)
                and result.source != OFFICIAL_SOURCE
                and result.name in official_names
            ):
                self.logger.warning(
                    f"第三方插件与官方插件同名，已忽略第三方副本: {result.name}"
                )
                self.loader.clear_module_cache(result.module_names)
                continue
            deduped.append(result)
        results = deduped
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
                if isinstance(result, DisabledPlugin):
                    # 前置插件未满足：自动禁用该插件，但不影响程序启动
                    self._remember_auto_disabled(
                        result.name, result.dependencies, result.reason
                    )
                    self.logger.warning(
                        f"插件依赖未满足，已自动禁用 ({result.name}): {result.reason}"
                    )
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
                incompatible = self._host_version_error(
                    result.name, result.min_neobot_version
                )
                if incompatible is not None:
                    error_count += 1
                    self.logger.error(f"插件加载跳过 ({result.name}): {incompatible}")
                    self.loader.clear_module_cache(result.module_names)
                    continue
                issues = self._dependency_presence_issues(result.dependencies)
                if issues:
                    # 跨目录依赖（例如官方插件依赖第三方插件）由这里兜底：同样只自动
                    # 禁用，不打断启动。
                    reason = "; ".join(issues)
                    self._remember_auto_disabled(result.name, result.dependencies, reason)
                    self.logger.warning(
                        f"插件依赖未满足，已自动禁用 ({result.name}): {reason}"
                    )
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
        # 前置插件卸载后依赖它的插件必然失效：先联动停掉，避免留下半死状态
        await self._cascade_stop_dependents(name, reason=f"前置插件已卸载: {name}")
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
        issues = self._dependency_issues(
            name, tuple(getattr(record.plugin, "dependencies", ()) or ())
        )
        if issues:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=record.state.value,
                error="; ".join(issues),
                path=path,
            )
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
        await self._cascade_stop_dependents(name, reason=f"前置插件已停止: {name}")
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

    # ------------------------------------------------------------------
    # 依赖联动
    # ------------------------------------------------------------------

    async def _cascade_stop_dependents(
        self, name: str, *, reason: str
    ) -> list[PluginOperationResult]:
        """前置插件停用 / 卸载 / 重载前，联动停掉依赖它的插件。

        被联动停用的插件登记在 _auto_disabled 里：前置插件恢复后由
        _cascade_restore_dependents 自动拉起，用户不需要手动重新启用。
        """
        outcomes: list[PluginOperationResult] = []
        registry = self.manager.registry_view
        for dependent in registry.dependents_of(name, transitive=True):
            record = self.manager.get_record(dependent)
            if record is None:
                continue
            if (
                record.state in {PluginState.UNLOADED, PluginState.STOPPED}
                and record.error is None
            ):
                continue
            self._remember_auto_disabled(
                dependent,
                tuple(getattr(record.plugin, "dependencies", ()) or ()),
                reason,
            )
            self.logger.info(f"前置插件 {name} 不可用，联动停用依赖插件: {dependent}")
            outcomes.append(await self.unload_plugin(dependent))
        return outcomes

    async def _cascade_restore_dependents(self, name: str) -> list[PluginOperationResult]:
        """前置插件恢复后，把因它而自动禁用的插件重新加载起来。"""
        outcomes: list[PluginOperationResult] = []
        pending = [
            dependent
            for dependent, (prerequisite, _reason) in list(self._auto_disabled.items())
            if prerequisite == name
        ]
        for dependent in pending:
            if self.manager.get_record(dependent) is not None:
                self._auto_disabled.pop(dependent, None)
                continue
            path = self._find_plugin_path(dependent)
            if path is None:
                self._auto_disabled.pop(dependent, None)
                continue
            self.logger.info(f"前置插件 {name} 已就绪，自动恢复依赖插件: {dependent}")
            outcome = await self.load_plugin_path(
                path, start=True, auto_install_dependencies=False
            )
            if outcome.ok:
                self._auto_disabled.pop(dependent, None)
            else:
                outcomes.append(outcome)
        return outcomes

    async def reload_plugin_result(
        self,
        name: str,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        # 重载会短暂摘掉插件：先把依赖它的插件联动停掉，重载成功后再拉回来
        await self._cascade_stop_dependents(name, reason=f"前置插件正在重载: {name}")
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
        if result.ok:
            await self._cascade_restore_dependents(name)
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

        flags = self._loaded_flags.get(name)
        if flags is not None and not flags[0]:
            return PluginOperationResult(
                ok=False,
                name=name,
                state=self._state_value(name),
                error="该插件声明不支持热重载，请重启 NeoBot",
                requires_restart=True,
                path=plugin_path,
            )

        old_record = self.manager.get_record(name)
        old_modules = self._loaded_modules.get(name, ())
        old_path = self._loaded_paths.get(name) or plugin_path
        old_state = old_record.state if old_record is not None else PluginState.UNLOADED
        old_error = old_record.error if old_record is not None else None
        old_stop_failed = bool(getattr(old_record, "stop_failed", False))

        install = self.auto_install_dependencies if auto_install_dependencies is None else auto_install_dependencies
        if install:
            discovered = self.discover_all()
            missing = []
            for item in discovered:
                if isinstance(item, DiscoveredPlugin) and item.name == name:
                    missing.extend(item.missing_python_dependencies)
            if missing:
                # 热重载发生在运行期：必须 await（内部走线程），否则等待用户
                # 输入与 pip 子进程会阻塞事件循环
                await self.dependency_installer.confirm_and_install(missing)

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
        discovered = self.discover_all()
        disabled_names = {
            item.name
            for item in discovered
            if isinstance(item, DiscoveredPlugin) and not item.enabled
        }
        registry = self.manager.registry_view

        for result in discovered:
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
                        source=self._source_for_path(path),
                    )
                )
                seen_names.add(result.name)
                seen_paths.add(path.resolve())
                continue

            path = self._path_for_discovered(result)
            state = self._state_value(result.name)
            if state == PluginState.UNLOADED.value and result.missing_python_dependencies:
                state = PluginState.ERROR.value
            loaded_flags = self._loaded_flags.get(result.name)
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
                    source=result.source,
                    repo=result.repo,
                    branch=result.branch,
                    homepage=result.homepage,
                    license=result.license,
                    tags=result.tags,
                    hot_reload=(
                        loaded_flags[0] if loaded_flags else result.hot_reload
                    ),
                    config_hot_reload=(
                        loaded_flags[1] if loaded_flags else result.config_hot_reload
                    ),
                    disabled_reason=(
                        result.disabled_reason
                        or self._auto_disabled.get(result.name, ("", None))[1]
                    ),
                    auto_disabled=bool(
                        result.auto_disabled or result.name in self._auto_disabled
                    ),
                    dependency_issues=tuple(
                        self._dependency_issues(
                            result.name,
                            result.dependencies,
                            disabled_names=disabled_names,
                        )
                    ),
                    dependents=tuple(registry.dependents_of(result.name)),
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
                    source=self._loaded_sources.get(name, THIRD_PARTY_SOURCE),
                    hot_reload=bool(getattr(plugin, "hot_reload", True)),
                    config_hot_reload=bool(getattr(plugin, "config_hot_reload", True)),
                    dependency_issues=tuple(
                        self._dependency_issues(
                            name,
                            tuple(getattr(plugin, "dependencies", ()) or ()),
                            disabled_names=disabled_names,
                        )
                    ),
                    dependents=tuple(registry.dependents_of(name)),
                )
            )

        return sorted(snapshots, key=lambda item: item.name.lower())

    def plugin_config_model(self, name: str) -> Any | None:
        """返回插件声明的配置模型（pydantic BaseModel），未声明时返回 None。

        面板用它为官方插件生成表单并做保存前校验。
        """
        record = self.manager.get_record(name)
        plugin = record.plugin if record is not None else None
        model = getattr(plugin, "config_model", None)
        return model if isinstance(model, type) else None

    # ------------------------------------------------------------------
    # 插件下载代理
    # ------------------------------------------------------------------

    def installer_proxy(self) -> dict[str, Any]:
        """当前插件下载代理设置（安装器不可用时返回空字典）。"""
        installer = self.installer
        if installer is None:
            return {}
        return installer.proxy.to_dict()

    def set_installer_proxy(
        self,
        *,
        mode: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        """切换插件下载代理；下一次下载立即生效。"""
        installer = self.installer
        if installer is None:
            raise RuntimeError("插件安装器不可用")
        return installer.set_proxy(mode=mode, host=host, port=port).to_dict()

    async def set_enabled(self, name: str, enabled: bool) -> PluginOperationResult:
        """启用 / 停用插件并持久化状态；官方插件与第三方插件使用同一套机制。"""
        path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        if path is None:
            return PluginOperationResult(ok=False, name=name, error=f"插件未找到: {name}")
        if not enabled:
            record = self.manager.get_record(name)
            if record is not None:
                result = await self.unload_plugin(name)
                if not result.ok:
                    return result
            self._persist_enabled_state(name, False)
            self._loaded_sources.pop(name, None)
            self._loaded_flags.pop(name, None)
            return PluginOperationResult(
                ok=True,
                name=name,
                state=PluginState.UNLOADED.value,
                path=path,
            )
        self._persist_enabled_state(name, True)
        outcome = await self.load_plugin_path(path, start=True)
        if outcome.ok:
            # 前置插件回来了：把之前因它而自动禁用的插件一并拉起来
            await self._cascade_restore_dependents(name)
        return outcome

    async def install_plugin(
        self,
        repo: str,
        *,
        branch: str | None = None,
        replace: bool = False,
        start: bool = True,
    ) -> PluginOperationResult:
        if self.installer is None:
            return PluginOperationResult(ok=False, name="", error="插件安装器未配置")
        result = await self.installer.install(repo, branch=branch, replace=replace)
        if not result.ok:
            return PluginOperationResult(
                ok=False, name=result.name, error=result.error, path=result.path
            )
        self._persist_enabled_state(result.name, True)
        if result.path is None:
            return PluginOperationResult(ok=True, name=result.name)
        outcome = await self.load_plugin_path(result.path, start=start)
        if outcome.ok:
            return PluginOperationResult(
                ok=True,
                name=outcome.name,
                state=outcome.state,
                path=outcome.path,
            )
        return PluginOperationResult(
            ok=False,
            name=result.name,
            state=outcome.state,
            error=f"{result.message}，但加载失败: {outcome.error or outcome.state}",
            path=result.path,
        )

    async def uninstall_plugin(self, name: str) -> PluginOperationResult:
        if self.installer is None:
            return PluginOperationResult(ok=False, name=name, error="插件安装器未配置")
        if self.is_official(name):
            return PluginOperationResult(
                ok=False, name=name, error=f"官方插件随本体分发，不能卸载: {name}"
            )
        path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        if self.manager.get_record(name) is not None:
            stopped = await self.unload_plugin(name)
            if not stopped.ok:
                return stopped
        result = await self.installer.uninstall(name)
        if not result.ok:
            return PluginOperationResult(ok=False, name=name, error=result.error, path=path)
        if self._state_store is not None:
            self._state_store.forget(name)
        self._memory_enabled.pop(name, None)
        self._loaded_sources.pop(name, None)
        self._loaded_paths.pop(name, None)
        return PluginOperationResult(
            ok=True,
            name=name,
            state=PluginState.UNLOADED.value,
            error=result.message or None,
            path=result.path,
        )

    async def check_plugin_update(self, name: str) -> PluginUpdateCheck:
        snapshot = self._snapshot_for(name)
        if snapshot is None:
            return PluginUpdateCheck(
                name=name, current_version="", status="error", error=f"插件未找到: {name}"
            )
        if snapshot.official:
            return PluginUpdateCheck(
                name=name,
                current_version=snapshot.version,
                status="unknown",
                error="官方插件随本体更新",
            )
        if self.installer is None:
            return PluginUpdateCheck(
                name=name,
                current_version=snapshot.version,
                status="error",
                error="插件安装器未配置",
            )
        return await self.installer.check_update(
            name,
            repo=snapshot.repo,
            branch=snapshot.branch,
            current_version=snapshot.version,
        )

    async def check_plugin_updates(self) -> list[PluginUpdateCheck]:
        checks: list[PluginUpdateCheck] = []
        for snapshot in self.snapshot_plugins():
            if snapshot.official or not snapshot.repo:
                continue
            checks.append(await self.check_plugin_update(snapshot.name))
        return checks

    def _snapshot_for(self, name: str) -> PluginSnapshot | None:
        for snapshot in self.snapshot_plugins():
            if snapshot.name == name:
                return snapshot
        return None

    def _source_for_path(self, path: Path | None) -> str:
        if path is None:
            return THIRD_PARTY_SOURCE
        resolved = path.resolve()
        for root in self._official_dirs:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return OFFICIAL_SOURCE
        return THIRD_PARTY_SOURCE

    def _confirm_and_install_missing_dependencies(self) -> None:
        missing: list[str] = []
        for result in self.discover_all():
            if isinstance(result, DiscoveredPlugin) and result.enabled:
                missing.extend(result.missing_python_dependencies)
        if missing:
            # 启动装配期的同步入口：无交互终端时内部直接跳过，不再抛 EOFError
            self.dependency_installer.confirm_and_install_sync(missing)

    async def _activate_loaded_plugin(
        self,
        loaded: LoadedPlugin,
        *,
        start: bool,
        auto_install_dependencies: bool,
    ) -> PluginOperationResult:
        missing = list(missing_python_dependencies(loaded.python_dependencies))
        if missing and auto_install_dependencies:
            # 面板「安装/重载插件」会走到这里，必须 await 线程化的安装流程
            await self.dependency_installer.confirm_and_install(missing)
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

        incompatible = self._host_version_error(loaded.name, loaded.min_neobot_version)
        if incompatible is not None:
            self.logger.error(f"插件加载失败 ({loaded.name}): {incompatible}")
            self.loader.clear_module_cache(loaded.module_names)
            return PluginOperationResult(
                ok=False,
                name=loaded.name,
                state=PluginState.ERROR.value,
                error=incompatible,
                path=self._path_for_loaded(loaded),
            )

        issues = self._dependency_issues(loaded.name, loaded.dependencies)
        if issues:
            # 前置插件未满足：自动禁用（不是错误），前置插件就绪后可再启用
            reason = "; ".join(issues)
            self._remember_auto_disabled(loaded.name, loaded.dependencies, reason)
            self.logger.warning(f"插件依赖未满足，已自动禁用 ({loaded.name}): {reason}")
            self.loader.clear_module_cache(loaded.module_names)
            return PluginOperationResult(
                ok=False,
                name=loaded.name,
                state=PluginState.UNLOADED.value,
                error=reason,
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
            self._loaded_sources.pop(name, None)
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
        resolved = path.resolve()
        roots = [self.plugin_dir, *self._official_dirs]
        for root in roots:
            try:
                resolved.relative_to(root)
            except ValueError:
                continue
            return True
        return False

    def plugin_source(self, name: str) -> str:
        """插件来源；未加载的插件通过发现结果推断。"""
        source = self._loaded_sources.get(name)
        if source is not None:
            return source
        for result in self.discover_all():
            if isinstance(result, DiscoveredPlugin) and result.name == name:
                return result.source
        return THIRD_PARTY_SOURCE

    def is_official(self, name: str) -> bool:
        return self.plugin_source(name) == OFFICIAL_SOURCE

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
            hot_reload=bool(read_optional_bool(metadata, "hot_reload", True)),
            config_hot_reload=bool(read_optional_bool(metadata, "config_hot_reload", True)),
        )

    def plugin_config_store(self, name: str) -> PluginConfigStore | None:
        """插件配置存储：配置存于插件数据目录，默认值来自 plugin.toml 的 [config]。

        与启停状态无关，因此插件被停用（未加载）时依然能读出配置。
        """
        if not name:
            return None
        try:
            data_dir = self._plugin_data_dir(name)
        except ValueError as exc:
            self.logger.warning(f"插件数据目录不可用 ({name}): {exc}")
            return None
        return PluginConfigStore(
            data_dir,
            defaults=self._manifest_config(name),
            logger=self._get_logger(f"plugin.{name}.config"),
        )

    def plugin_config_path(self, name: str) -> Path | None:
        store = self.plugin_config_store(name)
        return store.path if store is not None else None

    def plugin_manifest_path(self, name: str) -> Path | None:
        """插件自带 plugin.toml 的路径（面板用它读取 [config] 的注释作为字段说明）。

        插件未加载时回落到目录扫描；单文件插件没有 manifest，返回 None。
        """
        path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        if path is None:
            return None
        return self._manifest_path_for(path)

    def plugin_config_defaults(self, name: str) -> dict[str, Any]:
        store = self.plugin_config_store(name)
        return store.defaults if store is not None else {}

    def plugin_config_values(self, name: str) -> dict[str, Any]:
        """插件当前生效的配置（打包默认值 + 插件数据目录里保存的值）。"""
        store = self.plugin_config_store(name)
        return store.read() if store is not None else {}

    def _manifest_config(self, name: str) -> dict[str, Any]:
        """plugin.toml 的 [config]：插件打包默认值（插件未加载时回落到磁盘读取）。"""
        cached = self._manifest_configs.get(name)
        if cached is not None:
            return cached
        config: dict[str, Any] = {}
        path = self._loaded_paths.get(name) or self._find_plugin_path(name)
        manifest = self._manifest_path_for(path) if path is not None else None
        if manifest is not None:
            try:
                metadata = read_manifest(manifest)
            except Exception as exc:
                self.logger.warning(f"读取插件默认配置失败 ({name}): {exc}")
                metadata = {}
            raw = metadata.get("config")
            if isinstance(raw, Mapping):
                config = {str(key): value for key, value in raw.items()}
        self._manifest_configs[name] = config
        return config

    @staticmethod
    def _manifest_path_for(path: Path) -> Path | None:
        if path.is_dir():
            candidate = path / "plugin.toml"
            return candidate if candidate.is_file() else None
        candidate = path.parent / "plugin.toml"
        return candidate if candidate.is_file() else None

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
            self._manifest_configs.setdefault(
                loaded.name, {str(key): value for key, value in (loaded.config or {}).items()}
            )
            store = self.plugin_config_store(loaded.name)
            context = RuntimePluginContext(
                plugin_name=loaded.name,
                plugin_dir=loaded.plugin_dir,
                data_dir=plugin_data_dir,
                config=store.read() if store is not None else dict(loaded.config or {}),
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
                app_commands=self._app_commands,
                plugin_control=self.control,
                source=loaded.source,
            )
            self.manager.register(loaded.plugin, context)
            self._loaded_modules[loaded.name] = loaded.module_names
            self._loaded_paths[loaded.name] = self._path_for_loaded(loaded)
            self._loaded_sources[loaded.name] = loaded.source
            self._loaded_flags[loaded.name] = (
                bool(getattr(loaded, "hot_reload", True)),
                bool(getattr(loaded, "config_hot_reload", True)),
            )
            # 注册成功说明依赖已满足，清掉自动禁用记录
            self._auto_disabled.pop(loaded.name, None)
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

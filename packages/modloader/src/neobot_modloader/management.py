from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neobot_modloader.loading.models import OFFICIAL_SOURCE, THIRD_PARTY_SOURCE


@dataclass(frozen=True, slots=True)
class PluginOperationResult:
    ok: bool
    name: str
    state: str | None = None
    error: str | None = None
    requires_restart: bool = False
    path: Path | None = None


@dataclass(frozen=True, slots=True)
class PluginSnapshot:
    name: str
    version: str = "0.1.0"
    state: str = "unloaded"
    enabled: bool = True
    path: Path | None = None
    kind: str = "unknown"
    error: str | None = None
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    python_dependencies: tuple[str, ...] = ()
    missing_python_dependencies: tuple[str, ...] = ()
    source: str = THIRD_PARTY_SOURCE
    repo: str = ""
    branch: str = ""
    homepage: str = ""
    license: str = ""
    tags: tuple[str, ...] = ()
    #: 插件本体是否支持不重启进程的重载
    hot_reload: bool = True
    #: 插件配置改动是否支持不重启进程生效
    config_hot_reload: bool = True
    #: 依赖未满足时自动禁用的原因（None 表示依赖正常）
    disabled_reason: str | None = None
    #: 是否因前置插件未满足而被自动禁用（区别于用户在面板里手动停用）
    auto_disabled: bool = False
    #: 当前未满足的依赖说明（缺失 / 未就绪 / 版本不符）
    dependency_issues: tuple[str, ...] = ()
    #: 依赖本插件的其他插件（停用 / 卸载时会被联动处理）
    dependents: tuple[str, ...] = ()
    #: 插件配置校验告警：非空表示部分已存值非法、已回落默认值运行
    config_error: str | None = None

    @property
    def official(self) -> bool:
        return self.source == OFFICIAL_SOURCE

    @property
    def manageable(self) -> bool:
        """官方插件不可安装 / 更新 / 卸载，只能启停与重载。"""
        return not self.official

    @property
    def hot_reloadable(self) -> bool:
        """可热重载 = 插件自己声明支持 + 运行时能定位插件代码。"""
        return bool(self.hot_reload) and self.kind != "unknown"


class PluginControlFacade:
    """向插件暴露的窄化运行时管理门面。"""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def load_path(
        self,
        path: Path,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        return await self._runtime.load_plugin_path(
            path,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )

    async def unload(self, name: str) -> PluginOperationResult:
        return await self._runtime.unload_plugin(name)

    async def reload(
        self,
        name: str,
        *,
        start: bool = True,
        auto_install_dependencies: bool | None = None,
    ) -> PluginOperationResult:
        return await self._runtime.reload_plugin_result(
            name,
            start=start,
            auto_install_dependencies=auto_install_dependencies,
        )

    async def start(self, name: str) -> PluginOperationResult:
        return await self._runtime.start_plugin(name)

    async def stop(self, name: str) -> PluginOperationResult:
        return await self._runtime.stop_plugin(name)

    async def set_enabled(self, name: str, enabled: bool) -> PluginOperationResult:
        """启用 / 停用插件并持久化状态（官方与第三方插件统一处理）。"""
        return await self._runtime.set_enabled(name, enabled)

    async def install(
        self,
        repo: str,
        *,
        branch: str | None = None,
        replace: bool = False,
        start: bool = True,
    ) -> PluginOperationResult:
        return await self._runtime.install_plugin(
            repo, branch=branch, replace=replace, start=start
        )

    async def uninstall(self, name: str) -> PluginOperationResult:
        return await self._runtime.uninstall_plugin(name)

    async def check_update(self, name: str) -> Any:
        return await self._runtime.check_plugin_update(name)

    async def check_updates(self) -> list[Any]:
        return await self._runtime.check_plugin_updates()

    def snapshot(self) -> list[PluginSnapshot]:
        return self._runtime.snapshot_plugins()

    def get(self, name: str) -> PluginSnapshot | None:
        for snapshot in self.snapshot_plugins():
            if snapshot.name == name:
                return snapshot
        return None

    def snapshot_plugins(self) -> list[PluginSnapshot]:
        return self._runtime.snapshot_plugins()

    @property
    def installer_available(self) -> bool:
        return getattr(self._runtime, "installer", None) is not None

    def dependencies(self, name: str) -> dict[str, Any]:
        """插件依赖现状：声明、未满足项、反向依赖、自动禁用原因。"""
        reporter = getattr(self._runtime, "dependency_report", None)
        if not callable(reporter):
            return {}
        return dict(reporter(name))

    def config_model(self, name: str) -> Any | None:
        """插件声明的配置模型（pydantic BaseModel），未声明时返回 None。"""
        getter = getattr(self._runtime, "plugin_config_model", None)
        if callable(getter):
            return getter(name)
        return None

    def plugin_config_path(self, name: str) -> Path | None:
        """插件配置文件的路径（插件数据目录下的 config.toml）。

        插件配置与插件代码分离：面板编辑的是这个文件，
        官方插件与第三方插件使用同一套位置。
        """
        getter = getattr(self._runtime, "plugin_config_path", None)
        if callable(getter):
            return getter(name)
        return None

    def plugin_manifest_path(self, name: str) -> Path | None:
        """插件自带 plugin.toml 的路径（不存在时为 None）。"""
        getter = getattr(self._runtime, "plugin_manifest_path", None)
        if callable(getter):
            return getter(name)
        return None

    def plugin_config_defaults(self, name: str) -> dict[str, Any]:
        """插件打包默认值（plugin.toml 的 [config]）。"""
        getter = getattr(self._runtime, "plugin_config_defaults", None)
        if callable(getter):
            return dict(getter(name))
        return {}

    def plugin_config_values(self, name: str) -> dict[str, Any]:
        """插件当前生效的配置（默认值 + 插件数据目录中保存的值）。"""
        getter = getattr(self._runtime, "plugin_config_values", None)
        if callable(getter):
            return dict(getter(name))
        return {}

    # ------------------------------------------------------------------
    # 插件配置「原地生效」通道
    # ------------------------------------------------------------------

    def register_config_consumer(self, name: str, consumer: Any) -> bool:
        """声明「本插件的配置可以在运行期原地生效」。

        插件在 load() 里调用一次即可；此后面板保存该插件配置时，会把运行期安全的
        改动直接喂给 consumer.apply_config()，不必重载插件本体。
        未声明的插件行为完全不变（仍提示「需要重启 NeoBoot 才能生效」）。
        """
        registrar = getattr(self._runtime, "register_plugin_config_consumer", None)
        if not callable(registrar):
            return False
        return bool(registrar(name, consumer))

    def unregister_config_consumer(self, name: str) -> bool:
        unregister = getattr(self._runtime, "unregister_plugin_config_consumer", None)
        if not callable(unregister):
            return False
        return bool(unregister(name))

    def config_consumer(self, name: str) -> Any | None:
        """该插件登记的配置消费者；未登记时返回 None。"""
        getter = getattr(self._runtime, "plugin_config_consumer", None)
        if not callable(getter):
            return None
        return getter(name)

    def installer_proxy(self) -> dict[str, Any]:
        """当前插件下载代理设置。"""
        getter = getattr(self._runtime, "installer_proxy", None)
        if callable(getter):
            return dict(getter())
        return {}

    def set_installer_proxy(
        self,
        *,
        mode: str | None = None,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        """切换插件下载代理（下次下载立即生效）。"""
        setter = getattr(self._runtime, "set_installer_proxy", None)
        if not callable(setter):
            raise RuntimeError("插件安装器不可用")
        return dict(setter(mode=mode, host=host, port=port))

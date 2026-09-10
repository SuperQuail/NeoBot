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

    def config_model(self, name: str) -> Any | None:
        """插件声明的配置模型（pydantic BaseModel），未声明时返回 None。"""
        getter = getattr(self._runtime, "plugin_config_model", None)
        if callable(getter):
            return getter(name)
        return None

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

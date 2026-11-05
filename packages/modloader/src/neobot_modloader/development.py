"""把开发控制台接到当前插件运行时，不创建另一份机器人。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.hot_reload import PluginHotReloader
from neobot_modloader.loading.manifest import read_manifest
from neobot_modloader.plugins.registration import validate_plugin_name

if TYPE_CHECKING:
    from neobot_modloader.runtime import PluginRuntime


class DevelopmentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PluginDevelopment:
    """按需开启已选插件的监听，沿用全局监听时不创建重复监听器。"""

    def __init__(self, runtime: PluginRuntime) -> None:
        self.runtime = runtime
        self.names: set[str] = set()
        self.watcher = runtime._hot_reloader or PluginHotReloader(runtime, names=self.names)
        self._lock = asyncio.Lock()

    async def set_enabled(self, name: str, enabled: bool) -> None:
        try:
            validate_plugin_name(name)
        except ValueError as error:
            raise DevelopmentError("invalid_plugin_name", str(error)) from error
        async with self._lock:
            if not enabled:
                self.names.discard(name)
                if not self.names and self.watcher is not self.runtime._hot_reloader:
                    await self.watcher.stop()
                return
            if not self.runtime.user_plugins_enabled:
                raise DevelopmentError("user_plugins_disabled", "当前实例已全局禁用第三方插件")
            path = self.runtime.plugin_dir / name
            if path.is_symlink() or not path.is_dir() or path.resolve().parent != self.runtime.plugin_dir:
                raise DevelopmentError("invalid_plugin_path", "只能开发当前实例插件目录中的直接子目录")
            from neobot_modloader.sdk.tooling.validation import check_project

            checked = await asyncio.to_thread(check_project, path)
            if not checked.ok:
                raise DevelopmentError("invalid_plugin", "; ".join(checked.errors))
            manifest = read_manifest(path / "plugin.toml")
            if manifest.get("name") != name:
                raise DevelopmentError("invalid_plugin_name", "插件清单名称必须与目录名称一致")
            if not self.runtime._resolve_enabled_state(name, True):
                raise DevelopmentError("plugin_disabled", "插件已停用，请先显式启用")
            record = self.runtime.manager.get_record(name)
            loaded_path = self.runtime._loaded_paths.get(name)
            if record is not None and loaded_path != path.resolve():
                raise DevelopmentError("plugin_name_conflict", "同名插件已从其他目录加载")
            if record is not None and record.state not in {PluginState.LOADED, PluginState.RUNNING}:
                raise DevelopmentError("plugin_not_running", "插件未运行，请先显式启动")
            if record is None:
                outcome = await self.runtime.load_plugin_path(path, start=True, auto_install_dependencies=False)
                if not outcome.ok:
                    raise DevelopmentError("plugin_load_failed", outcome.error or "插件加载失败")
            if not self.runtime._loaded_flags.get(name, (True, True))[0]:
                raise DevelopmentError("restart_required", "此插件不支持热重载")
            self.names.add(name)
            await self.watcher.start()
            # 已在运行的监听器也必须先建立新目标的基线，不能吞掉首次保存。
            await self.watcher.poll_once()

    def status(self, name: str) -> dict[str, object]:
        return {
            "development": name in self.names,
            "reload": dict(self.watcher.results.get(name, {"sequence": 0, "status": "idle"})),
        }

    async def close(self) -> None:
        if self.watcher is not self.runtime._hot_reloader:
            await self.watcher.stop()
        self.names.clear()

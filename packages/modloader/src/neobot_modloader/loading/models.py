from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


# 插件来源：官方插件随本体分发（只读，不可卸载），第三方插件位于数据目录。
OFFICIAL_SOURCE = "official"
THIRD_PARTY_SOURCE = "third_party"


@dataclass(frozen=True, slots=True)
class PluginRepository:
    """插件仓库元数据（plugin.toml 的 repo/branch）。"""

    url: str = ""
    branch: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.url)


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    name: str
    version: str
    plugin: Any
    plugin_dir: Path
    config: dict[str, Any]
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    min_neobot_version: str | None = None
    python_dependencies: tuple[str, ...] = ()
    module_names: tuple[str, ...] = ()
    source_path: Path | None = None
    source: str = THIRD_PARTY_SOURCE
    repo: str = ""
    branch: str = ""
    homepage: str = ""
    license: str = ""
    tags: tuple[str, ...] = ()
    hot_reload: bool = True
    config_hot_reload: bool = True

    @property
    def official(self) -> bool:
        return self.source == OFFICIAL_SOURCE

    @property
    def manageable(self) -> bool:
        """官方插件随本体分发，只能在控制台启停，不能安装/更新/卸载。"""
        return not self.official


@dataclass(frozen=True, slots=True)
class PluginLoadError:
    name: str
    plugin_dir: Path
    error: Exception


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    name: str
    version: str
    plugin_dir: Path
    description: str = ""
    author: str = ""
    enabled: bool = True
    dependencies: tuple[str, ...] = ()
    priority: int = 0
    min_neobot_version: str | None = None
    python_dependencies: tuple[str, ...] = ()
    missing_python_dependencies: tuple[str, ...] = ()
    error: Exception | None = None
    source_path: Path | None = None
    source: str = THIRD_PARTY_SOURCE
    repo: str = ""
    branch: str = ""
    homepage: str = ""
    license: str = ""
    tags: tuple[str, ...] = ()
    hot_reload: bool = True
    config_hot_reload: bool = True
    #: 依赖未满足时自动禁用的原因（None 表示依赖正常）
    disabled_reason: str | None = None
    #: 自动禁用的类别：dependency-missing / dependency-version /
    #: dependency-disabled / dependency-cycle / dependency-invalid
    disabled_code: str = ""
    #: 是否因依赖未满足而被自动禁用（与用户手动停用区分）
    auto_disabled: bool = False

    @property
    def official(self) -> bool:
        return self.source == OFFICIAL_SOURCE

    @property
    def manageable(self) -> bool:
        return not self.official


@dataclass(frozen=True, slots=True)
class DisabledPlugin:
    """因前置插件未满足而被自动禁用的插件。

    这不是错误：程序照常启动，插件只是不参与注册与加载；前置插件满足后
    （例如被重新启用）运行时会自动把它重新拉起来。
    """

    name: str
    plugin_dir: Path
    reason: str
    code: str = "dependency-missing"
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    source_path: Path | None = None
    source: str = THIRD_PARTY_SOURCE
    module_names: tuple[str, ...] = ()

    @property
    def official(self) -> bool:
        return self.source == OFFICIAL_SOURCE

    @property
    def manageable(self) -> bool:
        return not self.official


PluginLoadResult = LoadedPlugin | PluginLoadError | DisabledPlugin
PluginDiscoveryResult = DiscoveredPlugin | PluginLoadError

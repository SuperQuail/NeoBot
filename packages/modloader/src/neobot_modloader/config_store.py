"""插件配置存储：插件数据目录下的 config.toml。

插件配置与插件代码分离，也与启停状态分离：

- **打包默认值** 放在插件的 ``plugin.toml`` ``[config]``，随插件更新一起替换；
- **运行期配置** 写在插件数据目录 ``plugins_data/<插件名>/config.toml``，
  由用户或网页面板维护，插件更新（重装/覆盖插件目录）不会丢配置；
- **是否启用** 是独立记录（``PluginStateStore``），不出现在任何配置里。

读取时以打包默认值打底、已存配置覆盖（嵌套表逐层合并），
因此插件升级新增的配置项会自动补上默认值，无需手工补写。
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

#: 插件数据目录下的配置文件名
CONFIG_FILENAME = "config.toml"


def merge_plugin_config(
    defaults: Mapping[str, Any] | None,
    stored: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """默认值打底、已存值覆盖；嵌套表递归合并。"""
    merged: dict[str, Any] = {str(key): value for key, value in (defaults or {}).items()}
    for key, value in (stored or {}).items():
        name = str(key)
        current = merged.get(name)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            merged[name] = merge_plugin_config(current, value)
        else:
            merged[name] = value
    return merged


class PluginConfigStore:
    """单个插件的配置读写（只读文件，写入由面板/用户完成）。"""

    def __init__(
        self,
        data_dir: Path,
        *,
        defaults: Mapping[str, Any] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / CONFIG_FILENAME
        self._defaults = {str(key): value for key, value in (defaults or {}).items()}
        self._logger = logger or NullLogger()

    @property
    def defaults(self) -> dict[str, Any]:
        """插件打包默认值（plugin.toml 的 [config]）。"""
        return dict(self._defaults)

    def exists(self) -> bool:
        return self.path.is_file()

    def read_stored(self) -> dict[str, Any]:
        """只读取插件数据目录里已保存的配置；缺失或损坏时返回空字典。"""
        if not self.path.is_file():
            return {}
        try:
            with self.path.open("rb") as handle:
                data = tomllib.load(handle)
        except Exception as exc:
            self._logger.warning(f"插件配置读取失败，按默认值处理: {self.path}: {exc}")
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): value for key, value in data.items()}

    def read(self) -> dict[str, Any]:
        """插件实际生效的配置：默认值 + 已保存配置。"""
        return merge_plugin_config(self._defaults, self.read_stored())

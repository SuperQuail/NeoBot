"""第三方插件 plugin.toml 的 [config] 在线编辑。

只改动 [config] 表，插件名/版本等元数据保持原样；保存前备份同目录
.plugin.toml.dashboard.bak，并使用 revision 检测并发修改。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any

import tomlkit


class PluginConfigError(RuntimeError):
    pass


class PluginConfigConflictError(PluginConfigError):
    pass


def _revision(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:32]
    except OSError:
        return ""


def _atomic_write(path: Path, text: str) -> None:
    descriptor, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".plugin-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def describe_mapping(data: dict[str, Any], path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """把任意字典转换为前端可渲染的字段描述（支持嵌套表与数组）。"""
    descriptors: list[dict[str, Any]] = []
    for key, value in data.items():
        item: dict[str, Any] = {
            "name": key,
            "path": [*path, key],
            "label": key,
            "description": "",
            "required": True,
            "default": None,
            "value": _jsonable(value),
            "kind": "scalar",
            "type": type(value).__name__,
        }
        if isinstance(value, dict):
            item["kind"] = "group"
            item["fields"] = describe_mapping(value, (*path, key))
        elif isinstance(value, list):
            if value and all(isinstance(entry, dict) for entry in value):
                item["kind"] = "model_list"
                item["item_fields"] = describe_mapping(value[0], (*path, key))
                item["items"] = [
                    {"index": index, "fields": describe_mapping(entry, (*path, key, str(index)))}
                    for index, entry in enumerate(value)
                ]
            else:
                item["kind"] = "list"
                item["element_type"] = type(value[0]).__name__ if value else "any"
        descriptors.append(item)
    return descriptors


class PluginConfigEditor:
    """单个插件的 plugin.toml 配置读写。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def revision(self) -> str:
        return _revision(self.path)

    def _document(self) -> Any:
        if not self.path.is_file():
            raise PluginConfigError(f"plugin.toml 不存在: {self.path}")
        try:
            return tomlkit.parse(self.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise PluginConfigError(f"plugin.toml 解析失败: {exc}") from exc

    def read(self) -> dict[str, Any]:
        document = self._document()
        config = document.get("config") or {}
        if not isinstance(config, dict):
            raise PluginConfigError("plugin.toml 的 [config] 必须是 table")
        data = _jsonable(dict(config.unwrap() if hasattr(config, "unwrap") else config))
        return {
            "path": str(self.path),
            "revision": self.revision(),
            "source": tomlkit.dumps(config) if hasattr(config, "unwrap") else "",
            "config": data,
            "schema": describe_mapping(data),
            "form_supported": True,
            "name": str(document.get("name") or self.path.parent.name),
            "version": str(document.get("version") or ""),
        }

    def save(
        self,
        *,
        config: dict[str, Any] | None = None,
        source: str | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        document = self._document()
        if expected_revision is not None and expected_revision != self.revision():
            raise PluginConfigConflictError("插件配置已被其它会话修改，请重新读取后再保存")
        if source is not None:
            try:
                table = tomlkit.parse(source)
            except Exception as exc:
                raise PluginConfigError(f"TOML 解析失败: {exc}") from exc
            document["config"] = table
        else:
            table = document.get("config")
            if table is None or not hasattr(table, "get"):
                table = tomlkit.table()
                document["config"] = table
            for key in list(table.keys()):
                if key not in (config or {}):
                    del table[key]
            for key, value in (config or {}).items():
                table[key] = tomlkit.item(value)
        if self.path.is_file():
            try:
                self.path.with_name(self.path.name + ".dashboard.bak").write_text(
                    self.path.read_text(encoding="utf-8-sig"), encoding="utf-8"
                )
            except OSError:
                pass
        _atomic_write(self.path, tomlkit.dumps(document))
        return self.read()

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


def _decorate_schema(descriptors: list[dict[str, Any]], original: Any) -> list[dict[str, Any]]:
    """把敏感字段的默认值清空，只保留「是否已设置」，避免密钥回传到前端。"""
    from .security import is_sensitive_key

    if not isinstance(original, dict):
        return descriptors
    for item in descriptors:
        name = str(item.get("name") or "")
        raw = original.get(name)
        if is_sensitive_key(name):
            item["sensitive"] = True
            item["has_value"] = bool(str(raw or "").strip())
            item["value"] = ""
            continue
        if item.get("kind") == "group":
            _decorate_schema(item.get("fields") or [], raw)
        elif item.get("kind") == "model_list":
            entries = raw if isinstance(raw, list) else []
            for index, entry in enumerate(item.get("items") or []):
                _decorate_schema(
                    entry.get("fields") or [],
                    entries[index] if index < len(entries) else None,
                )
            if entries:
                _decorate_schema(item.get("item_fields") or [], entries[0])
    return descriptors


class PluginConfigEditor:
    """单个插件的 plugin.toml 配置读写（密钥只写不读）。"""

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
        from .security import has_secret_value, mask_mapping

        original = _jsonable(dict(config.unwrap() if hasattr(config, "unwrap") else config))
        secret_present = has_secret_value(original)
        masked = mask_mapping(original)
        # schema 从打码后的数据构建，避免分组 value 里残留明文
        schema = _decorate_schema(describe_mapping(masked), original)
        return {
            "path": str(self.path),
            "revision": self.revision(),
            # 含密钥时不返回源码，避免绕过脱敏拿到明文
            "source": "" if secret_present else (tomlkit.dumps(config) if hasattr(config, "unwrap") else ""),
            "source_available": not secret_present,
            "secret_policy": "write_only",
            "config": masked,
            "schema": schema,
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
        from .security import has_secret_value, restore_mapping

        document = self._document()
        if expected_revision is not None and expected_revision != self.revision():
            raise PluginConfigConflictError("插件配置已被其它会话修改，请重新读取后再保存")
        table = document.get("config")
        original = _jsonable(
            dict(table.unwrap() if hasattr(table, "unwrap") else table)
        ) if table is not None and hasattr(table, "get") else {}
        if source is not None:
            if has_secret_value(original):
                raise PluginConfigError(
                    "该插件配置含密钥，已禁用源码编辑；请使用表单模式（密钥只能更新，不能读取）"
                )
            try:
                table = tomlkit.parse(source)
            except Exception as exc:
                raise PluginConfigError(f"TOML 解析失败: {exc}") from exc
            document["config"] = table
        else:
            if table is None or not hasattr(table, "get"):
                table = tomlkit.table()
                document["config"] = table
            # 占位符/空值 -> 沿用原密钥；新值 -> 覆盖（密钥只能更新，不能读取）
            submitted = restore_mapping(dict(config or {}), original)
            for key in list(table.keys()):
                if key not in submitted:
                    del table[key]
            for key, value in submitted.items():
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

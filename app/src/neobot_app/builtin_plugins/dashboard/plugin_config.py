"""插件配置文件的在线编辑。

插件配置保存在插件数据目录 ``plugins_data/<插件名>/config.toml``：

- 与插件代码分离——插件目录（plugins/）在安装/更新时会被整体替换，配置放那里会丢；
- 与启停状态分离——插件是否启用是 ``plugin_state.json`` 里的独立记录，不是配置项；
- 官方插件与第三方插件使用同一套位置与同一套编辑逻辑。

文件本身就是配置表（没有 ``[config]`` 外层）；文件不存在时按插件声明的默认值渲染，
首次保存时创建。保存前备份同目录 `.config.toml.dashboard.bak`，并用 revision 检测并发修改；
含密钥的配置禁用源码编辑，密钥只能更新、不能读取。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import tomlkit

from neobot_modloader import merge_plugin_config


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
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".config-", suffix=".tmp")
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
    """插件数据目录下 config.toml 的读写（密钥只写不读）。"""

    def __init__(
        self,
        path: Path,
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> None:
        self.path = Path(path)
        self._defaults = _jsonable({str(key): value for key, value in (defaults or {}).items()})

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def revision(self) -> str:
        return _revision(self.path)

    def _document(self) -> Any:
        """当前文档；文件不存在时用插件默认值渲染出一份可编辑的骨架。"""
        if not self.path.is_file():
            document = tomlkit.document()
            for key, value in self._defaults.items():
                document[key] = tomlkit.item(value)
            return document
        try:
            return tomlkit.parse(self.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise PluginConfigError(f"插件配置解析失败: {exc}") from exc

    def _stored(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        return _jsonable(dict(self._document().unwrap()))

    def read(self) -> dict[str, Any]:
        from .security import has_secret_value, mask_mapping

        document = self._document()
        # 插件实际生效的配置 = 打包默认值 + 插件数据目录里保存的值
        effective = merge_plugin_config(self._defaults, self._stored())
        secret_present = has_secret_value(effective)
        masked = mask_mapping(effective)
        # schema 从打码后的数据构建，避免分组 value 里残留明文
        schema = _decorate_schema(describe_mapping(masked), effective)
        return {
            "path": str(self.path),
            "exists": self.path.is_file(),
            "revision": self.revision(),
            # 含密钥时不返回源码，避免绕过脱敏拿到明文
            "source": "" if secret_present else tomlkit.dumps(document),
            "source_available": not secret_present,
            "secret_policy": "write_only",
            "config": masked,
            "schema": schema,
            "form_supported": bool(schema),
            # 默认值同样可能来自 plugin.toml 且含密钥形态的键：与 config/source 一起打码，
            # 不能因为 secret_policy=write_only 却把 defaults 明文发出去。
            "defaults": mask_mapping(self._defaults),
        }

    def save(
        self,
        *,
        config: dict[str, Any] | None = None,
        source: str | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        from .security import has_secret_value, restore_mapping

        original = self._stored()
        if expected_revision is not None and expected_revision != self.revision():
            raise PluginConfigConflictError("插件配置已被其它会话修改，请重新读取后再保存")
        if source is not None:
            if has_secret_value(original):
                raise PluginConfigError(
                    "该插件配置含密钥，已禁用源码编辑；请使用表单模式（密钥只能更新，不能读取）"
                )
            try:
                document = tomlkit.parse(source)
            except Exception as exc:
                raise PluginConfigError(f"TOML 解析失败: {exc}") from exc
        else:
            # 占位符/空值 -> 沿用原密钥；新值 -> 覆盖（密钥只能更新，不能读取）
            submitted = restore_mapping(_jsonable(dict(config or {})), original)
            if not isinstance(submitted, dict) or not submitted:
                raise PluginConfigError("配置内容为空")
            document = tomlkit.document()
            for key, value in submitted.items():
                document[key] = tomlkit.item(value)
        if self.path.is_file():
            try:
                self.path.with_name(self.path.name + ".dashboard.bak").write_text(
                    self.path.read_text(encoding="utf-8-sig"), encoding="utf-8"
                )
            except OSError:
                pass
        _atomic_write(self.path, tomlkit.dumps(document))
        return self.read()

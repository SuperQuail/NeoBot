"""插件配置文件的在线编辑。

插件配置保存在插件数据目录 plugins_data/<插件名>/config.toml：

- 与插件代码分离——插件目录（plugins/）在安装/更新时会被整体替换，配置放那里会丢；
- **与本体 config.toml 解耦**——官方插件与第三方插件使用完全相同的位置与编辑逻辑，
  面板里显示的路径就是真实文件路径，不存在「写回本体 config.toml 某个分区」的说法；
- 与启停状态分离——插件是否启用是 plugin_state.json 里的独立记录，不是配置项。

文件本身就是配置表（没有 [config] 外层）；文件不存在时按插件声明的默认值渲染，
首次保存时创建。保存前备份同目录 .config.toml.dashboard.bak，并用 revision 检测并发修改；
含密钥的配置禁用源码编辑，密钥只能更新、不能读取。

**字段说明（注释）的三个来源**，按优先级：

1. 配置文件里已有的注释（保存时原样保留，用户手写的说明优先）；
2. 插件自带 plugin.toml 里 [config] 各键的注释（面板读它作为字段说明，并在生成
   配置文件时把注释写进去，让文件自解释）；
3. 插件 pydantic 配置模型的 Field(description=...)。
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import tomlkit

from neobot_modloader import merge_plugin_config


class PluginConfigError(RuntimeError):
    pass


class PluginConfigConflictError(PluginConfigError):
    pass


#: 从 plugin.toml 提取字段说明时使用的表名
MANIFEST_CONFIG_SECTION = "config"


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


def _inline_comment(line: str) -> str:
    """取行尾注释（只认 " #"，避免把字符串里的 # 当成注释）。"""
    index = line.find(" #")
    if index < 0:
        return ""
    return line[index + 1 :].lstrip("#").strip()


def _comments_from_text(text: str, section: str | None) -> dict[str, str]:
    """按行解析 TOML 文本，取各键上方（或行尾）的注释。

    为什么不用 tomlkit 的 trivia：tomlkit 把「键上方」的注释挂在 key 上，
    而 table.items() 返回的是 value，value.trivia.comment 只有行尾注释，
    于是前面几行的说明全都读不到。这里直接按行解析，行为可预期，也与用户
    手写文件的方式一致。

    Args:
        text: TOML 文本。
        section: 需要解析的表名；None 表示解析顶层键（插件配置文件就是顶层表）。

    多行连续注释会合并为一段；空行会断开注释与键的关联。
    """
    comments: dict[str, str] = {}
    pending: list[str] = []
    header: list[str] = []
    in_section = section is None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            pending = []
            continue
        if line.startswith("#"):
            content = line.lstrip("#").strip()
            if content:
                pending.append(content)
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line.strip("[]").strip()
            if section is not None and name == section:
                in_section = True
                header = list(pending)
            else:
                in_section = False
            pending = []
            continue
        if not in_section:
            pending = []
            continue
        if "=" in line:
            key = line.split("=", 1)[0].strip().strip('"').strip("'")
            if pending:
                comments[key] = " ".join(pending)
            else:
                inline = _inline_comment(line)
                if inline:
                    comments[key] = inline
            pending = []
            continue
        pending = []
    if section is not None and header:
        comments[""] = " ".join(header)
    return comments


def read_manifest_comments(manifest_path: Path | None) -> dict[str, str]:
    """读取 plugin.toml 里 [config] 各键的注释，作为插件的字段说明。

    插件作者只要在默认值上方写注释，面板表单与生成的 config.toml 就都有说明：

    .. code-block:: toml

        [config]
        # 面板监听端口（被占用时向后自动尝试）
        port = 9981
        # 是否允许远程管理
        allow_remote_manage = true

    连续多行注释会合并成一段。解析失败时返回空字典：说明只是锦上添花，
    不应影响配置编辑。表头自身的注释放在空字符串键下，作为兜底文案。
    """
    if manifest_path is None or not Path(manifest_path).is_file():
        return {}
    try:
        text = Path(manifest_path).read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    return _comments_from_text(text, MANIFEST_CONFIG_SECTION)


def apply_field_descriptions(
    descriptors: Sequence[dict[str, Any]],
    comments: Mapping[str, str],
    *,
    path: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """把注释填进字段描述（已有说明的字段不覆盖）。"""
    if not comments:
        return list(descriptors)
    fallback = str(comments.get("") or "")
    for item in descriptors:
        name = str(item.get("name") or "")
        full_path = (*path, name)
        current = str(item.get("description") or "").strip()
        if not current:
            text = str(comments.get(".".join(full_path)) or comments.get(name) or "")
            if text:
                item["description"] = text
            elif fallback and item.get("kind") == "scalar":
                item["description"] = fallback
        if item.get("kind") == "group":
            apply_field_descriptions(item.get("fields") or [], comments, path=full_path)
        elif item.get("kind") == "model_list":
            apply_field_descriptions(item.get("item_fields") or [], comments, path=full_path)
            for entry in item.get("items") or []:
                apply_field_descriptions(entry.get("fields") or [], comments, path=full_path)
    return list(descriptors)


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


def _add_with_comment(document: Any, key: str, value: Any, comment: str) -> None:
    """往文档里追加一个键，并在它上方写一行注释（保证生成的文件自解释）。"""
    item = tomlkit.item(value)
    if comment:
        try:
            document.add(tomlkit.comment(comment))
        except Exception:
            item.comment(comment)
    document[key] = item


class PluginConfigEditor:
    """插件数据目录下 config.toml 的读写（密钥只写不读）。"""

    def __init__(
        self,
        path: Path,
        *,
        defaults: Mapping[str, Any] | None = None,
        comments: Mapping[str, str] | None = None,
    ) -> None:
        self.path = Path(path)
        self._defaults = _jsonable({str(key): value for key, value in (defaults or {}).items()})
        self._comments = {str(key): str(value) for key, value in (comments or {}).items()}

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    @property
    def comments(self) -> dict[str, str]:
        return dict(self._comments)

    def revision(self) -> str:
        return _revision(self.path)

    def _document(self) -> Any:
        """当前文档；文件不存在时用插件默认值渲染出一份可编辑的骨架（带注释）。"""
        if not self.path.is_file():
            document = tomlkit.document()
            for key, value in self._defaults.items():
                _add_with_comment(document, key, value, self._comment_for(key))
            return document
        try:
            return tomlkit.parse(self.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise PluginConfigError(f"插件配置解析失败: {exc}") from exc

    def _comment_for(self, key: str) -> str:
        return self._comments.get(key) or ""

    def _stored(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        return _jsonable(dict(self._document().unwrap()))

    def _document_comments(self) -> dict[str, str]:
        """读取当前配置文件里各键的注释（用户自己写的说明优先）。"""
        if not self.path.is_file():
            return {}
        try:
            text = self.path.read_text(encoding="utf-8-sig")
        except OSError:
            return {}
        return _comments_from_text(text, None)

    def read(self) -> dict[str, Any]:
        from .security import has_secret_value, mask_mapping

        document = self._document()
        # 插件实际生效的配置 = 打包默认值 + 插件数据目录里保存的值
        effective = merge_plugin_config(self._defaults, self._stored())
        secret_present = has_secret_value(effective)
        masked = mask_mapping(effective)
        # schema 从打码后的数据构建，避免分组 value 里残留明文
        schema = _decorate_schema(describe_mapping(masked), effective)
        # 字段说明：配置文件里已有的注释优先，其次是 plugin.toml 的注释
        comments: dict[str, str] = {}
        for key, text in self._comments.items():
            comments.setdefault(key, text)
        for key, text in self._document_comments().items():
            comments[key] = text
        apply_field_descriptions(schema, comments)
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
            document = self._merge_into_document(submitted)
        if self.path.is_file():
            try:
                self.path.with_name(self.path.name + ".dashboard.bak").write_text(
                    self.path.read_text(encoding="utf-8-sig"), encoding="utf-8"
                )
            except OSError:
                pass
        _atomic_write(self.path, tomlkit.dumps(document))
        return self.read()

    def _merge_into_document(self, submitted: dict[str, Any]) -> Any:
        """在现有文档上就地更新（保留注释、顺序与用户手写的格式）。

        旧实现每次都从空文档重建，会把注释与顺序全部丢掉——插件的字段说明
        也就无法随文件一起保留。新键按 plugin.toml 的注释补齐说明。
        """
        if not self.path.is_file():
            document = tomlkit.document()
        else:
            try:
                document = tomlkit.parse(self.path.read_text(encoding="utf-8-sig"))
            except Exception:
                document = tomlkit.document()
        for key, value in submitted.items():
            if key in document:
                existing = document[key]
                if hasattr(existing, "items") and not hasattr(value, "items"):
                    # 保留原有子表，避免把分组配置写丢
                    continue
                # 就地替换值：键上方的注释与文件顺序都由 tomlkit 保留
                document[key] = tomlkit.item(value)
                continue
            _add_with_comment(document, key, value, self._comment_for(key))
        return document


__all__ = [
    "MANIFEST_CONFIG_SECTION",
    "PluginConfigConflictError",
    "PluginConfigEditor",
    "PluginConfigError",
    "apply_field_descriptions",
    "describe_mapping",
    "read_manifest_comments",
]

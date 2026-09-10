"""本体配置在线管理：config.toml 与 .env 的读取、校验、备份与写入。

设计目标（替换旧内置控制台的弱配置能力）：
- 结构化：从 dataclass 生成字段描述，前端可渲染成分组表单（含嵌套对象与对象数组）。
- 可校验：保存前严格校验类型与取值，错误定位到具体路径，不会写入半成品。
- 可回滚：每次写入前备份到 config_backup/，写入使用临时文件 + 原子替换。
- 可并发：revision（内容哈希）检测冲突，避免两个标签页互相覆盖。
- 可审计：密钥默认打码，单独接口按需显示并记录日志。
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import MISSING, dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, Iterator, NamedTuple, Union, get_args, get_origin

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.schemas.bot import (
    MODEL_TYPE_LABELS,
    BotConfig,
    ModelAssignments,
    ModelDefinition,
)
from neobot_app.config.schemas.env import EnvConfig
from neobot_app.builtin_plugins.dashboard.security import is_sensitive_key

ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_STRING_LENGTH = 200_000


class ConfigConflictError(RuntimeError):
    """revision 不匹配：文件已被其它会话修改。"""


class ConfigValidationError(RuntimeError):
    """配置内容校验失败。"""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        message = "；".join(
            f"{item.get('path') or '?'}: {item.get('message')}" for item in errors[:8]
        )
        super().__init__(message or "配置校验失败")


@dataclass(slots=True)
class EnvEntry:
    key: str
    value: str
    description: str = ""
    required: bool = False
    sensitive: bool = False
    builtin: bool = True
    present: bool = True
    line: int = 0


def _revision_of(path: Path) -> str:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
    return digest[:32]


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


def _type_name(field_type: Any) -> str:
    origin = get_origin(field_type)
    if origin is Union:
        args = [item for item in get_args(field_type) if item is not type(None)]
        if args:
            return _type_name(args[0])
        return "any"
    if origin in (list, dict):
        return origin.__name__
    if field_type in (int, float, bool, str):
        return field_type.__name__
    if is_dataclass(field_type):
        return "model"
    return "any"


def _is_optional(field_type: Any) -> bool:
    return get_origin(field_type) is Union and type(None) in get_args(field_type)


def _inner_types(field_type: Any) -> tuple[Any, ...]:
    if get_origin(field_type) is Union:
        return tuple(item for item in get_args(field_type) if item is not type(None))
    return (field_type,)


def _default_of(field_obj: Any) -> Any:
    if field_obj.default is not MISSING:
        return field_obj.default
    if field_obj.default_factory is not MISSING:  # type: ignore[comparison-overlap]
        try:
            return field_obj.default_factory()
        except Exception:
            return None
    return None


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _matches(value: Any, expected: Any) -> bool:
    if expected is Any or expected is None:
        return True
    origin = get_origin(expected)
    if origin is Union:
        return any(_matches(value, item) for item in _inner_types(expected))
    if origin is list:
        if not isinstance(value, list):
            return False
        args = get_args(expected)
        if not args:
            return True
        return all(_matches(item, args[0]) for item in value)
    if origin is dict:
        if not isinstance(value, dict):
            return False
        args = get_args(expected)
        if len(args) != 2:
            return True
        return all(
            _matches(key, args[0]) and _matches(item, args[1])
            for key, item in value.items()
        )
    if is_dataclass(expected):
        return isinstance(value, dict)
    if expected is bool:
        return isinstance(value, bool)
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected is str:
        return isinstance(value, str)
    if expected is type(None):
        return value is None
    try:
        return isinstance(value, expected)
    except TypeError:
        return True


def _resolve_actual_schema(declared: Any, data: Any) -> Any:
    """声明类型是 dataclass 时，按数据里出现的额外字段推断真实子类。

    例如 settings 声明为 ModelSettings，实际可能是 DeepSeekModelSettings，
    否则子类专属字段会被误判为未知配置项。
    """
    if not is_dataclass(declared) or not isinstance(data, dict):
        return declared
    base_names = {item.name for item in fields(declared)}
    extra_keys = set(data) - base_names
    if not extra_keys:
        return declared
    for subclass in declared.__subclasses__():
        subclass_extra = {item.name for item in fields(subclass)} - base_names
        if extra_keys & subclass_extra:
            return _resolve_actual_schema(subclass, data)
    return declared


def _validate_payload(schema: type, data: Any, path: str, errors: list[dict[str, str]]) -> None:
    """严格校验配置字典：类型不匹配立即记录错误（不会静默回退默认值）。"""
    if not is_dataclass(schema):
        return
    if not isinstance(data, dict):
        errors.append({"path": path, "message": f"应为表（table），实际为 {type(data).__name__}"})
        return
    known = {item.name for item in fields(schema)}
    for key in data:
        if key not in known:
            errors.append({"path": f"{path}.{key}" if path else str(key), "message": "未知配置项"})
    for field_obj in fields(schema):
        if field_obj.name not in data:
            continue
        raw = data[field_obj.name]
        field_path = f"{path}.{field_obj.name}" if path else field_obj.name
        field_type = field_obj.type
        if raw is None and _is_optional(field_type):
            continue
        inner = _inner_types(field_type)
        if not inner:
            continue
        target = inner[0]
        if is_dataclass(target):
            _validate_payload(_resolve_actual_schema(target, raw), raw, field_path, errors)
            continue
        if get_origin(target) is list:
            if not isinstance(raw, list):
                errors.append({"path": field_path, "message": "应为数组"})
                continue
            args = get_args(target)
            if args and is_dataclass(args[0]):
                for index, item in enumerate(raw):
                    _validate_payload(args[0], item, f"{field_path}[{index}]", errors)
                continue
            if args and not all(_matches(item, args[0]) for item in raw):
                errors.append({"path": field_path, "message": f"数组元素类型应为 {_type_name(args[0])}"})
            continue
        if not _matches(raw, target):
            errors.append(
                {
                    "path": field_path,
                    "message": f"类型应为 {_type_name(target)}，实际为 {type(raw).__name__}",
                }
            )


def describe_dataclass(schema: type, instance: Any, path: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    """把 dataclass 结构转换为前端可渲染的字段描述（含热重载标注）。"""
    from neobot_app.config.hot_reload import classify

    descriptors: list[dict[str, Any]] = []
    if not is_dataclass(schema):
        return descriptors
    for field_obj in fields(schema):
        name = field_obj.name
        description = str(field_obj.metadata.get("description", "") or "")
        field_type = field_obj.type
        value = getattr(instance, name, None) if instance is not None else None
        inner = _inner_types(field_type)
        target = inner[0] if inner else field_type
        field_path = (*path, name)
        hot_reload, restart_reason = classify(field_path)
        item: dict[str, Any] = {
            "name": name,
            "path": [*path, name],
            "label": name,
            "description": description,
            "required": not _is_optional(field_type),
            "default": _jsonable(_default_of(field_obj)),
            "value": _jsonable(value),
            "kind": "scalar",
            "type": _type_name(field_type),
            "readonly": bool(field_obj.metadata.get("readonly", False)),
            "hot_reload": hot_reload,
            "restart_reason": restart_reason,
            "hidden": bool(field_obj.metadata.get("hidden", False)),
        }
        options = field_obj.metadata.get("options")
        if isinstance(options, (list, tuple)) and options:
            item["options"] = [str(value) for value in options]
            if field_obj.metadata.get("options_strict"):
                item["options_strict"] = True
        if is_dataclass(target):
            actual_schema = target
            if is_dataclass(value) and isinstance(value, target):
                actual_schema = type(value)
            item["kind"] = "group"
            item["fields"] = describe_dataclass(actual_schema, value, (*path, name))
            scalars = _collect_scalar_fields(item["fields"])
            hot_count = sum(1 for field in scalars if field.get("hot_reload"))
            item["hot_reload"] = bool(scalars) and hot_count == len(scalars)
            item["partial_hot_reload"] = 0 < hot_count < len(scalars)
            item["hot_reload_count"] = hot_count
            item["field_count"] = len(scalars)
        elif get_origin(target) is list:
            args = get_args(target)
            element = args[0] if args else Any
            if is_dataclass(element):
                item["kind"] = "model_list"
                item["item_label"] = "项"
                item["item_fields"] = describe_dataclass(element, None, (*path, name))
                item["items"] = [
                    {
                        "index": index,
                        "fields": describe_dataclass(element, entry, (*path, name, str(index))),
                    }
                    for index, entry in enumerate(value or [])
                ]
            else:
                item["kind"] = "list"
                item["element_type"] = _type_name(element)
        elif get_origin(target) is dict:
            item["kind"] = "dict"
        descriptors.append(item)
    return descriptors


#: pydantic 字段类型 -> 面板字段类型
_PYDANTIC_TYPE_NAMES = {
    "boolean": "bool",
    "integer": "int",
    "number": "float",
    "string": "str",
}


def describe_pydantic_model(model: Any, values: Any = None) -> list[dict[str, Any]]:
    """把 pydantic 配置模型转换为面板可渲染的字段描述（官方插件配置用）。"""
    if model is None or not hasattr(model, "model_fields"):
        return []
    data = dict(values or {})
    descriptors: list[dict[str, Any]] = []
    for name, info in model.model_fields.items():
        annotation = getattr(info, "annotation", None)
        type_name = _PYDANTIC_TYPE_NAMES.get(
            str(getattr(annotation, "__name__", annotation)), "str"
        )
        extra = getattr(info, "json_schema_extra", None) or {}
        metadata = getattr(info, "metadata", ()) or ()
        minimum = maximum = None
        for item in metadata:
            if hasattr(item, "ge") and item.ge is not None:
                minimum = item.ge
            if hasattr(item, "le") and item.le is not None:
                maximum = item.le
        descriptor: dict[str, Any] = {
            "name": name,
            "path": [name],
            "label": str(getattr(info, "title", "") or name),
            "description": str(getattr(info, "description", "") or ""),
            "required": bool(getattr(info, "is_required", lambda: False)()),
            "default": _jsonable(getattr(info, "default", None)),
            "value": _jsonable(data.get(name, getattr(info, "default", None))),
            "kind": "scalar",
            "type": type_name,
            "readonly": bool(isinstance(extra, dict) and extra.get("readonly")),
            "hot_reload": True,
            "restart_reason": "",
        }
        if minimum is not None:
            descriptor["min"] = minimum
        if maximum is not None:
            descriptor["max"] = maximum
        descriptors.append(descriptor)
    return descriptors


def _collect_scalar_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """递归收集分组内的标量字段描述（用于汇总热重载状态）。"""
    collected: list[dict[str, Any]] = []
    for field in fields:
        if field.get("kind") == "group":
            collected.extend(_collect_scalar_fields(field.get("fields") or []))
        elif field.get("kind") in {"scalar", "list", "dict"}:
            collected.append(field)
    return collected


class BotConfigManager:
    """config.toml 的在线管理。"""

    def __init__(self, *, config_path: Path, backup_dir: Path, logger: Any = None) -> None:
        self.config_path = Path(config_path)
        self.backup_dir = Path(backup_dir)
        self._logger = logger

    # ------------------------------------------------------------------

    def revision(self) -> str:
        return _revision_of(self.config_path)

    def instance(self) -> BotConfig:
        """按当前文件解析出的配置对象（不触发模型注册）。"""
        source = ""
        if self.config_path.is_file():
            source = self.config_path.read_text(encoding="utf-8-sig")
        try:
            parsed = tomlkit.parse(source).unwrap() if source else {}
        except Exception as exc:
            raise ConfigValidationError(
                [{"path": "config.toml", "message": f"TOML 解析失败: {exc}"}]
            ) from exc
        return dict_to_dataclass(parsed, BotConfig) if parsed else BotConfig()

    def read(self) -> dict[str, Any]:
        source = ""
        if self.config_path.is_file():
            source = self.config_path.read_text(encoding="utf-8-sig")
        instance = self.instance()
        try:
            parsed = tomlkit.parse(source).unwrap() if source else {}
        except Exception as exc:
            raise ConfigValidationError(
                [{"path": "config.toml", "message": f"TOML 解析失败: {exc}"}]
            ) from exc
        secret_state: dict[str, bool] = {}
        config_payload = _mask_sensitive_leaves(_jsonable(instance), secret_state)
        raw_payload = _mask_sensitive_leaves(_jsonable(parsed), None)
        schema_payload = describe_dataclass(BotConfig, instance)
        for item in schema_payload:
            _mask_schema_defaults(item, secret_state, (str(item.get("name") or ""),))
        return {
            "path": str(self.config_path),
            "revision": self.revision(),
            "source": _mask_toml_source(source),
            "config": config_payload,
            "raw": raw_payload,
            "schema": schema_payload,
            "version": str(getattr(instance, "version", "")),
            "form_supported": True,
            # 密钥字段只回「是否已设置」（与 .env 的 masked/has_value 语义一致）
            "secrets_set": secret_state,
        }

    def validate(self, *, source: str | None = None, config: Any = None) -> list[dict[str, str]]:
        if source is not None:
            try:
                parsed = tomlkit.parse(source).unwrap()
            except Exception as exc:
                return [{"path": "config.toml", "message": f"TOML 解析失败: {exc}"}]
        else:
            parsed = config
        errors: list[dict[str, str]] = []
        _validate_payload(BotConfig, parsed or {}, "", errors)
        return errors

    def save(
        self,
        *,
        source: str | None = None,
        config: Any = None,
        expected_revision: str | None = None,
        max_backups: int = 15,
    ) -> dict[str, Any]:
        if source is not None and self.config_path.is_file():
            # 原文模式的输入来自面板（密钥行是占位符）：先还原再校验/写入。
            source = _restore_masked_source(
                self.config_path.read_text(encoding="utf-8-sig"), source
            )
        errors = self.validate(source=source, config=config)
        if errors:
            raise ConfigValidationError(errors)
        if source is None:
            document = (
                tomlkit.parse(self.config_path.read_text(encoding="utf-8-sig"))
                if self.config_path.is_file()
                else tomlkit.document()
            )
            current = document.unwrap() if self.config_path.is_file() else {}
            # 面板拿到的密钥字段是掩码后的空串（见 read()）：回传的空串要还原成
            # 文件里的现有值，否则一次表单保存就把 token 抹掉。
            submitted = _restore_masked_secrets(current, config or {})
            _merge_into_document(document, _diff_document(current, submitted, BotConfig))
            source = tomlkit.dumps(document)
        if expected_revision is not None and expected_revision != self.revision():
            raise ConfigConflictError("配置文件已被其它会话修改，请重新读取后再保存")
        if len(source) > MAX_STRING_LENGTH:
            raise ConfigValidationError(
                [{"path": "config.toml", "message": "内容过大，超过 200KB 限制"}]
            )
        if self.config_path.is_file():
            backup_config(self.config_path, self.backup_dir, max_backups=max_backups)
        _atomic_write(self.config_path, source if source.endswith("\n") else source + "\n")
        return self.read()

    # ------------------------------------------------------------------
    # 官方插件配置段（config.toml 的同名分区）
    # ------------------------------------------------------------------

    def section_values(self, section: str) -> dict[str, Any]:
        """读取 config.toml 中某个分区（官方插件配置）的当前值。"""
        instance = self.instance()
        target = getattr(instance, str(section), None)
        if target is None:
            return {}
        if is_dataclass(target) and not isinstance(target, type):
            return _jsonable(target)
        if isinstance(target, dict):
            return _jsonable(target)
        return {}

    def update_section(
        self,
        section: str,
        values: dict[str, Any],
        *,
        expected_revision: str | None = None,
        max_backups: int = 15,
    ) -> dict[str, Any]:
        """只更新 config.toml 中某个分区的字段（官方插件配置直接编辑）。"""
        name = str(section or "").strip()
        if not name or not name.isidentifier():
            raise ConfigValidationError(
                [{"path": "section", "message": "非法配置分区名"}]
            )
        if expected_revision is not None and expected_revision != self.revision():
            raise ConfigConflictError("配置文件已被其它会话修改，请重新读取后再保存")

        document = (
            tomlkit.parse(self.config_path.read_text(encoding="utf-8-sig"))
            if self.config_path.is_file()
            else tomlkit.document()
        )
        current = document.unwrap() if self.config_path.is_file() else {}
        base = current.get(name)
        merged = dict(base) if isinstance(base, dict) else {}
        merged.update({str(key): value for key, value in (values or {}).items()})

        new_config = dict(current)
        new_config[name] = merged
        errors = self.validate(
            config=_filter_managed(BotConfig, new_config, strict=frozenset({(name,)}))
        )
        if errors:
            raise ConfigValidationError(errors)

        _merge_into_document(
            document, _diff_document(current, new_config, BotConfig)
        )
        if self.config_path.is_file():
            backup_config(self.config_path, self.backup_dir, max_backups=max_backups)
        source = tomlkit.dumps(document)
        _atomic_write(self.config_path, source if source.endswith("\n") else source + "\n")
        return self.read()

    # ------------------------------------------------------------------
    # 插件系统（代理设置）
    # ------------------------------------------------------------------

    def update_plugins_proxy(
        self,
        *,
        mode: str,
        host: str,
        port: int,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """写入 config.toml 的 [plugins] 代理字段（只改这三个键）。"""
        from neobot_modloader.installer import ProxySettings

        try:
            settings = ProxySettings(mode=mode, host=host, port=port)
        except Exception as exc:
            raise ConfigValidationError([{"path": "plugins.proxy", "message": str(exc)}]) from exc
        if expected_revision is not None and expected_revision != self.revision():
            raise ConfigConflictError("配置文件已被其它会话修改，请重新读取后再保存")

        document = (
            tomlkit.parse(self.config_path.read_text(encoding="utf-8-sig"))
            if self.config_path.is_file()
            else tomlkit.document()
        )
        current = document.unwrap() if self.config_path.is_file() else {}
        plugins_raw = current.get("plugins")
        if not isinstance(plugins_raw, dict):
            plugins_raw = _jsonable(BotConfig().plugins)
        plugins_raw = dict(plugins_raw)
        plugins_raw["proxy_mode"] = settings.mode
        plugins_raw["proxy_host"] = settings.host
        plugins_raw["proxy_port"] = settings.port

        new_config = dict(current)
        new_config["plugins"] = plugins_raw
        errors = self.validate(
            config=_filter_managed(BotConfig, new_config, strict=frozenset({("plugins",)}))
        )
        if errors:
            raise ConfigValidationError(errors)

        _merge_into_document(
            document, _diff_document(current, new_config, BotConfig)
        )
        if self.config_path.is_file():
            backup_config(self.config_path, self.backup_dir, max_backups=15)
        source = tomlkit.dumps(document)
        _atomic_write(self.config_path, source if source.endswith("\n") else source + "\n")
        return self.read()

    # ------------------------------------------------------------------
    # 模型库 / 调用方分配
    # ------------------------------------------------------------------

    def _models_document(self, parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """取出模型库与分配表；文件里没有时用默认值补全（首次编辑即落盘）。"""
        defaults = BotConfig()
        models_raw = parsed.get("models") if isinstance(parsed.get("models"), dict) else {}
        library_raw = models_raw.get("registry")
        if isinstance(library_raw, list) and library_raw:
            library = [dict(item) for item in library_raw if isinstance(item, dict)]
        else:
            library = [_jsonable(item) for item in defaults.models.registry]
        assignments_raw = models_raw.get("assignments")
        if isinstance(assignments_raw, dict):
            assignments = {str(key): value for key, value in assignments_raw.items()}
        else:
            assignments = _jsonable(defaults.models.assignments)
        return library, assignments

    def update_models(
        self,
        *,
        upsert: dict[str, Any] | None = None,
        delete: str | None = None,
        assignments: dict[str, Any] | None = None,
        expected_revision: str | None = None,
        max_backups: int = 15,
        resolved: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """模型库增删改 + 调用方分配，只改动 config.toml 的 [models] 段。

        `upsert` 未提供 key（引用名）时，按模型名自动生成唯一引用名；
        生成的引用名通过 `resolved`（可选出参）返回给调用方。
        """
        from neobot_app.config.schemas.bot import ModelAssignments, normalize_model_key

        if expected_revision is not None and expected_revision != self.revision():
            raise ConfigConflictError("配置文件已被其它会话修改，请重新读取后再保存")

        document = (
            tomlkit.parse(self.config_path.read_text(encoding="utf-8-sig"))
            if self.config_path.is_file()
            else tomlkit.document()
        )
        current = document.unwrap() if self.config_path.is_file() else {}
        library, current_assignments = self._models_document(current)

        errors: list[dict[str, str]] = []
        if delete is not None:
            target = normalize_model_key(str(delete))
            references = [
                role
                for role, key in _assignment_items(current_assignments)
                if key == target
            ]
            if references:
                labels = "、".join(ROLE_LABELS.get(role, role) for role in references)
                raise ConfigValidationError(
                    [
                        {
                            "path": "models.registry",
                            "message": f"模型 {target} 仍被以下调用方引用，请先改绑再删除: {labels}",
                        }
                    ]
                )
            if not any(str(item.get("key") or "") == target for item in library):
                raise ConfigValidationError(
                    [{"path": "models.registry", "message": f"模型库中不存在 {target}"}]
                )
            library = [item for item in library if str(item.get("key") or "") != target]
        elif upsert is not None:
            entry = {str(key): value for key, value in dict(upsert).items()}
            entry["key"] = normalize_model_key(str(entry.get("key") or ""))
            if not entry["key"]:
                # 面板不暴露引用名：按「模型名」自动生成（重名时追加序号）
                entry["key"] = _derive_model_key(
                    str(entry.get("model_name") or ""),
                    str(entry.get("model_type") or "chat"),
                    {str(item.get("key") or "") for item in library},
                )
            for index, item in enumerate(library):
                if str(item.get("key") or "") == entry["key"]:
                    library[index] = {**item, **entry}
                    break
            else:
                library.append(entry)
            if resolved is not None:
                resolved["key"] = entry["key"]

        if assignments is not None:
            valid_roles = set(ModelAssignments.SINGLE_ROLES) | {"creator_image_models"}
            unknown = [str(role) for role in assignments if str(role) not in valid_roles]
            if unknown:
                errors.append(
                    {
                        "path": "models.assignments",
                        "message": "未知调用方: " + "、".join(sorted(unknown)),
                    }
                )
            library_keys = {str(item.get("key") or "") for item in library}
            for role in ModelAssignments.SINGLE_ROLES:
                if role not in assignments:
                    continue
                key = str(assignments.get(role) or "").strip()
                if key and key not in library_keys:
                    errors.append(
                        {
                            "path": f"models.assignments.{role}",
                            "message": f"模型库中不存在 key: {key}",
                        }
                    )
                if not key and role not in ("vision_model", "tts_model"):
                    errors.append(
                        {"path": f"models.assignments.{role}", "message": "该调用方必须指定模型"}
                    )
                current_assignments[role] = key
            images = assignments.get("creator_image_models")
            if images is not None:
                if not isinstance(images, list):
                    errors.append(
                        {
                            "path": "models.assignments.creator_image_models",
                            "message": "应为数组",
                        }
                    )
                else:
                    cleaned = [
                        str(item or "").strip()
                        for item in images
                        if str(item or "").strip()
                    ]
                    for key in cleaned:
                        if key not in library_keys:
                            errors.append(
                                {
                                    "path": "models.assignments.creator_image_models",
                                    "message": f"模型库中不存在 key: {key}",
                                }
                            )
                    current_assignments["creator_image_models"] = cleaned
        if errors:
            raise ConfigValidationError(errors)

        new_config = dict(current)
        new_config["models"] = {
            "registry": library,
            "assignments": current_assignments,
        }
        config_errors = self.validate(
            config=_filter_managed(BotConfig, new_config, strict=frozenset({("models",)}))
        )
        if config_errors:
            raise ConfigValidationError(config_errors)

        _merge_into_document(
            document, _diff_document(current, new_config, BotConfig)
        )
        if self.config_path.is_file():
            backup_config(self.config_path, self.backup_dir, max_backups=max_backups)
        source = tomlkit.dumps(document)
        _atomic_write(self.config_path, source if source.endswith("\n") else source + "\n")
        return self.read()


def _derive_model_key(model_name: str, model_type: str, existing: set[str]) -> str:
    """按模型名生成引用名（key）：小写、非字母数字转连字符，重名时追加 -2/-3…"""
    raw = str(model_name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9_.-]+", "-", raw).strip("-._")
    while "--" in slug:
        slug = slug.replace("--", "-")
    base = (slug or f"{str(model_type or 'model').strip().lower()}-model")[:60]
    key = base
    counter = 2
    while key in existing:
        key = f"{base}-{counter}"[:64]
        counter += 1
    return key


def _assignment_items(assignments: dict[str, Any]) -> list[tuple[str, str]]:
    """展开「调用方 -> 模型 key」，生图列表逐项展开。"""
    items: list[tuple[str, str]] = []
    for role in ROLE_LABELS:
        value = assignments.get(role)
        if role == "creator_image_models":
            if isinstance(value, list):
                items.extend(
                    ("creator_image_models", str(item).strip())
                    for item in value
                    if str(item or "").strip()
                )
            continue
        if isinstance(value, str) and value.strip():
            items.append((role, value.strip()))
    return items


_DELETE = object()
_MISSING = object()

#: 自由映射字段（dict 类型）：键由用户/账号决定，例如分群回复系数，
#: 表单里删掉某个键就是真的要删，不做「未知键保护」。
_FREE_MAPPING = object()


class _ListOfTables(NamedTuple):
    """表数组字段（``List[dataclass]``，如 models.registry / chat.key_word）。

    逐元素 diff：元素里面板不认识的键同样要保留。
    """

    element: Any

_MANAGED_TREES: dict[type, dict[str, Any]] = {}


def _managed_tree(schema: type) -> dict[str, Any]:
    """按 dataclass 声明生成托管字段树，用于判断哪些键允许被表单删除。

    - dataclass 字段 -> 子 dataclass（分区：只有声明过的键才允许删）
    - dict 字段 -> ``_FREE_MAPPING``（键由用户决定，允许删）
    - 其它字段 -> ``None``（标量/数组，整值替换，不涉及删键）
    """
    cached = _MANAGED_TREES.get(schema)
    if cached is not None:
        return cached
    tree: dict[str, Any] = {}
    if is_dataclass(schema):
        for field_obj in fields(schema):
            inner = _inner_types(field_obj.type)
            target = inner[0] if inner else field_obj.type
            if is_dataclass(target):
                tree[field_obj.name] = target
            elif get_origin(target) is list:
                args = get_args(target)
                element = args[0] if args else None
                tree[field_obj.name] = (
                    _ListOfTables(element) if is_dataclass(element) else None
                )
            elif get_origin(target) is dict:
                tree[field_obj.name] = _FREE_MAPPING
            else:
                tree[field_obj.name] = None
    _MANAGED_TREES[schema] = tree
    return tree


def _mask_sensitive_leaves(data: Any, found: dict[str, bool] | None = None, path: tuple[str, ...] = ()) -> Any:
    """把密钥类字段的值替换为空串，并记录「是否已设置」。

    config.toml 里也有机密（``adapter.local_auth_token`` /
    ``adapter.reverse_ws_access_token``）：认证/反向 WS 的 token 落到面板响应里，
    任何已登录会话（含只读、远程）都能拿到并冒充 OneBot 框架注入伪造事件。
    这里与 .env 的处理保持一致：只回「是否已设置」，不回值。
    """
    if isinstance(data, dict):
        masked: dict[str, Any] = {}
        for key, value in data.items():
            child_path = (*path, str(key))
            if is_sensitive_key(key):
                has_value = bool(value)
                if isinstance(value, str) and value:
                    has_value = True
                if found is not None:
                    found[".".join(child_path)] = has_value
                masked[key] = "" if isinstance(value, str) or value is None else value
                continue
            masked[key] = _mask_sensitive_leaves(value, found, child_path)
        return masked
    if isinstance(data, list):
        return [_mask_sensitive_leaves(item, found, (*path, str(index))) for index, item in enumerate(data)]
    return data


_SECRET_PLACEHOLDER = "***"
_TOML_SECTION_RE = re.compile(r"^\s*\[(?P<name>[^\]]+)\]\s*(?:#.*)?$")
#: 只匹配「简单键 = 引号字符串/单 token（可带行尾注释）」，复杂值（数组、多行、
#: 时间）原样放过：面板不需要脱敏它们，误改反而是数据损坏。
_TOML_KEY_LINE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_\-]+)(?P<sep>\s*=\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^#\s]+)(?P<tail>\s*(?:#.*)?)$"
)


def _iter_secret_lines(source: str) -> Iterator[tuple[str, re.Match[str]]]:
    """逐行产出 (当前分区名, 匹配到的密钥行)。"""
    section = ""
    for line in source.splitlines():
        header = _TOML_SECTION_RE.match(line.strip())
        if header:
            section = header.group("name").strip()
            continue
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")):
            yield section, match


def _mask_toml_source(source: str) -> str:
    """把原文里密钥键的值替换为占位符（面板响应不回明文）。"""
    out: list[str] = []
    for line in source.splitlines():
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")):
            out.append(
                f'{match.group("indent")}{match.group("key")}{match.group("sep")}'
                f'"{_SECRET_PLACEHOLDER}"{match.group("tail")}'
            )
            continue
        out.append(line)
    text = "\n".join(out)
    return text + "\n" if source.endswith("\n") else text


def _restore_masked_source(current_source: str, submitted: str) -> str:
    """提交原文里仍是占位符的密钥键，还原成磁盘上的现有值。

    面板原文是脱敏后返回的：用户没动那一行（提交回来仍是 ``***``）时必须还原，
    否则一次保存就把 token 写成字面量 ``***``。
    """
    originals = {
        (section, match.group("key")): match.group("value")
        for section, match in _iter_secret_lines(current_source)
    }
    if not originals:
        return submitted
    out: list[str] = []
    section = ""
    for line in submitted.splitlines():
        header = _TOML_SECTION_RE.match(line.strip())
        if header:
            section = header.group("name").strip()
            out.append(line)
            continue
        match = _TOML_KEY_LINE_RE.match(line)
        if match and is_sensitive_key(match.group("key")):
            if match.group("value").strip("\"'") == _SECRET_PLACEHOLDER:
                original = originals.get((section, match.group("key")))
                if original is not None:
                    out.append(
                        f'{match.group("indent")}{match.group("key")}'
                        f'{match.group("sep")}{original}{match.group("tail")}'
                    )
                    continue
        out.append(line)
    text = "\n".join(out)
    return text + "\n" if submitted.endswith("\n") else text


def _mask_schema_defaults(
    item: dict[str, Any], found: dict[str, bool], path: tuple[str, ...]
) -> None:
    """schema 描述里的 default/value 同样不能带出密钥明文。"""
    if path and is_sensitive_key(path[-1]):
        for key in ("default", "value"):
            if item.get(key):
                found[".".join(path)] = True
            item[key] = ""
        return
    # 分区节点自身也带 default/value（整段配置的字典副本），里面的密钥要一并掩码。
    for key in ("default", "value"):
        value = item.get(key)
        if isinstance(value, (dict, list)):
            item[key] = _mask_sensitive_leaves(value, found, path)
    for child in item.get("fields") or []:
        if isinstance(child, dict):
            _mask_schema_defaults(child, found, (*path, str(child.get("name") or "")))
    for child in item.get("item_fields") or []:
        if isinstance(child, dict):
            _mask_schema_defaults(child, found, (*path, str(child.get("name") or "")))


def _restore_masked_secrets(current: Any, submitted: Any, path: tuple[str, ...] = ()) -> Any:
    """把被掩码的密钥字段还原成文件里的现有值。

    掩码后的空串回传时不能当成「用户清空」——否则面板保存会把 token 抹掉。
    想清空请用 TOML 模式直接编辑。
    """
    if isinstance(current, dict) and isinstance(submitted, dict):
        restored: dict[str, Any] = {}
        for key, value in submitted.items():
            child_path = (*path, str(key))
            existing = current.get(key)
            if is_sensitive_key(key) and value == "" and isinstance(existing, str) and existing:
                restored[key] = existing
                continue
            restored[key] = _restore_masked_secrets(existing, value, child_path)
        return restored
    if isinstance(current, list) and isinstance(submitted, list):
        return [
            _restore_masked_secrets(
                current[index] if index < len(current) else None,
                item,
                (*path, str(index)),
            )
            for index, item in enumerate(submitted)
        ]
    return submitted


def _filter_managed(
    schema: type,
    data: Any,
    *,
    strict: frozenset[tuple[str, ...]] = frozenset(),
    path: tuple[str, ...] = (),
) -> Any:
    """复制一份配置并丢掉声明之外的键（校验用）。

    配置文件里可能本来就有面板不认识的键（自定义分区、插件字段、更新版本
    留下的新字段）。它们既不该让整次保存因「未知配置项」失败，也不该参与
    本次校验。``strict`` 里的路径保持原样：正在编辑的那个分区若出现未知键，
    依然会被校验拦下。
    """
    if not isinstance(data, dict) or not is_dataclass(schema) or path in strict:
        return data
    tree = _managed_tree(schema)
    filtered: dict[str, Any] = {}
    for key, value in data.items():
        if key not in tree:
            continue
        child = tree[key]
        if is_dataclass(child) and isinstance(value, dict):
            filtered[key] = _filter_managed(child, value, strict=strict, path=(*path, key))
        else:
            filtered[key] = value
    return filtered


def _diff_sequence(
    current: Any, new: Any, element_schema: Any
) -> Any:
    """表数组（``[[models.registry]]`` 这类）逐元素 diff。

    数组是「整值替换」的话，元素里面板不认识的键会随一次表单保存被抹掉
    （与分区字段同一类数据丢失）。这里按序号逐元素 diff：下标对得上的元素走
    dict diff（未知键保留），新增的元素整体写入，变短的数组由合并阶段截断。
    返回 None 表示无需改动。
    """
    if not isinstance(current, list) or not isinstance(new, list):
        return new
    diff: list[Any] = []
    for index, item in enumerate(new):
        if (
            index < len(current)
            and isinstance(current[index], dict)
            and isinstance(item, dict)
        ):
            diff.append(_diff_document(current[index], item, element_schema))
        else:
            diff.append(item)
    if diff == current:
        return None
    return diff


def _diff_document(current: Any, new: Any, managed: Any = None) -> Any:
    """只保留相对当前文件真正变化的键，避免整份重写丢掉注释与顺序。

    ``managed`` 是 :func:`_managed_tree` 对应的 dataclass（或 ``_FREE_MAPPING``）。
    表单只认识托管字段，因此文件里那些面板不认识的键（用户自定义分区、插件
    写入的字段、更新版本留下的新字段）一律保留：之前它们会被当成「表单里
    删掉的键」直接删掉，一次面板保存就能把它们从 config.toml 里抹掉。
    """
    if not isinstance(current, dict) or not isinstance(new, dict):
        return new
    tree = _managed_tree(managed) if is_dataclass(managed) else None
    changes: dict[str, Any] = {}
    for key, value in new.items():
        child = tree.get(key) if tree is not None else None
        if isinstance(child, _ListOfTables):
            nested_list = _diff_sequence(current.get(key), value, child.element)
            if nested_list is not None:
                changes[key] = nested_list
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            nested = _diff_document(current[key], value, child)
            if nested:
                changes[key] = nested
        elif current.get(key, _MISSING) != value:
            changes[key] = value
    for key in current:
        if key in new:
            continue
        if tree is not None and key not in tree:
            continue
        changes[key] = _DELETE
    return changes


def _merge_sequence(document: Any, values: list[Any]) -> None:
    """把元素级 diff 合并回 TOML 表数组（保留未变元素的注释与顺序）。"""
    while len(document) > len(values):
        del document[-1]
    for index, item in enumerate(values):
        if index >= len(document):
            document.append(tomlkit.item(item))
            continue
        target = document[index]
        if isinstance(item, dict) and hasattr(target, "get"):
            _merge_into_document(target, item)
        else:
            document[index] = tomlkit.item(item)


def _merge_into_document(document: Any, data: dict[str, Any], prefix: tuple[str, ...] = ()) -> None:
    """把前端表单回传的字典合并回 TOML 文档，保留原有注释与顺序。"""
    if not isinstance(data, dict):
        return
    for key, value in data.items():
        if value is _DELETE:
            if key in document:
                del document[key]
            continue
        if value is None:
            # 可选字段留空：不写入该键，读取时按默认值（None）处理
            continue
        if isinstance(value, dict):
            existing = document.get(key)
            if existing is None or not hasattr(existing, "get"):
                document[key] = tomlkit.table()
                existing = document[key]
            _merge_into_document(existing, value, (*prefix, str(key)))
        elif isinstance(value, list) and _is_table_array(document.get(key)):
            _merge_sequence(document.get(key), value)
        else:
            document[key] = tomlkit.item(value)


def _is_table_array(node: Any) -> bool:
    return isinstance(node, tomlkit.items.AoT)


class EnvFileManager:
    """.env 的在线管理：保留注释与顺序，按行替换，密钥默认打码。"""

    def __init__(self, *, env_path: Path, backup_dir: Path, logger: Any = None) -> None:
        self.env_path = Path(env_path)
        self.backup_dir = Path(backup_dir)
        self._logger = logger

    def revision(self) -> str:
        return _revision_of(self.env_path)

    def _builtin_metadata(self) -> dict[str, tuple[str, bool]]:
        metadata: dict[str, tuple[str, bool]] = {}
        for field_obj in fields(EnvConfig):
            env_key = str(field_obj.metadata.get("env_key") or field_obj.name.upper())
            description = str(field_obj.metadata.get("description", "") or "")
            metadata[env_key] = (description, not _is_optional(field_obj.type))
        return metadata

    def read(self, *, mask: bool = True) -> dict[str, Any]:
        """读取 .env。

        安全约定：敏感键（APIKey/Token/密码等）的值永不出网，只返回
        has_value（是否已设置）；非敏感键照常返回。源码原文同样不返回，
        避免绕过脱敏直接拿到密钥。
        """
        from .security import is_sensitive_key

        builtin = self._builtin_metadata()
        entries: list[dict[str, Any]] = []
        lines: list[str] = []
        if self.env_path.is_file():
            lines = self.env_path.read_text(encoding="utf-8-sig").splitlines()
        seen: set[str] = set()
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            seen.add(key)
            description, required = builtin.get(key, ("", False))
            sensitive = is_sensitive_key(key)
            entries.append(
                {
                    "key": key,
                    "value": "" if (mask and sensitive) else value,
                    "has_value": bool(value),
                    "masked": bool(mask and sensitive and value),
                    "description": description,
                    "required": required,
                    "sensitive": sensitive,
                    "builtin": key in builtin,
                    "line": index,
                }
            )
        for key, (description, required) in builtin.items():
            if key in seen:
                continue
            entries.append(
                {
                    "key": key,
                    "value": "",
                    "has_value": False,
                    "masked": False,
                    "description": description,
                    "required": required,
                    "sensitive": is_sensitive_key(key),
                    "builtin": True,
                    "line": 0,
                }
            )
        return {
            "path": str(self.env_path),
            "revision": self.revision(),
            "items": entries,
            "platforms": self.platforms(),
            "source_available": False,
            "secret_policy": "write_only",
        }

    def platforms(self) -> list[dict[str, Any]]:
        """列出内置与自定义 API 平台：平台名、URL 以及 Key 是否已配置。"""
        values = self._current_values()
        names: dict[str, dict[str, Any]] = {}

        def record(name: str, *, builtin: bool) -> None:
            entry = names.setdefault(
                name,
                {
                    "name": name,
                    "url": "",
                    "has_key": False,
                    "url_env": f"{name}_URL",
                    "key_env": f"{name}_APIKey",
                    "builtin": builtin,
                },
            )
            entry["builtin"] = entry["builtin"] or builtin
            url = values.get(f"{name}_URL")
            if url:
                entry["url"] = url
            if values.get(f"{name}_APIKey"):
                entry["has_key"] = True

        for field_obj in fields(EnvConfig):
            env_key = str(field_obj.metadata.get("env_key") or field_obj.name.upper())
            for suffix in ("_URL", "_APIKey"):
                if env_key.endswith(suffix):
                    record(env_key[: -len(suffix)], builtin=True)
        for key in values:
            for suffix in ("_URL", "_APIKey"):
                if key.endswith(suffix):
                    record(key[: -len(suffix)], builtin=False)
        return sorted(names.values(), key=lambda item: item["name"].casefold())

    def add_platform(
        self,
        *,
        name: str,
        url: str,
        api_key: str = "",
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """一键添加 API 供应商：写入 <平台名>_URL 与 <平台名>_APIKey。

        Key 为只写字段：保存后无法再读取，只能覆盖更新。
        """
        normalized = EnvConfig._normalize_platform_name(str(name or ""))
        if not ENV_KEY_RE.fullmatch(normalized):
            raise ConfigValidationError(
                [
                    {
                        "path": "name",
                        "message": "平台名只能包含字母、数字与下划线，且不能以数字开头（例如 MyProvider）",
                    }
                ]
            )
        normalized_url = str(url or "").strip()
        if not normalized_url:
            raise ConfigValidationError([{"path": "url", "message": "请填写平台 API 地址"}])
        if not re.match(r"^https?://", normalized_url):
            raise ConfigValidationError(
                [{"path": "url", "message": "API 地址必须以 http:// 或 https:// 开头"}]
            )
        updates = {f"{normalized}_URL": normalized_url}
        key_value = str(api_key or "").strip()
        if key_value:
            updates[f"{normalized}_APIKey"] = key_value
        return self.save(updates=updates, expected_revision=expected_revision)

    def _current_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        if not self.env_path.is_file():
            return values
        for line in self.env_path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key:
                values[key] = value.strip()
        return values

    def save(
        self,
        *,
        updates: dict[str, str] | None = None,
        deletes: list[str] | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """保存 .env。

        - 只写入相对当前文件真正变化的键；
        - 敏感键（APIKey/Token 等）只能写入新值：空值视为「未改动」，
          占位符不会被写回文件，从而保证密钥不可读、不可被误覆盖。
        """
        from .security import SECRET_PLACEHOLDER, is_sensitive_key

        raw_updates = {str(key): str(value) for key, value in (updates or {}).items()}
        deletes = [str(key) for key in (deletes or [])]
        errors: list[dict[str, str]] = []
        for key in [*raw_updates, *deletes]:
            if not ENV_KEY_RE.fullmatch(key):
                errors.append({"path": key, "message": "非法环境变量名"})
        if errors:
            raise ConfigValidationError(errors)
        if expected_revision is not None and expected_revision != self.revision():
            raise ConfigConflictError(".env 已被其它会话修改，请重新读取后再保存")

        current = self._current_values()
        updates: dict[str, str] = {}
        for key, value in raw_updates.items():
            if key in deletes:
                continue
            if value == SECRET_PLACEHOLDER:
                continue
            if is_sensitive_key(key) and not value.strip():
                # 敏感键留空 = 保持原值（面板不会回传明文）
                continue
            if current.get(key, "") == value and key in current:
                continue
            updates[key] = value
        deletes = [key for key in deletes if key in current]
        if not updates and not deletes:
            return self.read()

        lines: list[str] = []
        if self.env_path.is_file():
            lines = self.env_path.read_text(encoding="utf-8-sig").splitlines()
        remaining = dict(updates)
        output: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                output.append(line)
                continue
            key = stripped.split("=", 1)[0].strip()
            if key in deletes:
                continue
            if key in remaining:
                output.append(f"{key}={remaining.pop(key)}")
                continue
            output.append(line)
        appended = [key for key in remaining]
        if appended:
            if output and output[-1].strip():
                output.append("")
            output.append("# 由网页面板添加的自定义平台 / 配置项")
            for key in appended:
                output.append(f"{key}={remaining[key]}")
        text = "\n".join(output) + "\n"
        if self.env_path.is_file():
            backup_config(self.env_path, self.backup_dir, max_backups=30)
        _atomic_write(self.env_path, text)
        for key in deletes:
            os.environ.pop(key, None)
        for key, value in updates.items():
            os.environ[key] = value
        return self.read()


#: 角色 -> 面板显示名
#: 角色 -> 期望的模型类型（面板按类型排序/标注，不强制限制）
ROLE_MODEL_TYPES: dict[str, str] = {
    "primary_chat_model": "chat",
    "agent_model_1": "chat",
    "agent_model_2": "chat",
    "agent_model_3": "chat",
    "vision_model": "vision",
    "tts_model": "tts",
    "creator_image_models": "image",
}


ROLE_LABELS: dict[str, str] = {
    "primary_chat_model": "主对话模型（Agent 编号 0）",
    "agent_model_1": "Agent 模型编号 1",
    "agent_model_2": "Agent 模型编号 2",
    "agent_model_3": "Agent 模型编号 3",
    "vision_model": "视觉 / 图像识别模型",
    "tts_model": "语音（TTS）模型",
    "creator_image_models": "创作者生图模型（可多个）",
}


def models_view(config: Any = None) -> dict[str, Any]:
    """模型库 + 调用方分配 + 平台凭据状态（用于面板展示与排查）。

    config 为运行中的配置代理时展示模型库与分配关系；否则只展示运行时注册表。
    """
    from neobot_chat import get_model_registry

    registry = get_model_registry()
    registered_names = set(registry.names)
    platforms: dict[str, dict[str, Any]] = {}

    def platform_payload(provider: str) -> dict[str, Any]:
        platform = EnvConfig.get_api_platform_config(provider) if provider else None
        if platform is None:
            return {"name": provider or "", "url": "", "has_key": False}
        payload = {
            "name": platform.name,
            "url": platform.url or "",
            "has_key": bool(platform.api_key),
        }
        platforms[platform.name] = payload
        return payload

    models_config = getattr(config, "models", None) if config is not None else None
    library: list[dict[str, Any]] = []
    assignments: dict[str, Any] = {}
    roles: list[dict[str, Any]] = []

    if models_config is not None and hasattr(models_config, "iter_definitions"):
        by_key = models_config.by_key()
        assigned_keys = {key for _role, key in models_config.assignments.items()}
        for key, definition in models_config.iter_definitions():
            platform = platform_payload(str(getattr(definition, "provider", "") or ""))
            library.append(
                {
                    "key": key,
                    "description": str(getattr(definition, "description", "") or ""),
                    "provider": str(getattr(definition, "provider", "") or ""),
                    "model_name": str(getattr(definition, "model_name", "") or ""),
                    "model_type": str(getattr(definition, "model_type", "chat") or "chat"),
                    "type_label": str(
                        getattr(definition, "type_label", "")
                        or MODEL_TYPE_LABELS.get(
                            str(getattr(definition, "model_type", "chat") or "chat"),
                            str(getattr(definition, "model_type", "") or ""),
                        )
                    ),
                    "native_vision": bool(getattr(definition, "native_vision", False)),
                    "use_system_proxy": bool(
                        getattr(definition, "use_system_proxy", False)
                    ),
                    "has_balance_hint": bool(
                        str(getattr(definition, "balance_query_hint", "") or "").strip()
                    ),
                    "assigned": key in assigned_keys,
                    "registered": key in registered_names,
                    "url_configured": bool(platform.get("url")),
                    "key_configured": bool(platform.get("has_key")),
                    # 完整条目（供面板编辑；模型条目不含密钥）
                    "entry": _jsonable(definition),
                }
            )
        assignments = {
            "roles": {
                role: models_config.assignments.role_key(role)
                for role in models_config.assignments.SINGLE_ROLES
            },
            "creator_image_models": list(models_config.assignments.image_keys()),
        }
        for role in models_config.assignments.SINGLE_ROLES:
            key = models_config.assignments.role_key(role)
            definition = by_key.get(key)
            roles.append(
                {
                    "role": role,
                    "label": ROLE_LABELS.get(role, role),
                    "key": key,
                    "missing": definition is None,
                    "description": str(getattr(definition, "description", "") or "") if definition else "",
                    "provider": str(getattr(definition, "provider", "") or "") if definition else "",
                    "model_name": str(getattr(definition, "model_name", "") or "") if definition else "",
                    "registered": key in registered_names,
                }
            )
        image_roles = [
            {
                "role": "creator_image_models",
                "label": ROLE_LABELS["creator_image_models"],
                "key": key,
                "missing": by_key.get(key) is None,
                "description": str(getattr(by_key.get(key), "description", "") or "") if by_key.get(key) else "",
                "provider": str(getattr(by_key.get(key), "provider", "") or "") if by_key.get(key) else "",
                "model_name": str(getattr(by_key.get(key), "model_name", "") or "") if by_key.get(key) else "",
                "registered": key in registered_names,
            }
            for key in models_config.assignments.image_keys()
        ]
        roles.extend(image_roles)

    # 运行时注册表（可能包含库中没有的旧式条目）
    registered: list[dict[str, Any]] = []
    for name, item in registry.items():
        platform = platform_payload(str(getattr(item, "provider_name", "") or ""))
        registered.append(
            {
                "name": name,
                "description": str(getattr(item, "description", "") or ""),
                "provider": str(getattr(item, "provider_name", "") or ""),
                "model_name": str(getattr(item, "model_name", "") or ""),
                "native_vision": bool(getattr(item, "native_vision", False)),
                "url_configured": bool(platform.get("url")),
                "key_configured": bool(platform.get("has_key")),
            }
        )

    provider_names: set[str] = set(EnvConfig.PLATFORM_NAME_ALIASES.values())
    for field_obj in fields(EnvConfig):
        env_key = str(field_obj.metadata.get("env_key") or field_obj.name.upper())
        if env_key.endswith("_URL"):
            provider_names.add(env_key[: -len("_URL")])
    def _canonical(name: str) -> str:
        text = str(name or "").strip()
        if not text:
            return ""
        try:
            return str(EnvConfig._normalize_platform_name(text))
        except Exception:
            return text

    for item in library:
        name = _canonical(item.get("provider"))
        if name:
            provider_names.add(name)
    for item in registered:
        name = _canonical(item.get("provider"))
        if name:
            provider_names.add(name)

    model_name_options = sorted(
        {
            *(str(item.get("model_name") or "").strip() for item in library),
            *(str(item.get("model_name") or "").strip() for item in registered),
        }
        - {""}
    )

    roles_meta = [
        {
            "role": role,
            "label": ROLE_LABELS.get(role, role),
            "multi": False,
            "required": role not in ("vision_model", "tts_model"),
            "model_type": ROLE_MODEL_TYPES.get(role, "chat"),
            "model_type_label": MODEL_TYPE_LABELS.get(
                ROLE_MODEL_TYPES.get(role, "chat"), ""
            ),
        }
        for role in ModelAssignments.SINGLE_ROLES
    ]
    roles_meta.append(
        {
            "role": "creator_image_models",
            "label": ROLE_LABELS["creator_image_models"],
            "multi": True,
            "required": False,
            "model_type": ROLE_MODEL_TYPES["creator_image_models"],
            "model_type_label": MODEL_TYPE_LABELS.get(
                ROLE_MODEL_TYPES["creator_image_models"], ""
            ),
        }
    )

    return {
        "library": library,
        "assignments": assignments,
        "roles": roles,
        "roles_meta": roles_meta,
        "role_labels": ROLE_LABELS,
        "entry_schema": describe_dataclass(ModelDefinition, None),
        "provider_options": sorted(provider_names, key=str.casefold),
        "model_name_options": model_name_options,
        "model_type_labels": dict(MODEL_TYPE_LABELS),
        "role_model_types": dict(ROLE_MODEL_TYPES),
        "registered": registered,
        "platforms": sorted(platforms.values(), key=lambda item: item["name"]),
    }

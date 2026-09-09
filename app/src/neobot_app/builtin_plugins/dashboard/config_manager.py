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
from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.config.schemas.env import EnvConfig

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
    """把 dataclass 结构转换为前端可渲染的字段描述。"""
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
        }
        if is_dataclass(target):
            actual_schema = target
            if is_dataclass(value) and isinstance(value, target):
                actual_schema = type(value)
            item["kind"] = "group"
            item["fields"] = describe_dataclass(actual_schema, value, (*path, name))
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
        return {
            "path": str(self.config_path),
            "revision": self.revision(),
            "source": source,
            "config": _jsonable(instance),
            "raw": _jsonable(parsed),
            "schema": describe_dataclass(BotConfig, instance),
            "version": str(getattr(instance, "version", "")),
            "form_supported": True,
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
            _merge_into_document(document, _diff_document(current, config or {}))
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
    ) -> dict[str, Any]:
        """模型库增删改 + 调用方分配，只改动 config.toml 的 [models] 段。"""
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
                raise ConfigValidationError(
                    [{"path": "models.registry.key", "message": "模型 key 不能为空"}]
                )
            for index, item in enumerate(library):
                if str(item.get("key") or "") == entry["key"]:
                    library[index] = {**item, **entry}
                    break
            else:
                library.append(entry)

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
        config_errors = self.validate(config=new_config)
        if config_errors:
            raise ConfigValidationError(config_errors)

        _merge_into_document(document, _diff_document(current, new_config))
        if self.config_path.is_file():
            backup_config(self.config_path, self.backup_dir, max_backups=max_backups)
        source = tomlkit.dumps(document)
        _atomic_write(self.config_path, source if source.endswith("\n") else source + "\n")
        return self.read()


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


def _diff_document(current: Any, new: Any) -> Any:
    """只保留相对当前文件真正变化的键，避免整份重写丢掉注释与顺序。"""
    if not isinstance(current, dict) or not isinstance(new, dict):
        return new
    changes: dict[str, Any] = {}
    for key, value in new.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            nested = _diff_document(current[key], value)
            if nested:
                changes[key] = nested
        elif current.get(key, _MISSING) != value:
            changes[key] = value
    for key in current:
        if key not in new:
            changes[key] = _DELETE
    return changes


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
        else:
            document[key] = tomlkit.item(value)


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
                    "native_vision": bool(getattr(definition, "native_vision", False)),
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

    from neobot_app.config.schemas.bot import ModelAssignments, ModelDefinition

    roles_meta = [
        {
            "role": role,
            "label": ROLE_LABELS.get(role, role),
            "multi": False,
            "required": role not in ("vision_model", "tts_model"),
        }
        for role in ModelAssignments.SINGLE_ROLES
    ]
    roles_meta.append(
        {
            "role": "creator_image_models",
            "label": ROLE_LABELS["creator_image_models"],
            "multi": True,
            "required": False,
        }
    )

    return {
        "library": library,
        "assignments": assignments,
        "roles": roles,
        "roles_meta": roles_meta,
        "role_labels": ROLE_LABELS,
        "entry_schema": describe_dataclass(ModelDefinition, None),
        "registered": registered,
        "platforms": sorted(platforms.values(), key=lambda item: item["name"]),
    }

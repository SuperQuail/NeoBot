"""「.env」的在线管理：保留注释与顺序，按行替换，密钥默认打码。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from neobot_app.builtin_plugins.dashboard.security import (
    SECRET_PLACEHOLDER,
    is_sensitive_key,
)
from neobot_app.config.loader.backup import backup_config
from neobot_app.config.schemas.env import EnvConfig

from .errors import ConfigConflictError, ConfigValidationError
from .files import _atomic_write, _revision_of
from .schema import _is_optional

ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
                    "in_file": True,
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
                    "in_file": False,
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

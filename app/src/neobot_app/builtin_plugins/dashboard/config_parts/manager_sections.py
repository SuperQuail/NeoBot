"""BotConfigManager 的分区编辑：官方插件配置段与插件代理。"""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.schemas.bot import BotConfig

from .errors import ConfigConflictError, ConfigValidationError
from .files import _atomic_write
from .schema import _coerce_payload, _jsonable
from .toml import _diff_document, _filter_managed, _merge_into_document


class _SectionMixin:
    """官方插件配置段与插件系统代理设置的编辑。"""

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
        # _filter_managed 会深拷贝一份用于校验；落盘用的是 new_config，
        # 所以必须在它上面转换，不能只转副本。
        new_config = _coerce_payload(BotConfig, new_config)
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

"""BotConfigManager 的文件生命周期：读取、校验、备份与原子保存。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.loader.converter import dict_to_dataclass
from neobot_app.config.model_params import (
    apply_model_param_catalog,
    fold_model_params_in_config,
)
from neobot_app.config.schemas.bot import BotConfig

from .describe import describe_dataclass
from .errors import ConfigConflictError, ConfigValidationError
from .files import _atomic_write, _revision_of
from .schema import _coerce_payload, _jsonable, _validate_payload
from .toml import (
    _diff_document,
    _mask_schema_defaults,
    _mask_sensitive_leaves,
    _mask_toml_source,
    _merge_into_document,
    _restore_masked_secrets,
    _restore_masked_source,
)

MAX_STRING_LENGTH = 200_000


class _ConfigIOMixin:
    """config.toml 的读取、校验、备份与原子保存。"""

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
        # spec(4) Part B：两条渲染路径共用同一个后处理器（本体配置页里的
        # models.registry 是 kind=model_list，条目字段同样来自 describe_dataclass）
        schema_payload = apply_model_param_catalog(describe_dataclass(BotConfig, instance))
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
            # 面板伪字段（settings.params）先折叠回 enabled_params / extra_body / 参数值
            parsed = fold_model_params_in_config(config)
            # 校验按钮必须与保存做同一份类型转换，否则「校验通过、保存 400」
            parsed = _coerce_payload(BotConfig, parsed)
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
        if source is None and config is not None:
            config = fold_model_params_in_config(config)
            # 落盘的 submitted 必须含转换结果：否则字符串 "0.5" 会写进 config.toml
            config = _coerce_payload(BotConfig, config)
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

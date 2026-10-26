"""BotConfigManager 的模型库 / 调用方分配编辑。"""

from __future__ import annotations

from typing import Any

import tomlkit

from neobot_app.config.loader.backup import backup_config
from neobot_app.config.model_params import fold_params_into_settings
from neobot_app.config.schemas.bot import BotConfig

from .errors import ConfigConflictError, ConfigValidationError
from .files import _atomic_write
from .models import ROLE_LABELS, _assignment_items, _derive_model_key
from .schema import _coerce_payload, _jsonable
from .toml import _diff_document, _filter_managed, _merge_into_document


class _ModelsMixin:
    """模型库条目与调用方分配的编辑。"""

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
        library = [
            {**item, "settings": fold_params_into_settings(item["settings"])}
            if isinstance(item.get("settings"), dict)
            else item
            for item in library
        ]
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

        `upsert` 未提供 model_ref（引用名）时，按模型名自动生成唯一引用名；
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
                for role, model_ref in _assignment_items(current_assignments)
                if model_ref == target
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
            if not any(str(item.get("model_ref") or "") == target for item in library):
                raise ConfigValidationError(
                    [{"path": "models.registry", "message": f"模型库中不存在 {target}"}]
                )
            library = [item for item in library if str(item.get("model_ref") or "") != target]
        elif upsert is not None:
            entry = {str(key): value for key, value in dict(upsert).items()}
            if isinstance(entry.get("settings"), dict):
                # 面板伪字段（settings.params）折叠回 enabled_params / extra_body / 参数值
                entry["settings"] = fold_params_into_settings(entry["settings"])
            entry["model_ref"] = normalize_model_key(str(entry.get("model_ref") or ""))
            if not entry["model_ref"]:
                # 面板不暴露引用名：按「模型名」自动生成（重名时追加序号）
                entry["model_ref"] = _derive_model_key(
                    str(entry.get("model_name") or ""),
                    str(entry.get("model_type") or "chat"),
                    {str(item.get("model_ref") or "") for item in library},
                )
            for index, item in enumerate(library):
                if str(item.get("model_ref") or "") == entry["model_ref"]:
                    library[index] = {**item, **entry}
                    break
            else:
                library.append(entry)
            if resolved is not None:
                resolved["model_ref"] = entry["model_ref"]

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
            library_refs = {str(item.get("model_ref") or "") for item in library}
            for role in ModelAssignments.SINGLE_ROLES:
                if role not in assignments:
                    continue
                model_ref = str(assignments.get(role) or "").strip()
                if model_ref and model_ref not in library_refs:
                    errors.append(
                        {
                            "path": f"models.assignments.{role}",
                            "message": f"模型库中不存在引用名: {model_ref}",
                        }
                    )
                if not model_ref and role not in ("vision_model", "tts_model"):
                    errors.append(
                        {"path": f"models.assignments.{role}", "message": "该调用方必须指定模型"}
                    )
                current_assignments[role] = model_ref
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
                    for model_ref in cleaned:
                        if model_ref not in library_refs:
                            errors.append(
                                {
                                    "path": "models.assignments.creator_image_models",
                                    "message": f"模型库中不存在引用名: {model_ref}",
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
        # 同 update_section：转换后的 new_config 才是落盘依据
        new_config = _coerce_payload(BotConfig, new_config)
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

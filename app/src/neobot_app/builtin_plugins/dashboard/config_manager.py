"""本体配置在线管理：config.toml 与 .env 的读取、校验、备份与写入。

设计目标（替换旧内置控制台的弱配置能力）：
- 结构化：从 dataclass 生成字段描述，前端可渲染成分组表单（含嵌套对象与对象数组）。
- 可校验：保存前严格校验类型与取值，错误定位到具体路径，不会写入半成品。
- 可回滚：每次写入前备份到 config_backup/，写入使用临时文件 + 原子替换。
- 可并发：revision（内容哈希）检测冲突，避免两个标签页互相覆盖。
- 可审计：密钥默认打码，单独接口按需显示并记录日志。

实现按主题拆在 config_parts/ 下，本模块保留公开入口与 re-export。
"""

from __future__ import annotations

from .config_parts.describe import (
    _collect_scalar_fields,
    describe_dataclass,
    describe_pydantic_model,
)
from .config_parts.env_file import ENV_KEY_RE, EnvEntry, EnvFileManager
from .config_parts.errors import ConfigConflictError, ConfigValidationError
from .config_parts.files import _atomic_write, _revision_of
from .config_parts.manager_io import MAX_STRING_LENGTH, _ConfigIOMixin
from .config_parts.manager_models import _ModelsMixin
from .config_parts.manager_sections import _SectionMixin
from .config_parts.models import (
    ROLE_LABELS,
    ROLE_MODEL_TYPES,
    _assignment_items,
    _derive_model_key,
    models_view,
)
from .config_parts.schema import (
    _COERCIBLE_TYPES,
    _UNION_ORIGINS,
    _coerce_leaf,
    _coerce_payload,
    _default_of,
    _inner_types,
    _is_optional,
    _jsonable,
    _matches,
    _resolve_actual_schema,
    _type_name,
    _validate_payload,
)
from .config_parts.toml import (
    _DELETE,
    _FREE_MAPPING,
    _MANAGED_TREES,
    _MISSING,
    _SECRET_PLACEHOLDER,
    _TOML_KEY_LINE_RE,
    _TOML_SECTION_RE,
    _ListOfTables,
    _diff_document,
    _diff_sequence,
    _filter_managed,
    _is_quoted,
    _is_table_array,
    _iter_secret_lines,
    _managed_tree,
    _mask_schema_defaults,
    _mask_sensitive_leaves,
    _mask_toml_source,
    _merge_into_document,
    _merge_sequence,
    _restore_masked_secrets,
    _restore_masked_source,
)


class BotConfigManager(_ConfigIOMixin, _SectionMixin, _ModelsMixin):
    """config.toml 的在线管理。"""


__all__ = [
    "BotConfigManager",
    "ConfigConflictError",
    "ConfigValidationError",
    "ENV_KEY_RE",
    "EnvEntry",
    "EnvFileManager",
    "MAX_STRING_LENGTH",
    "ROLE_LABELS",
    "ROLE_MODEL_TYPES",
    "_COERCIBLE_TYPES",
    "_DELETE",
    "_FREE_MAPPING",
    "_ListOfTables",
    "_MANAGED_TREES",
    "_MISSING",
    "_SECRET_PLACEHOLDER",
    "_TOML_KEY_LINE_RE",
    "_TOML_SECTION_RE",
    "_UNION_ORIGINS",
    "_assignment_items",
    "_atomic_write",
    "_coerce_leaf",
    "_coerce_payload",
    "_collect_scalar_fields",
    "_default_of",
    "_derive_model_key",
    "_diff_document",
    "_diff_sequence",
    "_filter_managed",
    "_inner_types",
    "_is_optional",
    "_is_quoted",
    "_is_table_array",
    "_iter_secret_lines",
    "_jsonable",
    "_managed_tree",
    "_mask_schema_defaults",
    "_mask_sensitive_leaves",
    "_mask_toml_source",
    "_matches",
    "_merge_into_document",
    "_merge_sequence",
    "_resolve_actual_schema",
    "_restore_masked_secrets",
    "_restore_masked_source",
    "_revision_of",
    "_type_name",
    "_validate_payload",
    "describe_dataclass",
    "describe_pydantic_model",
    "models_view",
]

"""spec(4) Part B：模型注册参数目录 + 可选参数启用清单。

本模块是配置层与面板共用的唯一真相源：

- MODEL_PARAM_CATALOG：可选参数目录（后端常量表）。每项含
  name / group / label / description / type / default / options / scope。
- apply_model_param_catalog：共享后处理器。在 describe_dataclass 的输出上
  递归定位 settings 组，把目录内的可选字段标记为 hidden，并在组末尾注入
  kind="model_params" 的伪字段（目录内嵌其中，因此不新增任何顶层载荷键）。
  模型库面板（models_view().entry_schema）与本体配置页（read().schema 里的
  models.registry[].items[].fields）两条渲染路径都必须过它。
- resolve_enabled_params：按 enabled_params 与 scope 归类（启用 / 未知 / 不适用），
  请求体下发与面板警告共用同一判据。
- fold_params_into_settings：把面板伪字段写进草稿的 settings.params 折叠回
  enabled_params / extra_body / 各可选参数值（本体配置页的整段保存路径）。
- infer_enabled_params：R12 旧配置迁移（缺 enabled_params 时按“值 ≠ 默认值”推断一次）。

scope 匹配一律走归一化值：provider 用 _normalize_provider_kind（neobot_chat），
model_type 用 normalize_model_type（config.schemas.bot），不做原始字符串白名单。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from neobot_app.config.schemas.bot import (
    DeepSeekModelSettings,
    ModelSettings,
    normalize_model_type,
)
from neobot_chat.models import _normalize_provider_kind

#: 参数分组（前端按下拉分组展示）
MODEL_PARAM_GROUPS: Tuple[str, ...] = ("openai", "deepseek", "image", "custom")

#: 基础通用参数：面板常显、不可移除（spec 4.12-D9 / Q5）
BASE_PARAM_NAMES: Tuple[str, ...] = (
    "temperature",
    "max_output_tokens",
    "timeout_seconds",
    "top_p",
)

#: 伪字段名（面板参数目录的载体）
PARAM_FIELD_NAME = "params"

#: DeepSeek 思考参数只对「对话 / 视觉 / 其它」模型有意义：
#  生图 payload 走 drawing/service.py（与聊天参数无关），TTS 也不接受思考参数。
#  见 R13 / A18：DeepSeek 思考参数不出现在生图 / TTS 模型的可选列表里。
_NON_IMAGE_MODEL_TYPES = ["chat", "vision", "other"]

#: 可选参数目录定义：name -> (group, label, scope)
_CATALOG_SPEC: Tuple[Tuple[str, str, str, Dict[str, Any]], ...] = (
    (
        "frequency_penalty",
        "openai",
        "频率惩罚",
        {"providers": ["openai", "deepseek"]},
    ),
    (
        "presence_penalty",
        "openai",
        "存在惩罚",
        {"providers": ["openai", "deepseek"]},
    ),
    ("image_api", "image", "生图接口形态", {"model_types": ["image"]}),
    (
        "image_reference_param",
        "image",
        "参考图字段名",
        {"model_types": ["image"]},
    ),
    (
        "deepseek_thinking_mode",
        "deepseek",
        "思考模式",
        {"providers": ["deepseek"], "model_types": _NON_IMAGE_MODEL_TYPES},
    ),
    (
        "deepseek_reasoning_effort",
        "deepseek",
        "思考强度",
        {"providers": ["deepseek"], "model_types": _NON_IMAGE_MODEL_TYPES},
    ),
    (
        "deepseek_random_thinking_probability",
        "deepseek",
        "随机思考概率",
        {"providers": ["deepseek"], "model_types": _NON_IMAGE_MODEL_TYPES},
    ),
)

#: 私有键前缀：用户自定义参数（extra_body）不得使用（spec 4.6）
RESERVED_EXTRA_BODY_PREFIX = "__"


def _type_label(field_type: Any) -> str:
    if field_type is float:
        return "float"
    if field_type is int:
        return "int"
    if field_type is bool:
        return "bool"
    if field_type is str:
        return "str"
    return "str"


def _schema_field(name: str) -> Optional[dataclasses.Field]:
    """在 ModelSettings / DeepSeekModelSettings 里查字段（后者是前者的子类）。"""
    for schema in (DeepSeekModelSettings, ModelSettings):
        for item in dataclasses.fields(schema):
            if item.name == name:
                return item
    return None


def _build_catalog_entry(
    name: str, group: str, label: str, scope: Dict[str, Any]
) -> Dict[str, Any]:
    field_obj = _schema_field(name)
    metadata: Dict[str, Any] = dict(getattr(field_obj, "metadata", {}) or {})
    if field_obj is None:
        default: Any = None
        field_type: Any = str
    else:
        if field_obj.default is not dataclasses.MISSING:
            default = field_obj.default
        elif field_obj.default_factory is not dataclasses.MISSING:
            default = field_obj.default_factory()
        else:
            default = None
        field_type = field_obj.type
    entry: Dict[str, Any] = {
        "name": name,
        "group": group,
        "label": label,
        "description": str(metadata.get("description", "") or ""),
        "type": _type_label(field_type),
        "default": default,
        "options": [str(item) for item in metadata.get("options", [])],
    }
    if scope:
        entry["scope"] = dict(scope)
    return entry


#: 可选参数目录（顺序即前端展示顺序）
MODEL_PARAM_CATALOG: List[Dict[str, Any]] = [
    _build_catalog_entry(name, group, label, scope)
    for name, group, label, scope in _CATALOG_SPEC
]

_CATALOG_BY_NAME: Dict[str, Dict[str, Any]] = {
    str(entry["name"]): entry for entry in MODEL_PARAM_CATALOG
}


def catalog_entry(name: str) -> Optional[Dict[str, Any]]:
    """按名字取目录项（不在目录里返回 None）。"""
    return _CATALOG_BY_NAME.get(str(name or ""))


def catalog_names() -> Tuple[str, ...]:
    return tuple(_CATALOG_BY_NAME)


# ----------------------------------------------------------------------
# scope 归一化与匹配
# ----------------------------------------------------------------------

def normalize_param_provider(value: Any) -> str:
    """归一 provider kind（与 chat 层 _normalize_provider_kind 同判据）。"""
    return _normalize_provider_kind(str(value or ""))


def params_scope_applies(
    entry: Dict[str, Any],
    *,
    provider: Any,
    model_type: Any,
) -> bool:
    """目录项是否适用于该 provider / model_type；无 scope 键 = 全适用。"""
    scope = entry.get("scope")
    if not isinstance(scope, dict) or not scope:
        return True
    providers = scope.get("providers")
    if isinstance(providers, (list, tuple)) and providers:
        wanted = {normalize_param_provider(item) for item in providers}
        if normalize_param_provider(provider) not in wanted:
            return False
    model_types = scope.get("model_types")
    if isinstance(model_types, (list, tuple)) and model_types:
        wanted_types = {normalize_model_type(item) for item in model_types}
        if normalize_model_type(model_type) not in wanted_types:
            return False
    return True


def applicable_catalog(*, provider: Any, model_type: Any) -> List[Dict[str, Any]]:
    """按 scope 过滤后的可添加候选项（无 scope 的参数始终保留）。"""
    return [
        entry
        for entry in MODEL_PARAM_CATALOG
        if params_scope_applies(entry, provider=provider, model_type=model_type)
    ]


def resolve_enabled_params(
    enabled: Sequence[Any] | None,
    *,
    provider: Any,
    model_type: Any,
) -> Tuple[List[str], List[str], List[str]]:
    """把 enabled_params 归类为（可用 / 未知 / 不适用）。

    未知项（不在目录里，只可能来自手改 TOML）与不适用项（scope 不匹配）都必须被
    调用方记 warning 后忽略——“配了却不生效”不许静默。
    """
    applied: List[str] = []
    unknown: List[str] = []
    inapplicable: List[str] = []
    for raw in enabled or []:
        name = str(raw or "").strip()
        if not name:
            continue
        entry = catalog_entry(name)
        if entry is None:
            unknown.append(name)
            continue
        if not params_scope_applies(entry, provider=provider, model_type=model_type):
            inapplicable.append(name)
            continue
        applied.append(name)
    return applied, unknown, inapplicable


# ----------------------------------------------------------------------
# 共享后处理器：describe_dataclass 输出 -> hidden 标记 + 伪字段
# ----------------------------------------------------------------------

def _settings_context(fields: List[Dict[str, Any]]) -> Tuple[Any, Any]:
    """取同层 provider / model_type 的当前值（伪字段 scope 过滤的兜底）。"""
    provider: Any = ""
    model_type: Any = ""
    for item in fields:
        if not isinstance(item, dict):
            continue
        if item.get("name") == "provider" and not provider:
            provider = item.get("value") or item.get("default") or ""
        elif item.get("name") == "model_type" and not model_type:
            model_type = item.get("value") or item.get("default") or ""
    return provider, model_type


def _params_pseudo_field(
    group: Dict[str, Any],
    *,
    provider: Any,
    model_type: Any,
) -> Dict[str, Any]:
    raw_value = group.get("value")
    value: Dict[str, Any] = raw_value if isinstance(raw_value, dict) else {}
    enabled_raw = value.get("enabled_params")
    enabled = [str(item) for item in enabled_raw] if isinstance(enabled_raw, list) else []
    extra_body = value.get("extra_body")
    if not isinstance(extra_body, dict):
        extra_body = {}
    applied, unknown, inapplicable = resolve_enabled_params(
        enabled, provider=provider, model_type=model_type
    )
    param_values = {name: value.get(name) for name in catalog_names() if name in value}
    group_path = [str(item) for item in (group.get("path") or [])]
    return {
        "name": PARAM_FIELD_NAME,
        "path": [*group_path, PARAM_FIELD_NAME],
        "label": "模型参数",
        "description": (
            "基础参数常显；可选参数点「添加参数」按当前模型的类型 / 供应商过滤后加入，"
            "未加入的可选参数不会下发到请求体；自定义参数原样并入请求体。"
        ),
        "kind": "model_params",
        "required": False,
        "default": None,
        "readonly": False,
        "hidden": False,
        "base_param_names": list(BASE_PARAM_NAMES),
        "enabled_params": applied,
        "catalog": [dict(entry) for entry in MODEL_PARAM_CATALOG],
        "unknown_params": unknown,
        "inapplicable_params": inapplicable,
        "extra_body": extra_body,
        # 前端下拉的 scope 过滤基准（模型库面板会用草稿里的当前值覆盖）
        "provider": str(provider or ""),
        "model_type": str(model_type or ""),
        # 标准 value 键：伪字段的可编辑载荷（enabled_params / extra_body / 各参数值）
        "value": {
            "enabled_params": applied,
            "extra_body": extra_body,
            "values": param_values,
        },
    }


def _process_settings_group(
    group: Dict[str, Any],
    *,
    provider: Any,
    model_type: Any,
) -> None:
    fields = group.get("fields")
    if not isinstance(fields, list):
        return
    for item in fields:
        if isinstance(item, dict) and item.get("name") in _CATALOG_BY_NAME:
            item["hidden"] = True
    kept = [
        item
        for item in fields
        if not (isinstance(item, dict) and item.get("name") == PARAM_FIELD_NAME)
    ]
    kept.append(_params_pseudo_field(group, provider=provider, model_type=model_type))
    group["fields"] = kept


def apply_model_param_catalog(
    fields: List[Dict[str, Any]],
    *,
    provider: Any = None,
    model_type: Any = None,
) -> List[Dict[str, Any]]:
    """共享后处理器：递归定位 settings 组，隐藏可选字段并注入 model_params 伪字段。

    两条渲染路径（模型库面板的 entry_schema、本体配置页 read().schema 的
    model_list 条目字段）都必须经过本函数，以保证行为一致。
    """
    if not isinstance(fields, list):
        return fields
    local_provider, local_model_type = _settings_context(fields)
    provider_value = provider if provider not in (None, "") else local_provider
    model_type_value = model_type if model_type not in (None, "") else local_model_type
    for item in fields:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        if kind == "group":
            if item.get("name") == "settings":
                _process_settings_group(
                    item, provider=provider_value, model_type=model_type_value
                )
            else:
                apply_model_param_catalog(
                    item.get("fields") or [],
                    provider=provider_value,
                    model_type=model_type_value,
                )
        elif kind == "model_list":
            for entry in item.get("items") or []:
                if isinstance(entry, dict):
                    apply_model_param_catalog(entry.get("fields") or [])
            apply_model_param_catalog(item.get("item_fields") or [])
    return fields


# ----------------------------------------------------------------------
# 面板伪字段 -> 真实配置字段的折叠
# ----------------------------------------------------------------------

def fold_params_into_settings(settings: Any) -> Any:
    """把 settings.params 折叠回 enabled_params / extra_body / 各参数值。

    面板（本体配置页）不区分 kind，伪字段的值会以 settings.params 的形状回到
    草稿；保存前必须折叠，否则 params 会被当作未知配置项。
    """
    if not isinstance(settings, dict):
        return settings
    if PARAM_FIELD_NAME not in settings:
        return settings
    params = settings.get(PARAM_FIELD_NAME)
    folded = {
        key: value for key, value in settings.items() if key != PARAM_FIELD_NAME
    }
    if not isinstance(params, dict):
        return folded
    enabled_raw = params.get("enabled_params")
    if isinstance(enabled_raw, list):
        folded["enabled_params"] = [
            str(item) for item in enabled_raw if str(item or "").strip()
        ]
    extra_body = params.get("extra_body")
    if isinstance(extra_body, dict):
        folded["extra_body"] = dict(extra_body)
    values = params.get("values")
    if isinstance(values, dict):
        for raw_name, value in values.items():
            name = str(raw_name or "").strip()
            if not name or catalog_entry(name) is None:
                # 未知参数不落盘（后端对 enabled_params 里的未知项只记 warning 忽略）
                continue
            folded[name] = value
    return folded


def fold_model_params_in_config(config: Any) -> Any:
    """整份配置字典里的 models.registry[*].settings.params 折叠。"""
    if not isinstance(config, dict):
        return config
    models = config.get("models")
    if not isinstance(models, dict):
        return config
    registry = models.get("registry")
    if not isinstance(registry, list):
        return config
    changed = False
    normalized: List[Any] = []
    for entry in registry:
        if isinstance(entry, dict) and isinstance(entry.get("settings"), dict):
            before = entry["settings"]
            after = fold_params_into_settings(before)
            if after is not before:
                changed = True
                entry = {**entry, "settings": after}
        normalized.append(entry)
    if not changed:
        return config
    return {**config, "models": {**models, "registry": normalized}}


def extra_body_reserved_keys(extra_body: Any) -> List[str]:
    """返回用户自定义参数里非法的键（__ 前缀，内部键命名空间）。"""
    if not isinstance(extra_body, dict):
        return []
    return sorted(
        str(key) for key in extra_body if str(key).startswith(RESERVED_EXTRA_BODY_PREFIX)
    )


# ----------------------------------------------------------------------
# R12：旧配置迁移（缺 enabled_params 时按“值 ≠ schema 默认值”推断一次）
# ----------------------------------------------------------------------

_inferred_keys: Set[str] = set()


def _defaults() -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for name in catalog_names():
        field_obj = _schema_field(name)
        if field_obj is None:
            continue
        if field_obj.default is not dataclasses.MISSING:
            defaults[name] = field_obj.default
        elif field_obj.default_factory is not dataclasses.MISSING:
            defaults[name] = field_obj.default_factory()
    return defaults


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left) == float(right)
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() == right.strip()
    return left == right


def infer_enabled_params(settings_raw: Any) -> List[str]:
    """按“TOML 值 ≠ schema 默认值”推断已启用的可选参数（保持目录顺序）。"""
    if not isinstance(settings_raw, dict):
        return []
    defaults = _defaults()
    inferred: List[str] = []
    for name in catalog_names():
        if name not in settings_raw:
            continue
        if name not in defaults:
            inferred.append(name)
            continue
        if not _same_value(settings_raw.get(name), defaults[name]):
            inferred.append(name)
    return inferred


def mark_inferred(keys: Any) -> None:
    """登记本次启动推断过的模型 key（面板据此提示「已按旧配置推断，请复核」）。"""
    for key in keys or []:
        text = str(key or "").strip()
        if text:
            _inferred_keys.add(text)


def is_inferred(key: Any) -> bool:
    return str(key or "").strip() in _inferred_keys


def inferred_keys() -> List[str]:
    return sorted(_inferred_keys)


def clear_inferred() -> None:
    _inferred_keys.clear()

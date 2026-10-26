"""模型库视图：运行中注册表、调用方分配与平台凭据状态。"""

from __future__ import annotations

import re
from dataclasses import fields
from typing import Any

from neobot_app.config.model_params import apply_model_param_catalog, is_inferred
from neobot_app.config.schemas.bot import (
    MODEL_TYPE_LABELS,
    ModelAssignments,
    ModelDefinition,
)
from neobot_app.config.schemas.env import EnvConfig

from .describe import describe_dataclass
from .schema import _jsonable


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
        by_ref = models_config.by_ref()
        assigned_refs = {ref for _role, ref in models_config.assignments.items()}
        for model_ref, definition in models_config.iter_definitions():
            platform = platform_payload(str(getattr(definition, "provider", "") or ""))
            library.append(
                {
                    # model_ref = 本机引用名（不发供应商）；model_name 才是发出去的模型名。
                    "model_ref": model_ref,
                    "display_name": str(
                        getattr(definition, "display_name", "") or ""
                    ),
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
                    "assigned": model_ref in assigned_refs,
                    "registered": model_ref in registered_names,
                    "url_configured": bool(platform.get("url")),
                    # 供应商 API Key 是否已配置（与引用名无关，别再叫 key_configured）
                    "api_key_configured": bool(platform.get("has_key")),
                    # 完整条目（供面板编辑；模型条目不含密钥）
                    "entry": _jsonable(definition),
                    # spec(4) Part B R12：本次启动按旧配置推断过 enabled_params
                    "params_inferred": is_inferred(model_ref),
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
            model_ref = models_config.assignments.role_key(role)
            definition = by_ref.get(model_ref)
            roles.append(
                {
                    "role": role,
                    "label": ROLE_LABELS.get(role, role),
                    "model_ref": model_ref,
                    "missing": definition is None,
                    "display_name": str(getattr(definition, "display_name", "") or "") if definition else "",
                    "provider": str(getattr(definition, "provider", "") or "") if definition else "",
                    "model_name": str(getattr(definition, "model_name", "") or "") if definition else "",
                    "registered": model_ref in registered_names,
                }
            )
        image_roles = [
            {
                "role": "creator_image_models",
                "label": ROLE_LABELS["creator_image_models"],
                "model_ref": image_ref,
                "missing": by_ref.get(image_ref) is None,
                "display_name": str(getattr(by_ref.get(image_ref), "display_name", "") or "") if by_ref.get(image_ref) else "",
                "provider": str(getattr(by_ref.get(image_ref), "provider", "") or "") if by_ref.get(image_ref) else "",
                "model_name": str(getattr(by_ref.get(image_ref), "model_name", "") or "") if by_ref.get(image_ref) else "",
                "registered": image_ref in registered_names,
            }
            for image_ref in models_config.assignments.image_keys()
        ]
        roles.extend(image_roles)

    # 运行时注册表（可能包含库中没有的旧式条目）
    registered: list[dict[str, Any]] = []
    for model_ref, item in registry.items():
        platform = platform_payload(str(getattr(item, "provider_name", "") or ""))
        registered.append(
            {
                "model_ref": model_ref,
                "display_name": str(getattr(item, "display_name", "") or ""),
                "provider": str(getattr(item, "provider_name", "") or ""),
                "model_name": str(getattr(item, "model_name", "") or ""),
                "native_vision": bool(getattr(item, "native_vision", False)),
                "url_configured": bool(platform.get("url")),
                "api_key_configured": bool(platform.get("has_key")),
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
        "entry_schema": apply_model_param_catalog(describe_dataclass(ModelDefinition, None)),
        "provider_options": sorted(provider_names, key=str.casefold),
        "model_name_options": model_name_options,
        "model_type_labels": dict(MODEL_TYPE_LABELS),
        "role_model_types": dict(ROLE_MODEL_TYPES),
        "registered": registered,
        "platforms": sorted(platforms.values(), key=lambda item: item["name"]),
    }

"""配置迁移"""

import re
from typing import Any

from neobot_app.config.loader import Config


@Config.migration(from_version="0.1.0", to_version="0.2.0")
def migrate_v1_to_v2(old: dict) -> dict:
    """迁移 0.1.0 -> 0.2.0 示例"""
    new: dict[str, Any] = {}

    # 迁移版本号
    new["version"] = "0.2.0"

    # 示例：如果旧版本有 secret_key，迁移到 app.secret_key
    if "secret_key" in old:
        if "app" not in new:
            new["app"] = {}
        new["app"]["secret_key"] = old["secret_key"]

    # 保留其他配置
    for key, value in old.items():
        if key not in ["secret_key", "version"]:
            new[key] = value

    return new


# 提示词系统重构:提示词模板从 config.toml 迁移到独立的提示词文件
# (data/prompts/ 目录,默认+自定义),config.toml 中不再保留提示词键。
# 已自定义过提示词的用户,可在升级后从 config_backup/ 中找回旧值,
# 并手动迁移到 data/prompts/custom/prompts.toml。
_PROMPT_KEYS = frozenset({
    "group_prompt_template",
    "friend_prompt_template",
    "long_reply_fallback_template",
    "group_chat_resume_prompt_template",
})


@Config.migration(from_version="0.3.0", to_version="0.4.0")
def migrate_v3_to_v4(old: dict) -> dict:
    """迁移 0.3.0 -> 0.4.0:清理 config.toml 中的提示词键(已迁移到独立文件)。"""
    new: dict[str, Any] = {"version": "0.4.0"}

    chat = old.get("chat")
    if isinstance(chat, dict):
        chat = {k: v for k, v in chat.items() if k not in _PROMPT_KEYS}
        if chat:
            new["chat"] = chat

    for key, value in old.items():
        if key in ("version", "chat"):
            continue
        new[key] = value

    return new


_LEGACY_ROLE_FIELDS = (
    "primary_chat_model",
    "agent_model_1",
    "agent_model_2",
    "agent_model_3",
    "vision_model",
    "tts_model",
)

_LEGACY_ROLE_DESCRIPTIONS = {
    "primary_chat_model": "主对话模型（Agent模型编号0）",
    "agent_model_1": "Agent模型编号1",
    "agent_model_2": "Agent模型编号2",
    "agent_model_3": "Agent模型编号3",
    "vision_model": "图像识别模型",
    "tts_model": "语音模型",
}


def _default_model_library_map() -> dict[str, dict[str, Any]]:
    """默认模型库：引用名 -> 条目字典（迁移时用于补齐旧配置缺失的角色）。"""
    from dataclasses import asdict

    from neobot_app.config.schemas.bot import _default_model_library

    return {item.model_ref: asdict(item) for item in _default_model_library()}


def _default_role_assignments() -> dict[str, str]:
    """默认调用方引用：角色 -> 默认模型条目引用名。"""
    from neobot_app.config.schemas.bot import ModelAssignments

    return dict(ModelAssignments().items())


def _slug_key(raw: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(raw or "").strip()).strip("-.")
    return (text or fallback)[:64]


@Config.migration(from_version="0.5.0", to_version="0.6.0")
def migrate_v5_to_v6(old: dict) -> dict:
    """迁移 0.5.0 -> 0.6.0：模型改为「模型库 + 调用方引用 key」。

    - 旧的内联角色配置（primary_chat_model/agent_model_*/vision_model/tts_model/
      creator_image_models）搬进 [[models.registry]]，key 由模型名自动生成；
    - [models.assignments] 记录各调用方引用的 key。
    """
    new: dict[str, Any] = {"version": "0.6.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    legacy_models = old.get("models")
    if not isinstance(legacy_models, dict):
        return new

    library: list[dict[str, Any]] = []
    used_keys: set[str] = set()

    def add_entry(entry: dict[str, Any], fallback_key: str) -> str:
        base = _slug_key(str(entry.get("model_name") or ""), fallback_key)
        key = base
        counter = 2
        while key in used_keys:
            key = f"{base}-{counter}"[:64]
            counter += 1
        used_keys.add(key)
        migrated = {name: value for name, value in entry.items() if name != "key"}
        migrated["key"] = key
        migrated.setdefault("description", _LEGACY_ROLE_DESCRIPTIONS.get(fallback_key, fallback_key))
        library.append(migrated)
        return key

    assignments: dict[str, Any] = {}
    for role in _LEGACY_ROLE_FIELDS:
        entry = legacy_models.get(role)
        if isinstance(entry, dict):
            assignments[role] = add_entry(entry, role)

    legacy_images = legacy_models.get("creator_image_models")
    if isinstance(legacy_images, list):
        image_keys = [
            add_entry(entry, f"image-{index + 1}")
            for index, entry in enumerate(legacy_images)
            if isinstance(entry, dict)
        ]
        if image_keys:
            assignments["creator_image_models"] = image_keys

    # 旧配置可能只写了部分角色：把未出现的角色补回默认模型库条目，
    # 否则 [models.assignments] 的默认值会引用到不存在的 key。
    defaults = _default_model_library_map()
    for role, key in _default_role_assignments().items():
        if role in assignments or key in used_keys:
            continue
        default_entry = defaults.get(key)
        if default_entry is None:
            continue
        used_keys.add(key)
        library.append(dict(default_entry))
        assignments[role] = key

    migrated_models: dict[str, Any] = {}
    if library:
        migrated_models["registry"] = library
    if assignments:
        migrated_models["assignments"] = assignments
    # 保留无法识别的其它模型字段，避免误删用户自定义内容
    for name, value in legacy_models.items():
        if name in _LEGACY_ROLE_FIELDS or name in ("creator_image_models", "registry", "assignments"):
            continue
        migrated_models[name] = value
    if migrated_models:
        new["models"] = migrated_models
    return new


@Config.migration(from_version="0.4.0", to_version="0.5.0")
def migrate_v4_to_v5(old: dict) -> dict:
    """迁移 0.4.0 -> 0.5.0。

    - [console] 双控制台合并为官方 dashboard 插件：面板设置不再写在本体配置里，
      由 plugin_config_migration 在加载配置前搬进插件数据目录，这里只丢弃旧分区。
    - [models.creator_image_model] -> [[models.creator_image_models]]：
      生图模型改为列表，允许配置多个模型/供应商。
    """
    new: dict[str, Any] = {"version": "0.5.0"}

    for key, value in old.items():
        if key in ("version", "console", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if isinstance(models, dict):
        migrated_models = {
            key: value for key, value in models.items() if key != "creator_image_model"
        }
        legacy_image_model = models.get("creator_image_model")
        if isinstance(legacy_image_model, dict):
            migrated_models["creator_image_models"] = [legacy_image_model]
        new["models"] = migrated_models

    return new


#: 旧的默认对话模型 key -> 新 key。这些 key 一开始由 model_name 自动生成，当时
#: DeepSeek 侧确实叫 deepseek-v4-*；后来 model_name 换成真实模型名 deepseek-flash，
#: key 没跟着改，于是留下一个既不对应任何模型、又让人误以为在跑另一个模型的空壳前缀。
#: 映射是**无条件**的：key 只是「调用方引用名」，改写它不动用户的 provider/model_name/
#: 参数，所以即便用户改过这些旧 key 条目，改名后依然指向同一个模型，不会丢配置。
_LEGACY_DEFAULT_MODEL_KEYS: dict[str, str] = {
    "deepseek-v4-pro": "deepseek-flash-max",
    "deepseek-v4-flash-max": "deepseek-flash-max",
    "deepseek-v4-flash-high": "deepseek-flash-high",
    "deepseek-v4-flash-off": "deepseek-flash-off",
}


@Config.migration(from_version="0.6.0", to_version="0.7.0")
def migrate_v6_to_v7(old: dict) -> dict:
    """迁移 0.6.0 -> 0.7.0：默认对话模型 key 与真实模型名对齐。

    - [[models.registry]] 里旧的 deepseek-v4-* key 改名为 deepseek-flash*；
      已停用的 pro 条目并入 flash（两者本来就是同一模型名 + 同一 max 推理强度）。
    - [models.assignments] 里引用旧 key 的角色同步改指新 key，避免出现
      「引用了模型库里不存在的 key」而让整条角色降级。
    """
    new: dict[str, Any] = {"version": "0.7.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if not isinstance(models, dict):
        return new

    migrated_models: dict[str, Any] = {}
    for name, value in models.items():
        if name not in ("registry", "assignments"):
            migrated_models[name] = value

    registry = models.get("registry")
    renamed: dict[str, str] = {}
    seen_refs: set[str] = set()
    migrated_registry: list[Any] = []
    if isinstance(registry, list):
        for entry in registry:
            if not isinstance(entry, dict):
                migrated_registry.append(entry)
                continue
            # 旧写法 key/description -> 新写法 model_ref/display_name。
            # 两者都是纯改名：provider / model_name / 参数原样保留。
            entry = dict(entry)
            current = str(entry.pop("key", "") or entry.get("model_ref") or "").strip()
            if "description" in entry and "display_name" not in entry:
                entry["display_name"] = entry.pop("description")
            target = _LEGACY_DEFAULT_MODEL_KEYS.get(current)
            if target is not None:
                # pro 与 flash-max 同为 model_name=deepseek-flash + max 推理，指向同一
                # 新引用名；去重后只留一条，否则模型库里会出现两个同模型条目。
                if target in seen_refs:
                    renamed[current] = target
                    continue
                entry["model_ref"] = target
                renamed[current] = target
            else:
                entry["model_ref"] = current
            ref_now = str(entry.get("model_ref") or "").strip()
            if ref_now in seen_refs:
                continue
            if ref_now:
                seen_refs.add(ref_now)
            migrated_registry.append(entry)
    if migrated_registry:
        migrated_models["registry"] = migrated_registry

    assignments = models.get("assignments")
    if isinstance(assignments, dict):
        migrated_assignments: dict[str, Any] = {}
        for role, value in assignments.items():
            if isinstance(value, list):
                migrated_assignments[role] = [
                    renamed.get(str(item).strip(), item) for item in value
                ]
            else:
                text = str(value or "").strip()
                migrated_assignments[role] = renamed.get(text, value)
        migrated_models["assignments"] = migrated_assignments

    if migrated_models:
        new["models"] = migrated_models
    return new


#: 与面板 ROLE_MODEL_TYPES 一致；迁移里不 import 面板模块，避免把 aiohttp 拉进配置层。
_ROLE_MODEL_TYPES_V8: dict[str, str] = {
    "primary_chat_model": "chat",
    "agent_model_1": "chat",
    "agent_model_2": "chat",
    "agent_model_3": "chat",
    "vision_model": "vision",
    "tts_model": "tts",
    "creator_image_models": "image",
}


@Config.migration(from_version="0.7.0", to_version="0.8.0")
def migrate_v7_to_v8(old: dict) -> dict:
    """迁移 0.7.0 -> 0.8.0：按分配角色推断模型条目的 model_type。

    仅当条目类型缺失/为 chat、且引用它的角色全部是非 chat 类型且类型一致时推断；
    混合角色、显式非 chat、未被引用的条目都不动。
    """
    new: dict[str, Any] = {"version": "0.8.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if not isinstance(models, dict):
        return new

    registry = models.get("registry")
    assignments = models.get("assignments")
    if not isinstance(registry, list) or not isinstance(assignments, dict):
        new["models"] = models
        return new

    role_types: dict[str, str] = {}
    for role, value in assignments.items():
        refs = value if isinstance(value, list) else [value]
        for ref in refs:
            text = str(ref or "").strip()
            if text:
                role_types.setdefault(text, set()).add(
                    _ROLE_MODEL_TYPES_V8.get(str(role), "chat")
                )

    migrated: list[Any] = []
    changed = False
    for entry in registry:
        if not isinstance(entry, dict):
            migrated.append(entry)
            continue
        item = dict(entry)
        ref = str(item.get("model_ref") or "").strip()
        current = str(item.get("model_type") or "").strip().lower()
        if ref and (not current or current == "chat"):
            types = role_types.get(ref, set())
            if len(types) == 1 and "chat" not in types:
                item["model_type"] = next(iter(types))
                changed = True
        migrated.append(item)

    new_models = {k: v for k, v in models.items() if k not in ("registry", "assignments")}
    if changed:
        new_models["registry"] = migrated
    else:
        new_models["registry"] = registry
    new_models["assignments"] = assignments
    new["models"] = new_models
    return new


#: 旧 settings.deepseek_reasoning_effort -> 顶层 reasoning_effort。沿用 DeepSeek provider
#: 的历史归并规则（low/medium->high，xhigh->max）；none/minimal 在旧字段里本来就无效，
#: 迁移时跳过，避免把一个「关闭推理」的语义搬成 high。
_LEGACY_EFFORT_TO_TOP_LEVEL: dict[str, str] = {
    "low": "high",
    "medium": "high",
    "high": "high",
    "xhigh": "max",
    "max": "max",
}

#: 旧思考开关里「明确关闭」的写法（历史配置可能是 bool，也可能是 enabled/disabled、true/false）
_THINKING_DISABLED_VALUES = frozenset({"disabled", "disable", "false", "off", "no", "0"})


def _thinking_is_disabled(settings: dict[str, Any]) -> bool:
    value = settings.get("deepseek_thinking_mode")
    if isinstance(value, bool):
        return value is False
    if isinstance(value, int):  # 手写 TOML 可能用 0/1 表示开关
        return value == 0
    return str(value or "").strip().casefold() in _THINKING_DISABLED_VALUES


def _is_image_or_tts(entry: dict[str, Any]) -> bool:
    from neobot_app.config.schemas.bot import normalize_model_type

    return normalize_model_type(entry.get("model_type", "chat")) in {"image", "tts"}


#: DeepSeek 官方 provider 的历史写法（与 neobot_chat._normalize_provider_kind 同判据）
_DEEPSEEK_PROVIDER_NAMES = frozenset({"deepseek", "deepseek_offical", "deepseek_official"})


def _is_deepseek_provider(entry: dict[str, Any]) -> bool:
    """旧 settings.deepseek_reasoning_effort 只有 DeepSeek provider 会真正使用。

    旧版程序给**每个**模型都写了这个字段（dataclass 默认值），所以迁移不能只看字段
    存在与否——否则 OpenAI / Anthropic / 硅基流动条目会凭空多出一个会改变请求体的
    顶层推理强度。
    """
    value = str(entry.get("provider") or "").strip().casefold().replace("-", "_")
    return value in _DEEPSEEK_PROVIDER_NAMES


@Config.migration(from_version="0.8.0", to_version="0.9.0")
def migrate_v8_to_v9(old: dict) -> dict:
    """迁移 0.8.0 -> 0.9.0：旧 DeepSeek 思考强度搬到模型库顶层 reasoning_effort。

    顶层字段是面板里可见、可编辑的主入口；旧 settings.deepseek_reasoning_effort 原样保留
    （provider 仍兼容），只是不再作为首选入口 —— 升级不会让用户丢掉已有设置。

    「思考已关」和「生图 / TTS 模型」不搬：这些条目上顶层值不会生效，搬过去只会让面板
    显示一个假的推理强度或在启动时刷无意义告警。
    """
    new: dict[str, Any] = {"version": "0.9.0"}
    for key, value in old.items():
        if key in ("version", "models"):
            continue
        new[key] = value

    models = old.get("models")
    if models is None:
        return new
    if not isinstance(models, dict):
        # 形态不可识别：原样保留，迁移只负责能看懂的部分
        new["models"] = models
        return new

    registry = models.get("registry")
    if not isinstance(registry, list):
        new["models"] = models
        return new

    migrated: list[Any] = []
    for entry in registry:
        if not isinstance(entry, dict):
            migrated.append(entry)
            continue
        item = dict(entry)
        settings = item.get("settings")
        # 只有 DeepSeek 条目会真正使用旧思考强度；思考已关（出厂 deepseek-flash-off
        # 就是这种）搬过去只会显示一个不生效的「推理 high」；生图 / TTS 模型搬过去只会
        # 在加载时刷无意义告警。都跳过，旧键不动。
        if (
            not str(item.get("reasoning_effort") or "").strip()
            and _is_deepseek_provider(item)
            and not _is_image_or_tts(item)
            and isinstance(settings, dict)
            and not _thinking_is_disabled(settings)
        ):
            legacy = str(settings.get("deepseek_reasoning_effort") or "").strip().casefold()
            effort = _LEGACY_EFFORT_TO_TOP_LEVEL.get(legacy)
            if effort is not None:
                item["reasoning_effort"] = effort
        migrated.append(item)

    # registry 之外的 models 字段（assignments / 其它自定义段）一律原样保留
    new_models = {name: value for name, value in models.items() if name != "registry"}
    new_models["registry"] = migrated
    new["models"] = new_models
    return new

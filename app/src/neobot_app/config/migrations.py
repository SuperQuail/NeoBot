"""配置迁移"""

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


_DASHBOARD_CARRY_KEYS = (
    "enabled",
    "host",
    "port",
    "session_timeout_minutes",
    "secure_cookies",
    "trust_proxy_headers",
)


@Config.migration(from_version="0.4.0", to_version="0.5.0")
def migrate_v4_to_v5(old: dict) -> dict:
    """迁移 0.4.0 -> 0.5.0。

    - [console] -> [dashboard]：双控制台合并为官方 dashboard 插件，admin_* 与
      port_search_limit 不再需要，其余可直接沿用的字段保留。
    - [models.creator_image_model] -> [[models.creator_image_models]]：
      生图模型改为列表，允许配置多个模型/供应商。
    """
    new: dict[str, Any] = {"version": "0.5.0"}

    for key, value in old.items():
        if key in ("version", "console", "models"):
            continue
        new[key] = value

    console = old.get("console")
    if isinstance(console, dict):
        dashboard = {
            key: console[key]
            for key in _DASHBOARD_CARRY_KEYS
            if key in console
        }
        if dashboard:
            new["dashboard"] = dashboard

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

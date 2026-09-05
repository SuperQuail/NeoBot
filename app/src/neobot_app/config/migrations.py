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

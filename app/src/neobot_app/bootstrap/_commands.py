"""命令系统与凭据管理器装配。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from neobot_app.core import CONFIG_BACKUP_DIR, CONFIG_FILE


def build_command_service(
    *,
    config: Any,
    adapter: Any,
    logger_factory: Any,
    markdown_image_converter: Any = None,
    file_server: Any = None,
    sleep_service: Any = None,
) -> Any:
    """构建命令服务(内置命令注册 + 配置保存/热重载回调)。

    markdown_image_converter/file_server 用于 /help 渲染图片(缺失时降级文本)。
    sleep_service 供 /sleep /awake 命令使用。
    """
    from neobot_app.commands.service import CommandService

    service = CommandService(
        config=config,
        adapter=adapter,
        config_save_callback=_make_config_save_callback(config),
        logger=logger_factory.get_logger("app.commands"),
        markdown_image_converter=markdown_image_converter,
        file_server=file_server,
        sleep_service=sleep_service,
    )
    return service


def build_credential_manager(*, permissions: Any) -> Any:
    """构建凭据管理器(风险操作授权,与命令系统共用权限树)。"""
    from neobot_app.credentials.service import CredentialManager

    return CredentialManager(permissions=permissions)


def _make_config_save_callback(config: Any):
    """配置保存回调:更新 chat.sub_admin_accounts 并触发热重载。"""

    async def _save_sub_admins(new_list: list[int]) -> str:
        try:
            import tomlkit

            from neobot_app.config.loader.backup import backup_config
            from neobot_app.config.loader.converter import dict_to_dataclass
            from neobot_app.config.schemas.bot import BotConfig

            document = tomlkit.parse(CONFIG_FILE.read_text(encoding="utf-8"))
            chat = document.get("chat", {})
            if not isinstance(chat, dict):
                raise TypeError("配置缺少 chat 段")
            chat["sub_admin_accounts"] = [int(value) for value in new_list]
            raw_config = document.unwrap()
            validated = dict_to_dataclass(raw_config, BotConfig)
            rendered = tomlkit.dumps(document)
            await asyncio.to_thread(backup_config, CONFIG_FILE, CONFIG_BACKUP_DIR)
            await asyncio.to_thread(_atomic_write, CONFIG_FILE, rendered)
            config.reload(validated)
        except Exception as exc:
            return f"错误: 配置保存失败: {exc}"
        return "ok"

    return _save_sub_admins


def _atomic_write(path: Path, text: str) -> None:
    """原子写文件(临时文件 + replace)。"""
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            import os

            os.fsync(handle.fileno())
        tmp = Path(tmp_name)
        tmp.replace(path)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


# 允许 AI 工具通过回调更新的 chat 段键(白名单,防任意键注入)
_CHAT_UPDATE_ALLOWED_KEYS = frozenset({
    "willing_agent_global_coefficient",
    "willing_global_coefficient",
})


def _make_chat_config_update_callback(config: Any):
    """chat 段指定键更新回调:写回 config.toml + 热重载(白名单键)。"""

    async def _update_chat_config(key: str, value: Any) -> str:
        if key not in _CHAT_UPDATE_ALLOWED_KEYS:
            return f"错误: 不允许更新配置键 {key}"
        try:
            import tomlkit

            from neobot_app.config.loader.backup import backup_config
            from neobot_app.config.loader.converter import dict_to_dataclass
            from neobot_app.config.schemas.bot import BotConfig

            document = tomlkit.parse(CONFIG_FILE.read_text(encoding="utf-8"))
            chat = document.get("chat", {})
            if not isinstance(chat, dict):
                raise TypeError("配置缺少 chat 段")
            chat[key] = value
            raw_config = document.unwrap()
            validated = dict_to_dataclass(raw_config, BotConfig)
            rendered = tomlkit.dumps(document)
            await asyncio.to_thread(backup_config, CONFIG_FILE, CONFIG_BACKUP_DIR)
            await asyncio.to_thread(_atomic_write, CONFIG_FILE, rendered)
            config.reload(validated)
        except Exception as exc:
            return f"错误: 配置保存失败: {exc}"
        return "ok"

    return _update_chat_config

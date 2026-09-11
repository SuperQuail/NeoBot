"""命令系统与凭据管理器装配。"""

from __future__ import annotations

import asyncio
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
    standby_service: Any = None,
    config_reload_callback: Any = None,
) -> Any:
    """构建命令服务(内置命令注册 + 配置保存/热重载回调)。

    markdown_image_converter/file_server 用于 /help 渲染图片(缺失时降级文本)。
    sleep_service 供 /sleep /awake 命令使用。
    standby_service 供 /standby /reboot /standby_status 命令使用。
    config_reload_callback 供 /reload 命令触发不重启进程的配置热重载。
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
        standby_service=standby_service,
        config_reload_callback=config_reload_callback,
    )
    return service


def build_credential_manager(*, permissions: Any) -> Any:
    """构建凭据管理器(风险操作授权,与命令系统共用权限树)。"""
    from neobot_app.credentials.service import CredentialManager

    return CredentialManager(permissions=permissions)


#: 允许 AI 工具通过回调更新的 chat 段键(白名单,防任意键注入)
_CHAT_UPDATE_ALLOWED_KEYS = frozenset({
    "willing_agent_global_coefficient",
    "willing_global_coefficient",
})


def _reload_live_config(config: Any) -> bool:
    """把磁盘上的 config.toml 重新加载进内存配置对象。

    返回是否生效：config 不是 ConfigProxy（例如配置加载失败时的兜底对象）
    时无法热重载，此时命令层会提示"重启后生效"，而不是把写盘成功当成失败。
    """
    reload = getattr(config, "reload", None)
    if not callable(reload):
        return False
    try:
        import tomlkit

        from neobot_app.config.loader.converter import dict_to_dataclass
        from neobot_app.config.schemas.bot import BotConfig

        raw = tomlkit.parse(CONFIG_FILE.read_text(encoding="utf-8-sig")).unwrap()
        reload(dict_to_dataclass(raw, BotConfig))
    except Exception:
        return False
    return True


def _make_config_save_callback(config: Any):
    """配置保存回调:更新 chat.sub_admin_accounts 并触发热重载。

    写盘走 chat_writer（缺 [chat] 段会在文档里创建、写盘前后都有校验），
    返回 ConfigSaveResult：只有磁盘上确实写入成功才 ok=True。
    """

    async def _save_sub_admins(new_list: list[int]) -> Any:
        from neobot_app.commands.model import ConfigSaveResult
        from neobot_app.config.chat_writer import save_sub_admin_accounts

        result = await asyncio.to_thread(
            save_sub_admin_accounts,
            CONFIG_FILE,
            new_list,
            backup_dir=CONFIG_BACKUP_DIR,
        )
        if not result.ok:
            return ConfigSaveResult(ok=False, error=result.error, path=str(CONFIG_FILE))
        accounts = tuple(
            str(item) for item in (result.values.get("sub_admin_accounts") or ())
        )
        applied = await asyncio.to_thread(_reload_live_config, config)
        return ConfigSaveResult(
            ok=True, accounts=accounts, applied=applied, path=str(CONFIG_FILE)
        )

    return _save_sub_admins


def _make_chat_config_update_callback(config: Any):
    """chat 段指定键更新回调:写回 config.toml + 热重载(白名单键)。

    与次级管理员共用 chat_writer：缺 [chat] 段时同样会在文档里创建，
    不会出现"返回 ok 但文件没变"的静默失败。
    """

    async def _update_chat_config(key: str, value: Any) -> str:
        if key not in _CHAT_UPDATE_ALLOWED_KEYS:
            return f"错误: 不允许更新配置键 {key}"
        from neobot_app.config.chat_writer import write_chat_values

        try:
            result = await asyncio.to_thread(
                write_chat_values,
                CONFIG_FILE,
                {key: value},
                backup_dir=CONFIG_BACKUP_DIR,
            )
        except Exception as exc:
            return f"错误: 配置保存失败: {exc}"
        if not result.ok:
            return f"错误: 配置保存失败: {result.error}"
        await asyncio.to_thread(_reload_live_config, config)
        return "ok"

    return _update_chat_config



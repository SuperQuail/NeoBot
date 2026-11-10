from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.sandbox import SandboxDataPort

from neobot_adapter.interfaces import RuntimeAdapter
from neobot_adapter.local import LocalAdapter


@dataclass(frozen=True)
class AdapterSettings:
    mode: str = "onebot"
    local_host: str = "127.0.0.1"
    local_port: int = 8090
    local_auth_token: str = ""
    bot_user_id: int = 0
    bot_name: str = "Neo Bot"
    # onebot 反向 WebSocket 服务端监听(空/0 表示未配置,回退环境变量与默认值)
    reverse_ws_host: str = ""
    reverse_ws_port: int = 0
    # 反向 WebSocket 握手鉴权的 access token(OneBot 11 规范;留空表示不校验)
    reverse_ws_access_token: str = ""
    # QQ 官方机器人协议(adapter.mode = "official")配置
    qq_appid: str = ""
    qq_client_secret: str = ""
    qq_markdown: bool = True
    qq_base_url: str = "https://api.bot.qq.com"
    qq_token_url: str = "https://api.bot.qq.com/app/getAppAccessToken"
    qq_portal_host: str = "q.qq.com"
    # 官方协议的凭据/身份持久化根目录(由本体传入 DATA_DIR)
    data_dir: str = ""


def create_adapter(
    settings: AdapterSettings | Any | None = None,
    *,
    logger: Logger | None = None,
    packet_callback: Callable[[dict[str, Any]], None] | None = None,
    sandbox_data: SandboxDataPort | None = None,
) -> RuntimeAdapter:
    cfg = _coerce_settings(settings)
    adapter_logger = logger or NullLogger()
    mode = cfg.mode.strip().casefold()
    if mode == "local":
        return LocalAdapter(
            host=cfg.local_host,
            port=cfg.local_port,
            auth_token=cfg.local_auth_token,
            bot_user_id=cfg.bot_user_id,
            bot_name=cfg.bot_name,
            logger=adapter_logger,
            packet_callback=packet_callback,
            sandbox_data=sandbox_data,
        )
    if mode in {"onebot", "official"}:
        # 延迟导入:SwitchableAdapter 反向依赖本模块的 AdapterSettings。
        from neobot_adapter.switchable import SwitchableAdapter

        return SwitchableAdapter(
            cfg,
            logger=adapter_logger,
            packet_callback=packet_callback,
            sandbox_data=sandbox_data,
            data_dir=cfg.data_dir or None,
        )
    raise ValueError(f"未知适配器模式: {cfg.mode}。可选值: onebot, official, local")


def _coerce_settings(settings: AdapterSettings | Any | None) -> AdapterSettings:
    if settings is None:
        return AdapterSettings()
    if isinstance(settings, AdapterSettings):
        return settings
    return AdapterSettings(
        mode=str(getattr(settings, "mode", "onebot") or "onebot"),
        local_host=str(getattr(settings, "local_host", "127.0.0.1") or "127.0.0.1"),
        local_port=int(getattr(settings, "local_port", 8090) or 8090),
        local_auth_token=str(getattr(settings, "local_auth_token", "") or ""),
        bot_user_id=int(getattr(settings, "bot_user_id", 0) or 0),
        bot_name=str(getattr(settings, "bot_name", "Neo Bot") or "Neo Bot"),
        reverse_ws_host=str(getattr(settings, "reverse_ws_host", "") or ""),
        reverse_ws_port=int(getattr(settings, "reverse_ws_port", 0) or 0),
        reverse_ws_access_token=str(
            getattr(settings, "reverse_ws_access_token", "") or ""
        ),
        qq_appid=str(getattr(settings, "qq_appid", "") or ""),
        qq_client_secret=str(getattr(settings, "qq_client_secret", "") or ""),
        qq_markdown=bool(getattr(settings, "qq_markdown", True)),
        qq_base_url=str(
            getattr(settings, "qq_base_url", "https://api.bot.qq.com")
            or "https://api.bot.qq.com"
        ),
        qq_token_url=str(
            getattr(settings, "qq_token_url", "https://api.bot.qq.com/app/getAppAccessToken")
            or "https://api.bot.qq.com/app/getAppAccessToken"
        ),
        qq_portal_host=str(getattr(settings, "qq_portal_host", "q.qq.com") or "q.qq.com"),
        data_dir=str(getattr(settings, "data_dir", "") or ""),
    )

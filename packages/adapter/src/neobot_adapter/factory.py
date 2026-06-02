from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.sandbox import SandboxDataPort

from neobot_adapter.adapter import OneBotAdapter
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
    if mode == "onebot":
        return OneBotAdapter(logger=adapter_logger, packet_callback=packet_callback)
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
    raise ValueError(f"未知适配器模式: {cfg.mode}。可选值: onebot, local")


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
    )

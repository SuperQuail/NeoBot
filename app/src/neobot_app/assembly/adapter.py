"""适配器装配"""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from neobot_adapter import AdapterSettings, RuntimeAdapter, create_adapter
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.sandbox import SandboxDataPort

from neobot_app.assembly.sandbox import build_json_sandbox_store
from neobot_app.core.constants import DATA_DIR


def build_adapter(
    *,
    config: Any = None,
    logger: Logger | None = None,
    packet_callback=None,
    sandbox_data: SandboxDataPort | None = None,
) -> RuntimeAdapter:
    settings = _settings_from_config(config)
    resolved_sandbox = sandbox_data
    if resolved_sandbox is None and settings.mode.strip().casefold() == "local":
        resolved_sandbox = build_json_sandbox_store(
            data_dir=DATA_DIR,
            bot_user_id=settings.bot_user_id,
            bot_name=settings.bot_name,
        )
    return create_adapter(
        settings,
        logger=logger or NullLogger(),
        packet_callback=packet_callback,
        sandbox_data=resolved_sandbox,
    )


def _settings_from_config(config: Any = None) -> AdapterSettings:
    adapter_cfg = getattr(config, "adapter", None)
    bot_cfg = getattr(config, "bot", None)
    settings = AdapterSettings(
        mode=str(getattr(adapter_cfg, "mode", "onebot") or "onebot"),
        local_host=str(getattr(adapter_cfg, "local_host", "127.0.0.1") or "127.0.0.1"),
        local_port=int(getattr(adapter_cfg, "local_port", 8090) or 8090),
        local_auth_token=str(getattr(adapter_cfg, "local_auth_token", "") or ""),
        bot_user_id=int(getattr(bot_cfg, "account", 0) or 0),
        bot_name=str(getattr(bot_cfg, "nick_name", "Neo Bot") or "Neo Bot"),
        reverse_ws_host=str(getattr(adapter_cfg, "reverse_ws_host", "") or ""),
        reverse_ws_port=int(getattr(adapter_cfg, "reverse_ws_port", 0) or 0),
        reverse_ws_access_token=str(
            getattr(adapter_cfg, "reverse_ws_access_token", "") or ""
        ),
    )
    return _apply_env_overrides(settings)


def _apply_env_overrides(settings: AdapterSettings) -> AdapterSettings:
    values: dict[str, Any] = {}
    if "NEOBOT_ADAPTER_MODE" in os.environ:
        values["mode"] = os.environ["NEOBOT_ADAPTER_MODE"]
    if "NEOBOT_LOCAL_ADAPTER_HOST" in os.environ:
        values["local_host"] = os.environ["NEOBOT_LOCAL_ADAPTER_HOST"]
    if "NEOBOT_LOCAL_ADAPTER_PORT" in os.environ:
        values["local_port"] = int(os.environ["NEOBOT_LOCAL_ADAPTER_PORT"])
    if "NEOBOT_LOCAL_ADAPTER_TOKEN" in os.environ:
        values["local_auth_token"] = os.environ["NEOBOT_LOCAL_ADAPTER_TOKEN"]
    # onebot 反向 WS:优先专用变量;兼容老版本无 Local 字样的键(NEOBOT_ADAPTER_*)
    # 与生产既有 NEOBOT_LOCAL_ADAPTER_* 配置,避免"配了 8091 实际监听 8080"
    reverse_host = (
        _env_ci("NEO_BOT_ADAPTER_HOST")
        or _env_ci("NEOBOT_ADAPTER_HOST")
        or _env_ci("NEOBOT_LOCAL_ADAPTER_HOST")
    )
    reverse_port = (
        _env_ci("NEO_BOT_ADAPTER_PORT")
        or _env_ci("NEOBOT_ADAPTER_PORT")
        or _env_ci("NEOBOT_LOCAL_ADAPTER_PORT")
    )
    if reverse_host:
        values["reverse_ws_host"] = reverse_host
    if reverse_port:
        values["reverse_ws_port"] = int(reverse_port)
    # 反向 WS 的 token 只认专用变量：不复用 NEOBOT_LOCAL_ADAPTER_TOKEN，
    # 否则 local 模式的老配置会突然让反向 WS 开始强制校验、连不上框架。
    reverse_token = _env_ci("NEO_BOT_ADAPTER_TOKEN") or _env_ci("NEOBOT_ADAPTER_TOKEN")
    if reverse_token:
        values["reverse_ws_access_token"] = reverse_token
    if not values:
        return settings
    return replace(settings, **values)


def _env_ci(name: str) -> str | None:
    """大小写不敏感读取环境变量(.env 键名原样保留,os.getenv 大小写敏感)。"""
    target = name.casefold()
    for key, value in os.environ.items():
        if key.casefold() == target:
            return value
    return None

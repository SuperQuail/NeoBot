"""反向 WebSocket 的监听设置值对象。

把「配置项 / 环境变量 → 实际监听地址、端口、access token」的解析规则收敛到
一个不可变值对象里，`AdapterCore` 只负责使用结果，不再自己解析与判断：

- 解析优先级：构造参数（来自本体配置系统） > 环境变量 > 默认值；
- 环境变量兼容链（大小写不敏感）保留历史行为：
  ``NEO_BOT_ADAPTER_HOST`` / ``NEO_BOT_ADAPTER_PORT`` 为新键，
  ``NEOBOT_ADAPTER_*`` 为配置迁移期的老键，
  ``NEOBOT_LOCAL_ADAPTER_*`` 为生产长期使用的 local 专用键（onebot 模式下
  回退读取，避免「配了 8091 实际监听 8080」）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from neobot_adapter.utils.net import is_loopback_host

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8080

_HOST_ENV_KEYS = (
    "NEO_BOT_ADAPTER_HOST",
    "NEOBOT_ADAPTER_HOST",
    "NEOBOT_LOCAL_ADAPTER_HOST",
)
_PORT_ENV_KEYS = (
    "NEO_BOT_ADAPTER_PORT",
    "NEOBOT_ADAPTER_PORT",
    "NEOBOT_LOCAL_ADAPTER_PORT",
)


def env_ci(environ: Mapping[str, str], name: str) -> str | None:
    """大小写不敏感地读取环境变量。

    .env 文件中的键名由 load_env 原样写入 os.environ（保留用户大小写），
    而 os.getenv 大小写敏感，用户写成 NEOBOT_ADAPTER_PORT / 小写变体时
    会静默回落到默认值 —— 这里统一按大小写不敏感匹配，杜绝该坑。
    """
    target = name.casefold()
    for key, value in environ.items():
        if key.casefold() == target:
            return value
    return None


def _first_env(environ: Mapping[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        value = env_ci(environ, name)
        if value:
            return value
    return None


@dataclass(frozen=True, slots=True)
class ReverseWsSettings:
    """反向 WebSocket 的实际监听设置（已解析，可直接使用）。"""

    host: str
    port: int
    access_token: str

    @property
    def token_enabled(self) -> bool:
        """是否启用握手鉴权。留空表示不校验（与历史行为一致）。"""
        return bool(self.access_token)

    @property
    def exposes_non_loopback_without_token(self) -> bool:
        """未配置 token 且对外监听：同网段任何主机都能连入注入伪造事件。"""
        return not self.token_enabled and not is_loopback_host(self.host)

    def describe(self) -> str:
        """启动日志用的监听描述。"""
        state = "已启用" if self.token_enabled else "未启用"
        return f"ws://{self.host}:{self.port}（access token 校验：{state}）"

    def security_warning(self) -> str | None:
        """未配置 token 却对外监听时的告警文案；配置安全时返回 None。"""
        if not self.exposes_non_loopback_without_token:
            return None
        return (
            "反向 WebSocket 未配置 access token 且监听非回环地址 "
            f"({self.host}:{self.port})：该网段内任何主机都能连入并注入伪造事件。"
            "请在 [adapter].reverse_ws_access_token 与 OneBot 框架反向 WS 的 "
            "token 中填入同一个值。"
        )

    @classmethod
    def resolve(
        cls,
        *,
        host: str | None = None,
        port: int | None = None,
        access_token: str = "",
        environ: Mapping[str, str] | None = None,
    ) -> "ReverseWsSettings":
        """按「构造参数 > 环境变量 > 默认值」解析出实际设置。"""
        source = os.environ if environ is None else environ
        resolved_host = host or _first_env(source, _HOST_ENV_KEYS) or DEFAULT_HOST
        resolved_port = port
        if resolved_port is None:
            raw_port = _first_env(source, _PORT_ENV_KEYS)
            resolved_port = int(raw_port) if raw_port else DEFAULT_PORT
        return cls(
            host=str(resolved_host),
            port=int(resolved_port),
            access_token=str(access_token or "").strip(),
        )

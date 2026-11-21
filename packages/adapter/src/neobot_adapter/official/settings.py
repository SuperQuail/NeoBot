"""QQ 官方机器人协议的适配器配置。

官方协议需要的 AppID/AppSecret、API 地址与落盘目录都在这里收口：配置层
（``[adapter].qq_*``）与测试里直接构造的值共享同一份默认值，避免两处漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://api.bot.qq.com"
DEFAULT_TOKEN_URL = "https://api.bot.qq.com/app/getAppAccessToken"
DEFAULT_PORTAL_HOST = "q.qq.com"
DEFAULT_BIND_TIMEOUT_SECONDS = 600.0


def _clean(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


@dataclass(frozen=True, slots=True)
class OfficialSettings:
    """官方协议运行期设置（``from_adapter_settings`` 是唯一的生产来源）。"""

    app_id: str
    client_secret: str
    base_url: str = DEFAULT_BASE_URL
    token_url: str = DEFAULT_TOKEN_URL
    portal_host: str = DEFAULT_PORTAL_HOST
    data_dir: Path = field(default_factory=lambda: Path("data"))
    bind_timeout_seconds: float = DEFAULT_BIND_TIMEOUT_SECONDS

    @property
    def qqbot_dir(self) -> Path:
        """官方协议落盘目录：凭据与身份映射都在 <DATA_DIR>/qqbot 下。"""
        return self.data_dir / "qqbot"

    @classmethod
    def from_adapter_settings(
        cls,
        settings: Any,
        *,
        data_dir: str | Path | None = None,
    ) -> "OfficialSettings":
        """从 ``AdapterSettings`` 解析；``qq_*`` 为空串时按各自默认值回落。

        data_dir 显式参数优先于 settings.data_dir：切换门面拿到的是 DATA_DIR
        根目录，而旧配置对象可能还没有 data_dir 字段。
        """
        resolved_data_dir = data_dir if data_dir is not None else getattr(settings, "data_dir", "")
        portal_host = _clean(getattr(settings, "qq_portal_host", ""), DEFAULT_PORTAL_HOST)
        return cls(
            app_id=_clean(getattr(settings, "qq_appid", ""), ""),
            client_secret=_clean(getattr(settings, "qq_client_secret", ""), ""),
            base_url=_clean(getattr(settings, "qq_base_url", ""), DEFAULT_BASE_URL),
            token_url=_clean(getattr(settings, "qq_token_url", ""), DEFAULT_TOKEN_URL),
            # 配置里允许填带协议头的域名，统一成 host 供 URL 拼接使用。
            portal_host=portal_host.removeprefix("https://").removeprefix("http://").rstrip("/"),
            data_dir=Path(str(resolved_data_dir or "data")),
            bind_timeout_seconds=DEFAULT_BIND_TIMEOUT_SECONDS,
        )

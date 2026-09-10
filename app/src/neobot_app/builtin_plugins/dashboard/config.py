"""面板配置模型。

官方插件的配置直接来自本体 config.toml 的 [dashboard] 分区
（由 PluginRuntime 的 official_config_provider 注入），因此这里只做校验与默认值。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DashboardConfig(BaseModel):
    """网页面板运行配置（对应 config.toml 的 [dashboard]）。"""

    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = Field(default=9981, ge=1, le=65535)
    base_path: str = ""
    manage_plugins: bool = True
    allow_remote_manage: bool = True
    session_timeout_minutes: int = Field(default=720, ge=5, le=10080)
    log_buffer_size: int = Field(default=500, ge=1, le=10000)
    bot_info_cache_ttl: int = Field(default=300, ge=0, le=86400)
    history_max_days: int = Field(default=30, ge=1, le=3650)
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_rate_limit_window_seconds: int = Field(default=600, ge=1, le=86400)
    secure_cookies: bool = False
    trust_proxy_headers: bool = False

    @field_validator("host")
    @classmethod
    def _host_not_empty(cls, value: str) -> str:
        if not str(value).strip():
            raise ValueError("dashboard.host 不能为空")
        return str(value).strip()

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return ""
        if not normalized.startswith("/"):
            raise ValueError("dashboard.base_path 必须以 / 开头")
        return normalized.rstrip("/")

    @property
    def prefix(self) -> str:
        """带前导斜杠的访问前缀；根路径时为 空串。"""
        return self.base_path

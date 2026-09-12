"""面板配置模型。

面板配置保存在插件数据目录 plugins_data/dashboard/config.toml（由 PluginRuntime 注入），
这里的默认值就是面板的出厂配置；插件自带 plugin.toml 的 [config] 只提供打包默认值，
两者应保持一致（有测试守住）。

配置与本体 config.toml 完全解耦：面板不再读写本体配置的 [dashboard] 分区。
「面板是否启用」也不属于配置：它是 plugin_state.json 里的独立启动记录。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class DashboardConfig(BaseModel):
    """网页面板运行配置（plugins_data/dashboard/config.toml）。"""

    host: str = Field(
        default="0.0.0.0",
        description="监听地址。0.0.0.0 对网络开放；只在本机使用请填 127.0.0.1。",
    )
    port: int = Field(
        default=9981,
        ge=1,
        le=65535,
        description="监听端口。被占用时从该端口起向后自动尝试 10 个端口。",
    )
    base_path: str = Field(
        default="",
        description="访问前缀，用于反向代理子路径部署（如 /neobot），留空表示根路径。",
    )
    manage_plugins: bool = Field(
        default=True,
        description="是否允许在面板里做写操作（插件启停/安装、配置保存、待机重启）。关闭后面板变为只读。",
    )
    allow_remote_manage: bool = Field(
        default=True,
        description="是否允许非本机来源做写操作。关闭后远程只能查看，改配置仅限本机。",
    )
    session_timeout_minutes: int = Field(
        default=720,
        ge=5,
        le=10080,
        description="登录会话有效期（分钟），超时后需要重新登录。",
    )
    log_buffer_size: int = Field(
        default=500,
        ge=1,
        le=10000,
        description="面板内存中保留的日志条数（用于「日志」页实时滚动）。",
    )
    bot_info_cache_ttl: int = Field(
        default=300,
        ge=0,
        le=86400,
        description="机器人信息（昵称/版本/头像）的缓存秒数，0 表示每次都重新查询。",
    )
    latency_probe_interval_seconds: int = Field(
        default=60,
        ge=0,
        le=86400,
        description="有人查看面板时的延迟探测间隔（秒）。探测会真实调用一次 get_status；0 表示彻底关闭探针。",
    )
    latency_probe_idle_seconds: int = Field(
        default=0,
        ge=0,
        le=86400,
        description="无人在线时的延迟探测间隔（秒）。0（默认）表示完全停止探测，不产生任何 API 调用。",
    )
    latency_probe_active_window_seconds: int = Field(
        default=120,
        ge=1,
        le=86400,
        description="面板会话视为「有人在线」的活跃窗口（秒）；最后一次请求在此窗口内才认为有人在看面板。",
    )
    latency_probe_gate_check_seconds: int = Field(
        default=30,
        ge=1,
        le=86400,
        description="空闲/未探测时复检门控条件的间隔（秒）。该间隔不产生 API 调用，只用于及时发现有人重新打开面板。",
    )
    allow_archive_delete: bool = Field(
        default=False,
        description="是否允许在「档案」页删除档案记录。默认关闭（防止误删长期记忆）；与模型侧 agent.memory.archive.allow_delete 完全独立。",
    )
    history_max_days: int = Field(
        default=30,
        ge=1,
        le=3650,
        description="面板指标历史（消息量、延迟、用量）的保留天数。",
    )
    login_max_failures: int = Field(
        default=5,
        ge=1,
        le=100,
        description="同一来源在统计窗口内允许的登录失败次数，超过后暂时封禁。",
    )
    login_rate_limit_window_seconds: int = Field(
        default=600,
        ge=1,
        le=86400,
        description="登录失败次数统计窗口（秒）。",
    )
    secure_cookies: bool = Field(
        default=False,
        description="会话 Cookie 是否只在 HTTPS 下发送。确认反向代理 HTTPS 生效后再开启。",
    )
    trust_proxy_headers: bool = Field(
        default=False,
        description="是否信任反向代理写入的客户端地址头（X-Forwarded-For/Host）。仅在代理可信时开启。",
    )

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

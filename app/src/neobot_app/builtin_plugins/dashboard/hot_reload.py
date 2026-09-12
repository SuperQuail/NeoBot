"""面板插件配置的「运行期原地生效」声明（bugfixes/feat(2) §6）。

背景：dashboard 声明了 hot_reload=False / config_hot_reload=False —— 面板持有 HTTP 服务与
监听端口，整插件重载会关闭服务、切断当前保存请求、并丢掉全部内存指标。因此
「让配置改动立即生效」不能靠重载插件，而要靠**原地改配置**。

做法：在 load() 里把自己登记成 modloader 的「插件配置消费者」
（PluginControlFacade.register_config_consumer），并逐项声明每个配置键是
「运行期安全（保存即生效）」还是「绑定期 / 安全类（仍需重启）」。

面板保存配置时由 neobot_app.runtime.plugin_config_reload 负责分类与调用，
本模块只负责「声明 + 应用 + 失败时保留旧配置」。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.config.hot_reload import HotReloadRule

if TYPE_CHECKING:  # pragma: no cover - 仅类型检查
    from . import DashboardPlugin

#: 运行期安全：这些字段的改动保存后立即生效，无需重启、无需重载插件
_RUNTIME_SAFE: tuple[tuple[str, str], ...] = (
    (
        "latency_probe_interval_seconds",
        "延迟探针每轮重读插件配置，保存后下一轮生效（interval=0 会立即关闭探针）",
    ),
    (
        "latency_probe_idle_seconds",
        "空闲探测间隔每轮重读，保存后下一轮生效",
    ),
    (
        "latency_probe_active_window_seconds",
        "活跃窗口每轮判定时读取，保存后下一轮生效",
    ),
    (
        "latency_probe_gate_check_seconds",
        "门控复检间隔每轮读取，保存后下一轮生效",
    ),
    (
        "bot_info_cache_ttl",
        "机器人信息缓存 TTL 在每次读取时判断，保存后立即生效",
    ),
    (
        "log_buffer_size",
        "日志缓冲按新容量就地重建（保留最近条目，不清空历史）",
    ),
    (
        "history_max_days",
        "指标历史保留天数立即裁剪，不需要重建任何服务",
    ),
    (
        "allow_archive_delete",
        "面板档案删除开关在每次请求时读取，保存后立即生效",
    ),
)

#: 绑定期 / 安全类：保守处理，继续要求重启 NeoBot
_REQUIRES_RESTART: tuple[tuple[str, str], ...] = (
    ("host", "监听地址在启动时绑定，改动需重启重新监听"),
    ("port", "监听端口在启动时绑定，改动需重启重新监听"),
    ("base_path", "路由前缀在启动时注册，改动需重启"),
    ("manage_plugins", "安全开关：避免把管理员锁在门外，需重启"),
    ("allow_remote_manage", "安全开关：远程管理策略需重启后重新评估"),
    ("session_timeout_minutes", "会话超时在会话表构造时固化，需重启"),
    ("secure_cookies", "Cookie 安全策略在启动时确定，需重启"),
    ("trust_proxy_headers", "代理信任策略在启动时确定，需重启"),
    ("login_max_failures", "登录限流器在启动时构造，需重启"),
    ("login_rate_limit_window_seconds", "登录限流窗口在启动时构造，需重启"),
)

#: 供 plugin_config_reload 判定的路径前缀（plugin.<插件名>）
CONFIG_PATH_PREFIX = "plugin.dashboard"


def _rule_path(key: str) -> str:
    return f"{CONFIG_PATH_PREFIX}.{key}"


class DashboardConfigConsumer:
    """面板自身的配置消费者（登记进 modloader 的原地生效通道）。"""

    def __init__(self, plugin: "DashboardPlugin") -> None:
        self._plugin = plugin

    # ------------------------------------------------------------------
    # modloader 侧读取的声明
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "dashboard"

    @property
    def config_paths(self) -> tuple[str, ...]:
        return (CONFIG_PATH_PREFIX,)

    @property
    def hot_reload_policies(self) -> tuple[HotReloadRule, ...]:
        return tuple(
            HotReloadRule(_rule_path(key), True, reason)
            for key, reason in _RUNTIME_SAFE
        ) + tuple(
            HotReloadRule(_rule_path(key), False, reason)
            for key, reason in _REQUIRES_RESTART
        )

    # ------------------------------------------------------------------
    # 生效
    # ------------------------------------------------------------------

    async def apply_config(self, config: Any) -> None:
        """用新的生效配置刷新面板的运行期字段。

        失败时**抛出**：调用方（plugin_config_reload）会保留旧配置并把错误原样报给面板，
        面板继续按旧值运行 —— 这正是「注入 apply_config 异常」验收口径要求的行为。
        """
        from .config import DashboardConfig

        if isinstance(config, DashboardConfig):
            new = config
        else:
            new = DashboardConfig.model_validate(dict(config or {}))
        self._plugin.apply_runtime_config(new)

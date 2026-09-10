"""配置项热重载分类。

本模块回答一个问题：**改动某个配置项后，是否必须重启 NeoBot？**

- 通过 `ConfigProxy` 在运行时按需读取的配置（概率系数、冷却时间、名单、提示词等）
  在 `config.reload` 之后立即生效；
- 由启动期组件持有快照的配置（运行中的 LLM Provider、关键词规则、TTS 服务、
  适配器、面板服务、插件运行时等）必须重启进程才会生效。

规则表按「最长前缀优先」匹配，**未命中任何规则的路径默认视为需要重启**（保守），
这样新增配置项不会因为忘记登记而被错误地标成热重载。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Iterable, Mapping

#: 面板/日志展示时单值最大长度
MAX_VALUE_CHARS = 240


@dataclass(frozen=True, slots=True)
class HotReloadRule:
    """一条分类规则：路径前缀 -> 是否热重载 + 原因。"""

    path: str
    hot_reload: bool
    reason: str = ""

    @property
    def parts(self) -> tuple[str, ...]:
        return tuple(part for part in self.path.split(".") if part)


#: 规则表：按路径前缀匹配，最长前缀优先；同长度时以更靠后的规则为准（便于覆盖）。
RULES: tuple[HotReloadRule, ...] = (
    # ── 需要重启（启动期快照）────────────────────────────────
    HotReloadRule("bot.account", False, "机器人账号在启动时用于登录与适配器初始化"),
    HotReloadRule("chat.key_word", False, "关键词规则在启动时构建快照（KeywordReactionBuilder）"),
    HotReloadRule("chat.cache_retention_seconds", False, "缓存计算器参数在启动时读取"),
    HotReloadRule("chat.cache_hit_price_difference", False, "缓存计算器参数在启动时读取"),
    HotReloadRule("chat.enable_balance_check", False, "余额检查器在启动时构建"),
    HotReloadRule("chat.balance_threshold", False, "余额检查器在启动时构建"),
    HotReloadRule("chat.balance_check_cooldown_seconds", False, "余额检查器在启动时构建"),
    HotReloadRule("chat.admin_accounts", False, "余额检查器在启动时构建"),
    HotReloadRule("models", False, "运行中的 Provider 已固化模型名 / 密钥 / base_url，需重启重建"),
    HotReloadRule("tts", False, "TTS 服务在启动时构建"),
    HotReloadRule("adapter", False, "连接适配器在启动时建立"),
    HotReloadRule("file_server", False, "文件服务器在启动时启动"),
    HotReloadRule("plugins", False, "插件运行时与插件目录在启动时确定"),
    HotReloadRule("debug", False, "调试记录器在启动时构建"),
    HotReloadRule("agent", False, "Agent、工具与技能在启动时装配"),
    HotReloadRule("scheduled_task", False, "定时任务管理器在启动时构建"),
    HotReloadRule("dashboard.host", False, "面板监听地址在启动时绑定"),
    HotReloadRule("dashboard.port", False, "面板端口在启动时绑定"),
    HotReloadRule("dashboard.base_path", False, "面板路径前缀在启动时注册路由"),
    HotReloadRule("dashboard.enabled", False, "面板启停在启动时决定"),
    HotReloadRule("dashboard.session_timeout_minutes", False, "会话表在启动时创建"),
    HotReloadRule("dashboard.secure_cookies", False, "Cookie 属性在启动时确定"),
    HotReloadRule("dashboard.trust_proxy_headers", False, "代理头信任在启动时确定"),
    HotReloadRule("dashboard.log_buffer_size", False, "日志缓冲在启动时创建"),
    HotReloadRule("dashboard.bot_info_cache_ttl", False, "机器人信息缓存在启动时创建"),
    HotReloadRule("dashboard.history_max_days", False, "统计历史窗口在启动时创建"),
    HotReloadRule("dashboard.login_max_failures", False, "登录限速器在启动时创建"),
    HotReloadRule("dashboard.login_rate_limit_window_seconds", False, "登录限速器在启动时创建"),
    # ── 无需重启（运行时按需读取）────────────────────────────
    HotReloadRule("chat", True, "聊天管线按需读取配置，重载后立即生效"),
    HotReloadRule("bot", True, "人设与昵称在生成回复时读取"),
    HotReloadRule("willing", True, "回复意愿按需读取"),
    HotReloadRule("message", True, "消息处理按需读取"),
    HotReloadRule("dashboard.manage_plugins", True, "面板权限实时读取"),
    HotReloadRule("dashboard.allow_remote_manage", True, "面板权限实时读取"),
)


def _rule_for(path: Iterable[str]) -> HotReloadRule | None:
    parts = tuple(str(part) for part in path if str(part))
    best: HotReloadRule | None = None
    best_len = -1
    for rule in RULES:
        rule_parts = rule.parts
        if len(rule_parts) > len(parts):
            continue
        if parts[: len(rule_parts)] != rule_parts:
            continue
        if len(rule_parts) >= best_len:
            best = rule
            best_len = len(rule_parts)
    return best


def classify(path: Iterable[str]) -> tuple[bool, str]:
    """返回 (是否热重载, 原因)。未登记路径按「需要重启」处理。"""
    rule = _rule_for(path)
    if rule is None:
        return False, "未登记为热重载配置，按需要重启处理"
    return rule.hot_reload, rule.reason


def is_hot_reloadable(path: Iterable[str]) -> bool:
    return classify(path)[0]


# ----------------------------------------------------------------------
# 配置差异
# ----------------------------------------------------------------------


def _flatten(value: Any, prefix: tuple[str, ...] = ()) -> dict[str, Any]:
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if isinstance(value, Mapping):
        flattened: dict[str, Any] = {}
        for key, item in value.items():
            flattened.update(_flatten(item, (*prefix, str(key))))
        return flattened
    if isinstance(value, (list, tuple)):
        return {".".join(prefix): list(value)}
    return {".".join(prefix): value}


def _inner(config: Any) -> Any:
    return getattr(config, "_inner", config)


def _display(value: Any) -> str:
    text = str(value)
    if len(text) > MAX_VALUE_CHARS:
        return text[:MAX_VALUE_CHARS] + "…"
    return text


@dataclass(frozen=True, slots=True)
class ConfigChange:
    """一处配置改动及其生效方式。"""

    path: str
    before: str
    after: str
    hot_reload: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "before": self.before,
            "after": self.after,
            "hot_reload": self.hot_reload,
            "reason": self.reason,
        }


def snapshot(config: Any) -> dict[str, Any]:
    """把配置对象拍平成 路径 -> 值 的快照，便于重载前后比较。"""
    return _flatten(_inner(config))


def diff_snapshot(before: Mapping[str, Any], after: Any) -> list[ConfigChange]:
    """用重载前的快照与重载后的配置比较。"""
    return _diff_maps(dict(before), _flatten(_inner(after)))


def diff_configs(before: Any, after: Any) -> list[ConfigChange]:
    """比较两份配置对象，返回改动的配置项及其热重载结论。"""
    return _diff_maps(_flatten(_inner(before)), _flatten(_inner(after)))


def _diff_maps(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[ConfigChange]:
    changes: list[ConfigChange] = []
    for path in sorted(set(old) | set(new)):
        old_value = old.get(path)
        new_value = new.get(path)
        if old_value == new_value:
            continue
        hot, reason = classify(path.split("."))
        changes.append(
            ConfigChange(
                path=path,
                before=_display(old_value),
                after=_display(new_value),
                hot_reload=hot,
                reason=reason,
            )
        )
    return changes


def summarize_changes(changes: Iterable[ConfigChange]) -> dict[str, Any]:
    """把改动列表汇总为「已生效 / 需重启」两组。"""
    hot = [item.to_dict() for item in changes if item.hot_reload]
    restart = [item.to_dict() for item in changes if not item.hot_reload]
    return {
        "hot_reload": hot,
        "needs_restart": restart,
        "hot_reload_count": len(hot),
        "needs_restart_count": len(restart),
    }

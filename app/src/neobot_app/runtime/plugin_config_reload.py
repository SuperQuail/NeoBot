"""插件配置「原地生效」的判定与编排。

对应 bugfixes/feat(2) §6：面板保存插件配置时，**运行期安全**的字段应立刻生效，
而不是一律提示「需要重启 NeoBot」。

职责划分（复用优先，不新造机制）：
- modloader 侧只提供「插件配置消费者」的登记通道（PluginControlFacade.register_config_consumer），
  它不关心配置项语义；
- 插件自己声明关心哪些键、以及每个键是「运行期安全」还是「需要重启」（hot_reload_policies）；
- 本模块负责**判定**（哪些改动可以原地生效）与**编排**（调用 apply_config、失败保留旧配置）。

路径命名空间统一为 plugin.<插件名>.<配置键>，与本体配置的 config.hot_reload 前缀风格一致，
但**不写入本体分类表**：插件配置不属于本体 config.toml，混在一起会让面板的本体配置页出现幻觉条目。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

#: 插件配置路径命名空间前缀：plugin.<插件名>.<配置键>
PLUGIN_PATH_PREFIX = "plugin"


def plugin_config_path(plugin_name: str, key: str) -> str:
    """把插件配置键映射为带命名空间的路径。"""
    name = str(plugin_name or "").strip()
    item = str(key or "").strip()
    return f"{PLUGIN_PATH_PREFIX}.{name}.{item}"


def _policy_entries(consumer: Any) -> tuple[tuple[str, bool, str], ...]:
    """读取消费者声明的生效方式，容忍缺失 / 异构形态。"""
    entries: list[tuple[str, bool, str]] = []
    for item in tuple(getattr(consumer, "hot_reload_policies", ()) or ()):
        path = str(getattr(item, "path", "") or "").strip()
        if not path:
            continue
        entries.append(
            (path, bool(getattr(item, "hot_reload", False)), str(getattr(item, "reason", "") or ""))
        )
    return tuple(entries)


def classify_plugin_path(consumer: Any, path: str) -> tuple[bool, str]:
    """按「最长前缀优先」判定某个插件配置路径是否可原地生效。

    未命中的路径一律按「需要重启」处理（与本体 config.hot_reload 的保守假设一致），
    避免新增字段因为忘记登记而被错误地当成热重载项。
    """
    best: tuple[bool, str] | None = None
    best_len = -1
    parts = tuple(part for part in str(path).split(".") if part)
    for rule_path, hot, reason in _policy_entries(consumer):
        rule_parts = tuple(part for part in rule_path.split(".") if part)
        if len(rule_parts) > len(parts) or parts[: len(rule_parts)] != rule_parts:
            continue
        if len(rule_parts) >= best_len:
            best = (hot, reason)
            best_len = len(rule_parts)
    if best is None:
        return False, "该配置项未声明运行期生效方式，按需要重启处理"
    return best


@dataclass(frozen=True, slots=True)
class PluginConfigChange:
    """一处插件配置改动及其生效方式。"""

    path: str
    key: str
    before: Any
    after: Any
    hot_reload: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "key": self.key,
            "before": self.before,
            "after": self.after,
            "hot_reload": self.hot_reload,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PluginConfigApplyResult:
    """一次插件配置原地生效的结论。"""

    ok: bool = False
    applied: tuple[str, ...] = ()
    needs_restart: tuple[str, ...] = ()
    error: str = ""
    changes: tuple[PluginConfigChange, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.applied or self.needs_restart)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "applied": list(self.applied),
            "needs_restart": list(self.needs_restart),
        }
        if self.error:
            payload["error"] = self.error
        return payload


def diff_plugin_config(
    consumer: Any,
    *,
    plugin_name: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> list[PluginConfigChange]:
    """比较保存前后的插件生效配置，返回改动项及其生效方式。"""
    old = dict(before or {})
    new = dict(after or {})
    changes: list[PluginConfigChange] = []
    for key in sorted(set(old) | set(new)):
        if old.get(key) == new.get(key):
            continue
        path = plugin_config_path(plugin_name, key)
        hot, reason = classify_plugin_path(consumer, path)
        changes.append(
            PluginConfigChange(
                path=path,
                key=str(key),
                before=old.get(key),
                after=new.get(key),
                hot_reload=hot,
                reason=reason,
            )
        )
    return changes


async def apply_plugin_config_change(
    consumer: Any,
    *,
    plugin_name: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> PluginConfigApplyResult:
    """把「运行期安全」的插件配置改动原地喂给插件。

    - 没有可原地生效的改动时**不会**调用 apply_config，也不报错（调用方沿用「需要重启」提示）；
    - apply_config 抛异常时原样返回错误，**旧配置保持不变**（由消费者保证不部分应用）；
    - 未声明 hot_reload_policies 的消费者 => 所有改动都按需要重启处理。
    """
    changes = diff_plugin_config(
        consumer, plugin_name=plugin_name, before=before, after=after
    )
    hot = tuple(item.key for item in changes if item.hot_reload)
    restart = tuple(item.key for item in changes if not item.hot_reload)
    if not hot:
        return PluginConfigApplyResult(
            ok=False, needs_restart=restart, changes=tuple(changes)
        )
    try:
        await consumer.apply_config(dict(after or {}))
    except Exception as exc:
        return PluginConfigApplyResult(
            ok=False,
            needs_restart=restart,
            error=f"{type(exc).__name__}: {exc}",
            changes=tuple(changes),
        )
    return PluginConfigApplyResult(
        ok=True, applied=hot, needs_restart=restart, changes=tuple(changes)
    )


def diff_summary(changes: Iterable[PluginConfigChange]) -> dict[str, Any]:
    """与本体 config.hot_reload.summarize_changes 同构的汇总（面板前端可直接复用）。"""
    hot = [item.to_dict() for item in changes if item.hot_reload]
    restart = [item.to_dict() for item in changes if not item.hot_reload]
    return {
        "hot_reload": hot,
        "needs_restart": restart,
        "hot_reload_count": len(hot),
        "needs_restart_count": len(restart),
    }


__all__ = [
    "PLUGIN_PATH_PREFIX",
    "PluginConfigApplyResult",
    "PluginConfigChange",
    "apply_plugin_config_change",
    "classify_plugin_path",
    "diff_plugin_config",
    "diff_summary",
    "plugin_config_path",
]

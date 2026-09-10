"""热重载注册表测试。

这里锁死的是「开闭原则」那条设计约束：新增一个可热重载子系统应当只是
**多一次注册**，重载编排代码不动。因此测试里用的都是测试自定义的消费者，
注册表不需要认识任何具体组件。
"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_app.config.hot_reload import (
    HotReloadRule,
    classify,
    register_rule,
    unregister_rule,
)
from neobot_app.runtime.hot_reload_registry import (
    ConfigConsumer,
    HotReloadRegistry,
    ReloadOutcome,
)
from neobot_contracts.ports.logging import NullLogger


class _Consumer:
    """测试用消费者：记录被调用时拿到的配置。"""

    def __init__(
        self,
        name: str,
        paths: tuple[str, ...],
        *,
        policies: tuple[HotReloadRule, ...] = (),
        error: Exception | None = None,
    ) -> None:
        self._name = name
        self.config_paths = paths
        self.hot_reload_policies = policies
        self._error = error
        self.applied: list[Any] = []

    @property
    def name(self) -> str:
        return self._name

    async def apply_config(self, config: Any) -> None:
        if self._error is not None:
            raise self._error
        self.applied.append(config)


# ── 协议与注册 ──────────────────────────────────────────────────────


def test_consumer_satisfies_protocol() -> None:
    assert isinstance(_Consumer("a", ("adapter",)), ConfigConsumer)


def test_non_consumer_is_rejected() -> None:
    class _Incomplete:
        name = "x"

    with pytest.raises(TypeError, match="热重载消费者"):
        HotReloadRegistry().register(_Incomplete())  # type: ignore[arg-type]


def test_duplicate_name_registration_is_idempotent() -> None:
    registry = HotReloadRegistry(logger=NullLogger())
    first = _Consumer("same", ("adapter",))
    second = _Consumer("same", ("models",))

    registry.register(first)
    registry.register(second)

    assert registry.consumers == (first,)


# ── 分发：只调用声明关心的组件 ──────────────────────────────────────


async def test_only_interested_consumers_are_invoked() -> None:
    adapter = _Consumer("adapter", ("adapter",))
    models = _Consumer("models", ("models",))
    registry = HotReloadRegistry([adapter, models])

    report = await registry.apply(object(), ["adapter.reverse_ws_port"])

    assert report.applied == ("adapter",)
    assert models.applied == []


async def test_all_interested_consumers_are_invoked() -> None:
    adapter = _Consumer("adapter", ("adapter",))
    models = _Consumer("models", ("models",))
    registry = HotReloadRegistry([adapter, models])

    report = await registry.apply(object(), ["adapter.reverse_ws_port", "models.assignments"])

    assert set(report.applied) == {"adapter", "models"}


def test_prefix_match_does_not_leak_to_sibling_names() -> None:
    """``adapter`` 不该命中 ``adapter_x``（点分前缀匹配，不是字符串前缀）。"""
    registry = HotReloadRegistry([_Consumer("adapter", ("adapter",))])

    assert registry.consumers_for(["adapter.reverse_ws_port"])
    assert registry.consumers_for(["adapter"]) == registry.consumers
    assert registry.consumers_for(["adapter_x.field"]) == ()


def test_no_changed_paths_selects_nothing() -> None:
    registry = HotReloadRegistry([_Consumer("adapter", ("adapter",))])

    assert registry.consumers_for([]) == ()


def test_registration_order_is_preserved() -> None:
    first = _Consumer("first", ("adapter",))
    second = _Consumer("second", ("adapter",))
    registry = HotReloadRegistry([first, second])

    assert registry.consumers_for(["adapter"]) == (first, second)


# ── 失败隔离 ────────────────────────────────────────────────────────


async def test_one_failure_does_not_block_others() -> None:
    broken = _Consumer("broken", ("adapter",), error=RuntimeError("boom"))
    healthy = _Consumer("healthy", ("adapter",))
    registry = HotReloadRegistry([broken, healthy], logger=NullLogger())

    report = await registry.apply(object(), ["adapter"])

    assert report.applied == ("healthy",)
    assert report.failed_count == 1
    assert report.failed[0].name == "broken"
    assert "boom" in report.failed[0].error
    assert healthy.applied != []


async def test_report_summary_mentions_failures() -> None:
    broken = _Consumer("broken", ("adapter",), error=RuntimeError("boom"))
    registry = HotReloadRegistry([broken], logger=NullLogger())

    report = await registry.apply(object(), ["adapter"])

    assert "1 个失败" in report.summary()


async def test_report_when_nothing_interested() -> None:
    registry = HotReloadRegistry([_Consumer("models", ("models",))])

    report = await registry.apply(object(), ["chat.reply_mode"])

    assert report.outcomes == ()
    assert "没有组件声明关心" in report.summary()


async def test_report_serializes_for_panel() -> None:
    registry = HotReloadRegistry([_Consumer("adapter", ("adapter",))])

    payload = (await registry.apply(object(), ["adapter"])).to_dict()

    assert payload["applied_count"] == 1
    assert payload["failed_count"] == 0
    assert payload["applied"][0]["name"] == "adapter"
    assert payload["changed_paths"] == ["adapter"]


def test_outcome_dict_omits_empty_error() -> None:
    assert ReloadOutcome("a", True).to_dict() == {"name": "a", "applied": True}
    assert ReloadOutcome("a", False, "x").to_dict() == {
        "name": "a",
        "applied": False,
        "error": "x",
    }


# ── 规则自注册（开闭原则） ──────────────────────────────────────────


def test_registered_policies_upgrade_classification() -> None:
    """组件注册时把「需重启」升级为「可在运行期生效」，无需改分类表。"""
    path = "unit_test_subsystem"
    from neobot_app.config.hot_reload import classify as fresh_classify

    assert fresh_classify([path])[0] is False  # 未登记 → 保守按需重启
    try:
        HotReloadRegistry(
            [_Consumer("unit", (path,), policies=(HotReloadRule(path, True, "运行期重建"),))]
        )
        assert fresh_classify([path]) == (True, "运行期重建")
    finally:
        unregister_rule(path)
    assert fresh_classify([path])[0] is False


def test_register_rule_replaces_same_path() -> None:
    path = "unit_test_replace"
    register_rule(HotReloadRule(path, False, "旧结论"))
    try:
        register_rule(HotReloadRule(path, True, "新结论"))
        assert classify([path]) == (True, "新结论")
    finally:
        unregister_rule(path)


@pytest.mark.parametrize("path", ["models", "adapter"])
def test_core_classification_defaults_stay_conservative_without_registration(
    path: str,
) -> None:
    """分类表本身不认识任何组件：没注册就是「需重启」。"""
    assert classify([path])[0] is False

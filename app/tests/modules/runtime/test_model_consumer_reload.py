"""通用「模型产物重建」消费者：接入一行，失败互不牵连。

背景：provider 之外还有组件把模型条目固化在自己身上（TTS 服务、生图服务……），
它们以前只在启动期装配一次，于是「先在面板里配好 Key，再重载」走不通。
本用例钉住通用重建器的三条契约：

1. 重建时拿到的是**新** config（不是闭包里的旧值）；
2. 与 provider 消费者同源：models 与 env 两条路径都会选中它；
3. 失败隔离：一个组件抛异常不影响其它组件（注册表逐个隔离，见 apply 的实现）。
"""

from __future__ import annotations

from typing import Any

from neobot_app.runtime.hot_reload_registry import HotReloadRegistry
from neobot_app.runtime.provider_reload import ModelConsumerReload


def _preserve_global_rules(*paths: str):
    """注册消费者会改写进程级全局规则表，用完必须还原（否则污染后续用例的分类基线）。

    不能直接用 unregister_rule：那会把基线条目一起删掉。
    """
    from contextlib import contextmanager

    from neobot_app.config import hot_reload

    @contextmanager
    def _ctx():
        backup = {
            path: next((rule for rule in hot_reload.RULES if rule.path == path), None)
            for path in paths
        }
        try:
            yield
        finally:
            hot_reload.RULES = tuple(
                rule for rule in hot_reload.RULES if rule.path not in paths
            )
            for rule in backup.values():
                if rule is not None:
                    hot_reload.register_rule(rule)

    return _ctx()


def test_rebuild_receives_the_new_config() -> None:
    """重建函数必须拿到新 config —— 否则「换装」换的还是旧模型。"""
    seen: list[Any] = []
    consumer = ModelConsumerReload(name="tts", rebuild=lambda cfg: seen.append(cfg))

    new_config = object()
    import asyncio

    with _preserve_global_rules("models", "env"):
        registry = HotReloadRegistry()
        registry.register(consumer)
        asyncio.run(registry.apply(new_config, ["env"]))

    assert seen == [new_config]


def test_models_path_also_selects_the_component_consumer() -> None:
    """模型库变更同样要重建（不只是 .env）—— 两者是同一个消费者关心的两条路径。"""
    consumer = ModelConsumerReload(name="tts", rebuild=lambda cfg: None)

    assert consumer.config_paths == ("models", "env")
    with _preserve_global_rules("models", "env"):
        registry = HotReloadRegistry()
        registry.register(consumer)
        assert registry.consumers_for(["models"]) == (consumer,)
        assert registry.consumers_for(["env"]) == (consumer,)


def test_one_component_failure_does_not_block_others() -> None:
    """TTS 建不起来不能拖垮 provider 的重建：失败的记失败，其余照常生效。"""
    import asyncio

    applied: list[str] = []

    def _boom(config: Any) -> None:
        raise RuntimeError("TTS 模型仍未注册")

    failing = ModelConsumerReload(name="tts", rebuild=_boom)
    healthy = ModelConsumerReload(name="creator_image", rebuild=lambda cfg: applied.append("creator"))

    with _preserve_global_rules("models", "env"):
        registry = HotReloadRegistry()
        registry.register(failing)
        registry.register(healthy)
        report = asyncio.run(registry.apply(object(), ["env"]))

    assert applied == ["creator"]
    assert report.applied == ("creator_image",)
    assert [item.name for item in report.failed] == ["tts"]
    assert "TTS 模型仍未注册" in report.failed[0].error


def test_consumer_declares_its_own_reason() -> None:
    """每个组件的热重载结论要能自解释（面板/报告里直接展示这条 reason）。"""
    consumer = ModelConsumerReload(name="tts", rebuild=lambda cfg: None, reason="TTS 凭据变更后重建")

    policies = consumer.hot_reload_policies
    assert {rule.path for rule in policies} == {"models", "env"}
    assert all(rule.hot_reload is True for rule in policies)
    assert all(rule.reason == "TTS 凭据变更后重建" for rule in policies)

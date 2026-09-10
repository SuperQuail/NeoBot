"""provider 热重载消费者测试（模型 / API Key 变更后重建）。

关键契约：
1. 全部挂载点替换成功后才关闭旧 provider；
2. 新 provider 建不起来时**整体放弃并保留旧 provider** —— 宁可维持现状，
   也不要变成「配错一次就彻底不回复」；
3. 挂载点由注入决定，本模块不认识任何具体服务（依赖倒置）。
"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_app.runtime.provider_reload import (
    ProviderBundle,
    ProviderReloadConsumer,
)
from neobot_contracts.ports.logging import NullLogger


class _Provider:
    def __init__(self, model: str = "new-model") -> None:
        self.model = model
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _MountPoint:
    """模拟一个持有 provider 的挂载点：install_* 换引用并返回旧对象。"""

    def __init__(self, current: Any = None) -> None:
        self.current = current
        self.installed: list[Any] = []

    def install(self, provider: Any) -> Any:
        previous = self.current
        self.current = provider
        self.installed.append(provider)
        return previous


def _consumer(
    mount: _MountPoint,
    *,
    bundle: ProviderBundle | None = None,
    extra_mounts: dict[str, _MountPoint] | None = None,
    logger: Any = None,
) -> ProviderReloadConsumer:
    installers: dict[str, tuple[Any, Any]] = {
        "reply": (
            lambda b: mount.install(b.main),
            lambda previous: previous.close(),
        )
    }
    for label, target in (extra_mounts or {}).items():
        installers[label] = (
            lambda b, target=target: target.install(b.main),
            lambda _previous: None,
        )

    def _build(_config: Any) -> ProviderBundle:
        return bundle if bundle is not None else ProviderBundle(main=_Provider())

    return ProviderReloadConsumer(
        builder=_build, installers=installers, logger=logger or NullLogger()
    )


# ── 正常重建 ────────────────────────────────────────────────────────


async def test_rebuild_swaps_provider() -> None:
    old = _Provider("old-model")
    mount = _MountPoint(old)
    new = _Provider("new-model")
    consumer = _consumer(mount, bundle=ProviderBundle(main=new))

    await consumer.apply_config(object())

    assert mount.current is new
    assert new.closed is False


async def test_previous_provider_is_closed_after_successful_swap() -> None:
    old = _Provider("old-model")
    mount = _MountPoint(old)
    consumer = _consumer(mount, bundle=ProviderBundle(main=_Provider("new-model")))

    await consumer.apply_config(object())

    assert old.closed is True


async def test_all_mounts_are_updated() -> None:
    first = _MountPoint()
    second = _MountPoint()
    new = _Provider()
    consumer = _consumer(
        first, bundle=ProviderBundle(main=new), extra_mounts={"second": second}
    )

    await consumer.apply_config(object())

    assert first.current is new
    assert second.current is new


# ── 失败保持现状 ────────────────────────────────────────────────────


async def test_unavailable_new_provider_keeps_current_one() -> None:
    """新配置下主模型不可用：保留旧 provider，并明确报错。"""
    old = _Provider("working")
    mount = _MountPoint(old)
    consumer = _consumer(
        mount,
        bundle=ProviderBundle(main=None, main_error="缺少 DeepSeek_APIKey 配置"),
    )

    with pytest.raises(RuntimeError, match="缺少 DeepSeek_APIKey 配置"):
        await consumer.apply_config(object())

    assert mount.current is old
    assert old.closed is False


async def test_install_failure_does_not_close_previous_providers() -> None:
    """某个挂载点安装失败时，绝不关闭任何旧 provider（避免悬空引用）。"""
    old = _Provider("working")
    mount = _MountPoint(old)
    new = _Provider("new")

    def _boom(_bundle: ProviderBundle) -> Any:
        raise RuntimeError("install failed")

    consumer = ProviderReloadConsumer(
        builder=lambda _c: ProviderBundle(main=new),
        installers={"reply": (lambda b: mount.install(b.main), lambda p: p.close()),
                    "broken": (_boom, lambda _p: None)},
        logger=NullLogger(),
    )

    with pytest.raises(RuntimeError, match="install failed"):
        await consumer.apply_config(object())

    assert old.closed is False


async def test_dispose_failure_is_swallowed() -> None:
    """关闭旧 provider 失败不应影响「新 provider 已生效」这个事实。"""
    old = _Provider("old")
    mount = _MountPoint(old)
    new = _Provider("new")

    def _explode(_previous: Any) -> None:
        raise OSError("already closed")

    consumer = ProviderReloadConsumer(
        builder=lambda _c: ProviderBundle(main=new),
        installers={"reply": (lambda b: mount.install(b.main), _explode)},
        logger=NullLogger(),
    )

    await consumer.apply_config(object())

    assert mount.current is new


# ── 声明与状态 ──────────────────────────────────────────────────────


def test_consumer_declares_models_scope() -> None:
    consumer = _consumer(_MountPoint())

    assert consumer.name == "provider"
    assert consumer.config_paths == ("models",)
    policies = consumer.hot_reload_policies
    assert policies[0].path == "models"
    assert policies[0].hot_reload is True


async def test_builder_receives_the_new_config() -> None:
    seen: list[Any] = []
    marker = object()

    def _build(config: Any) -> ProviderBundle:
        seen.append(config)
        return ProviderBundle(main=_Provider())

    consumer = ProviderReloadConsumer(
        builder=_build,
        installers={"reply": (lambda b: None, lambda _p: None)},
        logger=NullLogger(),
    )

    await consumer.apply_config(marker)

    assert seen == [marker]

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from neobot_modloader.plugins.agents import PluginAgentRegistrar


class _LegacyRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    @property
    def names(self) -> list[str]:
        return list(self.agents)

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        return self.agents.pop(name, None)


class _RetryCloseAgent:
    description = "retry"
    tool_definitions: list[dict[str, Any]] = []

    def __init__(self) -> None:
        self.close_count = 0
        self.cancel_close = False

    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return state

    async def stream_invoke(self, state: dict[str, Any]):
        if False:
            yield state

    async def close(self) -> None:
        self.close_count += 1
        if self.cancel_close:
            self.cancel_close = False
            raise asyncio.CancelledError
        if self.close_count == 1:
            raise RuntimeError("legacy close failed")


async def test_legacy_close_failure_retains_agent_and_retries() -> None:
    registry = _LegacyRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="legacy", registry=registry, record_registration=None
    )
    agent = _RetryCloseAgent()
    name = registrar.register("worker", agent)

    with pytest.raises(RuntimeError, match="legacy close failed"):
        await registrar.unregister_and_drain(name)
    assert registrar._pending_close[name] is agent

    assert await registrar.unregister_and_drain(name) is agent
    assert agent.close_count == 2
    assert registrar._pending_close == {}


async def test_legacy_close_cancellation_retains_agent_and_retries() -> None:
    registry = _LegacyRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="legacy", registry=registry, record_registration=None
    )
    agent = _RetryCloseAgent()
    agent.close_count = 1
    agent.cancel_close = True
    name = registrar.register("worker", agent)

    with pytest.raises(asyncio.CancelledError):
        await registrar.unregister_and_drain(name)
    assert registrar._pending_close[name] is agent

    assert await registrar.unregister_and_drain(name) is agent
    assert agent.close_count == 3
    assert registrar._pending_close == {}


def test_sync_unregister_retains_legacy_agent_ownership() -> None:
    registry = _LegacyRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="legacy", registry=registry, record_registration=None
    )
    agent = _RetryCloseAgent()
    name = registrar.register("worker", agent)

    assert registrar.unregister(name) is agent
    assert registrar._pending_close[name] is agent


class _SimpleAgent:
    description = "simple"
    tool_definitions: list[dict[str, Any]] = []

    def __init__(self) -> None:
        self.close_count = 0

    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return state

    async def stream_invoke(self, state: dict[str, Any]):
        if False:
            yield state

    async def close(self) -> None:
        self.close_count += 1


async def test_sync_unregister_pins_only_until_drain_closes_exactly_once() -> None:
    """注册表仍开放时同步 unregister 挂起实例；后续 unregister_and_drain 关闭
    恰好一次并解除挂起。"""
    from neobot_chat.tools.registry import AgentRegistry

    registry = AgentRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="p", registry=registry, record_registration=None
    )
    agent = _SimpleAgent()
    name = registrar.register("worker", agent)

    assert registrar.unregister(name) is agent
    assert registrar._pending_close[name] is agent
    assert await registrar.unregister_and_drain(name) is agent
    assert agent.close_count == 1
    assert registrar._pending_close == {}
    await registry.close()


async def test_sync_unregister_after_registry_closed_does_not_pin() -> None:
    """注册表已关闭时同步 unregister 不得挂起实例：关闭清扫已关闭实例，
    挂起只会造成永久强持有泄漏。"""
    from neobot_chat.tools.registry import AgentRegistry

    registry = AgentRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="p", registry=registry, record_registration=None
    )
    agent = _SimpleAgent()
    name = registrar.register("worker", agent)

    await registry.close()
    assert agent.close_count == 1

    removed = registrar.unregister(name)
    assert removed is agent
    assert registrar._pending_close == {}
    assert registrar._registered == {}
    assert agent.close_count == 1


async def test_sync_unregister_after_close_clears_pending_close() -> None:
    """已挂起实例后注册表关闭，同步 unregister 必须同时清掉 _pending_close，
    使实例可被回收，而不是被永久强持有。"""
    import gc
    import weakref

    from neobot_chat.tools.registry import AgentRegistry

    registry = AgentRegistry()
    registrar = PluginAgentRegistrar(
        plugin_name="p", registry=registry, record_registration=None
    )
    agent = _SimpleAgent()
    name = registrar.register("worker", agent)

    assert registrar.unregister(name) is agent
    assert registrar._pending_close[name] is agent

    await registry.close()
    assert agent.close_count == 1

    assert registrar.unregister(name) is None
    assert registrar._pending_close == {}
    assert registrar._registered == {}

    agent_ref = weakref.ref(agent)
    del agent
    for _ in range(10):
        gc.collect()
        if agent_ref() is None:
            break
        await asyncio.sleep(0)
    assert agent_ref() is None

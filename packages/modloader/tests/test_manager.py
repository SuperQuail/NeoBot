from __future__ import annotations

import unittest
from typing import Any

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.manager import DefaultPluginManager


class FakeAgentRegistrar:
    def __init__(self) -> None:
        self.unregistered: list[str] = []

    def unregister(self, registered_name: str) -> None:
        self.unregistered.append(registered_name)


class FakeContext:
    def __init__(self, plugin_name: str = "plugin") -> None:
        self.plugin_name = plugin_name
        self.agents = FakeAgentRegistrar()


class FakeAgent:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class FakeSubscription:
    def __init__(self) -> None:
        self.unsubscribed = False

    def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakePlugin:
    name = "plugin"
    version = "0.1.0"

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_load = False
        self.fail_start = False
        self.fail_stop = False

    async def on_load(self, ctx: Any) -> None:
        self.calls.append("load")
        if self.fail_load:
            raise RuntimeError("load")

    async def on_start(self) -> None:
        self.calls.append("start")
        if self.fail_start:
            raise RuntimeError("start")

    async def on_stop(self) -> None:
        self.calls.append("stop")
        if self.fail_stop:
            raise RuntimeError("stop")


class DefaultPluginManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_states_and_subscription_cleanup(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        subscription = FakeSubscription()
        manager.register(plugin, FakeContext())
        manager.record_subscription("plugin", subscription)

        await manager.load_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.LOADED)
        await manager.start_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.RUNNING)
        await manager.stop_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.STOPPED)
        self.assertTrue(subscription.unsubscribed)
        self.assertEqual(plugin.calls, ["load", "start", "stop"])

    async def test_load_failure_sets_error_and_cleans_subscriptions(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_load = True
        subscription = FakeSubscription()
        manager.register(plugin, FakeContext())
        manager.record_subscription("plugin", subscription)

        await manager.load_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertTrue(subscription.unsubscribed)

    async def test_start_failure_sets_error_and_cleans_subscriptions(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_start = True
        subscription = FakeSubscription()
        manager.register(plugin, FakeContext())
        manager.record_subscription("plugin", subscription)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertTrue(subscription.unsubscribed)

    async def test_stop_failure_does_not_prevent_stopped_state(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_stop = True
        manager.register(plugin, FakeContext())

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")
        self.assertEqual(manager.get_state("plugin"), PluginState.STOPPED)

    async def test_stop_cleans_agent_registrations(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        context = FakeContext()
        agent = FakeAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin:plugin:echo", agent)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")

        self.assertEqual(context.agents.unregistered, ["plugin:plugin:echo"])
        self.assertTrue(agent.closed)

    async def test_load_failure_cleans_agent_registrations(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_load = True
        context = FakeContext()
        agent = FakeAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin:plugin:echo", agent)

        await manager.load_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertEqual(context.agents.unregistered, ["plugin:plugin:echo"])
        self.assertTrue(agent.closed)

    async def test_start_failure_cleans_agent_registrations(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_start = True
        context = FakeContext()
        agent = FakeAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin:plugin:echo", agent)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertEqual(context.agents.unregistered, ["plugin:plugin:echo"])
        self.assertTrue(agent.closed)


if __name__ == "__main__":
    unittest.main()

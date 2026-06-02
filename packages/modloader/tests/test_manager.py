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
    capabilities = {"echo": lambda payload: {"echo": payload.get("text", "")}}

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


class SlowLoadPlugin(FakePlugin):
    async def on_load(self, ctx: Any) -> None:
        import asyncio

        await asyncio.sleep(0.01)
        await super().on_load(ctx)


class ObservingPlugin(FakePlugin):
    def __init__(self, manager: DefaultPluginManager, name: str = "plugin") -> None:
        super().__init__()
        self.manager = manager
        self.name = name
        self.observed: list[PluginState] = []

    async def on_load(self, ctx: Any) -> None:
        self.observed.append(self.manager.get_state(self.name))
        await super().on_load(ctx)

    async def on_start(self) -> None:
        self.observed.append(self.manager.get_state(self.name))
        await super().on_start()

    async def on_stop(self) -> None:
        self.observed.append(self.manager.get_state(self.name))
        await super().on_stop()


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
        manager.record_agent_registration("plugin", "plugin.echo", agent)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")

        self.assertEqual(context.agents.unregistered, ["plugin.echo"])
        self.assertTrue(agent.closed)

    async def test_registry_view_returns_restricted_handle(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        manager.register(plugin, FakeContext())

        registry = manager.registry_view
        handle = registry.get("plugin")

        self.assertIsNotNone(handle)
        assert handle is not None
        self.assertEqual(registry.names(), ["plugin"])
        self.assertTrue(registry.has("plugin"))
        self.assertEqual(handle.name, "plugin")
        self.assertEqual(handle.version, "0.1.0")
        self.assertEqual(handle.capabilities, ("echo",))
        self.assertEqual(await handle.call("echo", {"text": "hi"}), {"echo": "hi"})
        with self.assertRaises(KeyError):
            await handle.call("missing", {})

    async def test_load_failure_cleans_agent_registrations(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_load = True
        context = FakeContext()
        agent = FakeAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin.echo", agent)

        await manager.load_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])
        self.assertTrue(agent.closed)

    async def test_start_failure_cleans_agent_registrations(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_start = True
        context = FakeContext()
        agent = FakeAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin.echo", agent)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])
        self.assertTrue(agent.closed)

    async def test_concurrent_load_only_runs_once(self) -> None:
        import asyncio

        manager = DefaultPluginManager()
        plugin = SlowLoadPlugin()
        manager.register(plugin, FakeContext())

        await asyncio.gather(manager.load_plugin("plugin"), manager.load_plugin("plugin"))

        self.assertEqual(manager.get_state("plugin"), PluginState.LOADED)
        self.assertEqual(plugin.calls, ["load"])

    async def test_intermediate_lifecycle_states_are_observable(self) -> None:
        manager = DefaultPluginManager()
        plugin = ObservingPlugin(manager)
        manager.register(plugin, FakeContext())

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")

        self.assertEqual(
            plugin.observed,
            [PluginState.LOADING, PluginState.STARTING, PluginState.STOPPING],
        )

    async def test_concurrent_start_only_runs_once(self) -> None:
        import asyncio

        manager = DefaultPluginManager()
        plugin = SlowLoadPlugin()
        manager.register(plugin, FakeContext())
        await manager.load_plugin("plugin")

        await asyncio.gather(manager.start_plugin("plugin"), manager.start_plugin("plugin"))

        self.assertEqual(manager.get_state("plugin"), PluginState.RUNNING)
        self.assertEqual(plugin.calls, ["load", "start"])


if __name__ == "__main__":
    unittest.main()

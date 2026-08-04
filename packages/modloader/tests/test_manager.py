from __future__ import annotations

import asyncio
import unittest
from typing import Any

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.manager import DefaultPluginManager


class FakeAgentRegistrar:
    def __init__(self) -> None:
        self.unregistered: list[str] = []

    def unregister(self, registered_name: str) -> None:
        self.unregistered.append(registered_name)


class FakeAgentRegistrarWithDrain(FakeAgentRegistrar):
    """带 unregister_and_drain 的新式注册表：卸载时应走排空路径而非 unregister+close。"""

    def __init__(self) -> None:
        super().__init__()
        self.drained: list[str] = []

    async def unregister_and_drain(self, registered_name: str) -> None:
        self.drained.append(registered_name)


class FakeContext:
    def __init__(self, plugin_name: str = "plugin") -> None:
        self.plugin_name = plugin_name
        self.agents = FakeAgentRegistrar()


class FakeContextWithDrain(FakeContext):
    def __init__(self, plugin_name: str = "plugin") -> None:
        super().__init__(plugin_name)
        self.agents = FakeAgentRegistrarWithDrain()


class FakeAgent:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class TrackingAgent(FakeAgent):
    """记录 close 调用次数，验证排空路径下 manager 不再重复关闭实例。"""

    def __init__(self) -> None:
        super().__init__()
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


class FakeSubscription:
    def __init__(self) -> None:
        self.unsubscribed = False

    def unsubscribe(self) -> None:
        self.unsubscribed = True


class CancelOnceSubscription(FakeSubscription):
    def __init__(self) -> None:
        super().__init__()
        self.unsubscribe_calls = 0

    def unsubscribe(self) -> None:
        self.unsubscribe_calls += 1
        if self.unsubscribe_calls == 1:
            raise asyncio.CancelledError
        super().unsubscribe()


class CancelOnceCleanup:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> None:
        self.calls += 1
        if self.calls == 1:
            raise asyncio.CancelledError


class CancelOnceAgent(TrackingAgent):
    async def close(self) -> None:
        self.close_calls += 1
        if self.close_calls == 1:
            raise asyncio.CancelledError
        self.closed = True


class CancelOnceAgentRegistrar(FakeAgentRegistrar):
    def __init__(self, cancel_name: str) -> None:
        super().__init__()
        self.cancel_name = cancel_name
        self.unregister_calls: dict[str, int] = {}

    def unregister(self, registered_name: str) -> None:
        calls = self.unregister_calls.get(registered_name, 0) + 1
        self.unregister_calls[registered_name] = calls
        if registered_name == self.cancel_name and calls == 1:
            raise asyncio.CancelledError
        super().unregister(registered_name)


def exception_leaves(error: Exception) -> list[Exception]:
    if isinstance(error, ExceptionGroup):
        leaves: list[Exception] = []
        for nested in error.exceptions:
            leaves.extend(exception_leaves(nested))
        return leaves
    return [error]


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

    async def test_stop_uses_unregister_and_drain_when_available(self) -> None:
        """注册表提供 unregister_and_drain 时，卸载必须走排空路径（由注册表负责关闭实例）。"""
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        context = FakeContextWithDrain()
        agent = TrackingAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin.echo", agent)

        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")

        self.assertEqual(context.agents.drained, ["plugin.echo"])
        self.assertEqual(context.agents.unregistered, [])
        # 排空路径内由注册表关闭实例，manager 不应重复调用 close
        self.assertEqual(agent.close_calls, 0)

    async def test_load_failure_uses_unregister_and_drain_when_available(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_load = True
        context = FakeContextWithDrain()
        agent = TrackingAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin.echo", agent)

        await manager.load_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        self.assertEqual(context.agents.drained, ["plugin.echo"])

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

    async def test_load_failure_runs_recorded_cleanups_once(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_load = True
        context = FakeContext()
        ran: list[str] = []
        manager.register(plugin, context)
        # 模拟 on_load 失败前已注册的 Tool / SKILL.md 等资源清理
        manager.record_cleanup("plugin", lambda: ran.append("skill"))
        manager.record_cleanup("plugin", lambda: ran.append("tool"))

        await manager.load_plugin("plugin")
        await manager.load_plugin("plugin")

        self.assertEqual(manager.get_state("plugin"), PluginState.ERROR)
        # LIFO 顺序执行一次，失败路径不留半成品、不重复清理
        self.assertEqual(ran, ["tool", "skill"])

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

        await asyncio.gather(
            manager.load_plugin("plugin"), manager.load_plugin("plugin")
        )

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

        await asyncio.gather(
            manager.start_plugin("plugin"), manager.start_plugin("plugin")
        )

        self.assertEqual(manager.get_state("plugin"), PluginState.RUNNING)
        self.assertEqual(plugin.calls, ["load", "start"])

    async def test_stale_operation_does_not_load_replacement_record(self) -> None:
        import asyncio

        manager = DefaultPluginManager()
        original = FakePlugin()
        manager.register(original, FakeContext())
        original_record = manager.get_record("plugin")
        lock = manager._plugin_locks["plugin"]

        async with lock:
            stale_load = asyncio.create_task(manager.load_plugin("plugin"))
            await asyncio.sleep(0)
            manager._records.pop("plugin")
            replacement = FakePlugin()
            manager.register(replacement, FakeContext())
            self.assertIs(manager._plugin_locks["plugin"], lock)

        await stale_load

        self.assertIsNot(manager.get_record("plugin"), original_record)
        self.assertEqual(replacement.calls, [])
        self.assertEqual(manager.get_state("plugin"), PluginState.UNLOADED)

    async def test_restart_retries_failed_cleanup_before_loading(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        attempts = 0

        def cleanup() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("busy")

        manager.register(plugin, FakeContext())
        manager.record_cleanup("plugin", cleanup)
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")

        await manager.stop_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertIsNotNone(record.error)
        self.assertEqual(len(record.cleanup_callbacks), 1)

        await manager.start_plugin("plugin")

        self.assertEqual(attempts, 2)
        self.assertEqual(plugin.calls, ["load", "start", "stop", "load", "start"])
        self.assertEqual(record.state, PluginState.RUNNING)
        self.assertIsNone(record.error)
        self.assertEqual(record.cleanup_callbacks, [])

    async def test_failed_on_stop_is_retried_on_later_remove(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_stop = True
        manager.register(plugin, FakeContext())
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertTrue(record.stop_failed)
        self.assertEqual(plugin.calls.count("stop"), 1)

        plugin.fail_stop = False
        removed = await manager.remove_plugin("plugin")
        self.assertIs(removed, record)
        self.assertIsNone(manager.get_record("plugin"))
        # 真正的 on_stop 被再次调用，而不是只清已记录资源
        self.assertEqual(plugin.calls.count("stop"), 2)
        self.assertFalse(record.stop_failed)
        self.assertIsNone(record.error)

    async def test_failed_on_stop_retry_keeps_flag_while_still_failing(self) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_stop = True
        manager.register(plugin, FakeContext())
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None

        await manager.stop_plugin("plugin")
        self.assertEqual(plugin.calls.count("stop"), 2)
        self.assertTrue(record.stop_failed)
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertIsNotNone(record.error)

        plugin.fail_stop = False
        await manager.stop_plugin("plugin")
        self.assertEqual(plugin.calls.count("stop"), 3)
        self.assertFalse(record.stop_failed)
        self.assertIsNone(record.error)

    async def test_second_cancellation_during_stop_cleanup_keeps_terminal_bookkeeping(
        self,
    ) -> None:
        manager = DefaultPluginManager()

        class BlockingStopPlugin(FakePlugin):
            def __init__(self) -> None:
                super().__init__()
                self.stop_entered = asyncio.Event()
                self.stop_release = asyncio.Event()

            async def on_stop(self) -> None:
                self.calls.append("stop")
                if self.calls.count("stop") == 1:
                    self.stop_entered.set()
                    await self.stop_release.wait()

        class ObservingCloseAgent(TrackingAgent):
            def __init__(self) -> None:
                super().__init__()
                self.entered = asyncio.Event()
                self.release = asyncio.Event()
                self.observed: tuple[PluginState, bool, bool] | None = None

            async def close(self) -> None:
                self.close_calls += 1
                record = manager.get_record("plugin")
                assert record is not None
                self.observed = (
                    record.state,
                    record.error is not None,
                    record.stop_failed,
                )
                self.entered.set()
                await self.release.wait()
                self.closed = True

        plugin = BlockingStopPlugin()
        context = FakeContext()
        agent = ObservingCloseAgent()
        manager.register(plugin, context)
        manager.record_agent_registration("plugin", "plugin.echo", agent)
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")

        stop_task = asyncio.create_task(manager.stop_plugin("plugin"))
        await plugin.stop_entered.wait()
        stop_task.cancel()
        await asyncio.wait_for(agent.entered.wait(), timeout=1)

        self.assertEqual(agent.observed, (PluginState.STOPPED, True, True))
        stop_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await stop_task

        record = manager.get_record("plugin")
        assert record is not None
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertTrue(record.stop_failed)
        self.assertIsNotNone(record.error)
        self.assertEqual(agent.close_calls, 1)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])

        agent.release.set()
        await manager.stop_plugin("plugin")

        self.assertEqual(plugin.calls.count("stop"), 2)
        self.assertEqual(agent.close_calls, 2)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])
        self.assertFalse(record.stop_failed)
        self.assertIsNone(record.error)
        self.assertEqual(record.agent_registrations, [])

    async def test_cleanup_cancelled_errors_are_retryable_and_stop_all_continues(
        self,
    ) -> None:
        manager = DefaultPluginManager()
        healthy = FakePlugin()
        flaky = FakePlugin()
        manager.register(healthy, FakeContext("healthy"))

        context = FakeContext("flaky")
        registrar = CancelOnceAgentRegistrar("flaky.unregister")
        context.agents = registrar
        manager.register(flaky, context)

        cleanup = CancelOnceCleanup()
        subscription = CancelOnceSubscription()
        unregister_agent = TrackingAgent()
        close_agent = CancelOnceAgent()
        good_agent = TrackingAgent()
        manager.record_cleanup("flaky", cleanup)
        manager.record_subscription("flaky", subscription)
        manager.record_agent_registration("flaky", "flaky.unregister", unregister_agent)
        manager.record_agent_registration("flaky", "flaky.close", close_agent)
        manager.record_agent_registration("flaky", "flaky.good", good_agent)

        await manager.load_all()
        await manager.start_all()
        await manager.stop_all()

        record = manager.get_record("flaky")
        assert record is not None
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertIsNotNone(record.error)
        self.assertFalse(record.stop_failed)
        self.assertEqual(healthy.calls.count("stop"), 1)
        self.assertEqual(flaky.calls.count("stop"), 1)
        self.assertEqual(cleanup.calls, 1)
        self.assertEqual(subscription.unsubscribe_calls, 1)
        self.assertEqual(unregister_agent.close_calls, 0)
        self.assertEqual(close_agent.close_calls, 1)
        self.assertEqual(good_agent.close_calls, 1)
        self.assertEqual(registrar.unregister_calls["flaky.unregister"], 1)
        self.assertEqual(registrar.unregister_calls["flaky.close"], 1)
        self.assertEqual(registrar.unregister_calls["flaky.good"], 1)

        await manager.stop_all()

        self.assertIsNone(record.error)
        self.assertEqual(record.cleanup_callbacks, [])
        self.assertEqual(record.subscriptions, [])
        self.assertEqual(record.agent_registrations, [])
        self.assertEqual(flaky.calls.count("stop"), 1)
        self.assertEqual(cleanup.calls, 2)
        self.assertEqual(subscription.unsubscribe_calls, 2)
        self.assertEqual(unregister_agent.close_calls, 1)
        self.assertEqual(close_agent.close_calls, 2)
        self.assertEqual(good_agent.close_calls, 1)
        self.assertEqual(registrar.unregister_calls["flaky.unregister"], 2)
        self.assertEqual(registrar.unregister_calls["flaky.close"], 1)
        self.assertEqual(registrar.unregister_calls["flaky.good"], 1)

    async def test_force_remove_pops_after_permanent_stop_and_resource_failures(
        self,
    ) -> None:
        manager = DefaultPluginManager()
        plugin = FakePlugin()
        plugin.fail_stop = True
        context = FakeContext()

        class FailingCleanup:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self) -> None:
                self.calls += 1
                raise RuntimeError("cleanup")

        class FailingSubscription:
            def __init__(self) -> None:
                self.calls = 0

            def unsubscribe(self) -> None:
                self.calls += 1
                raise RuntimeError("unsubscribe")

        class FailingAgent(TrackingAgent):
            async def close(self) -> None:
                self.close_calls += 1
                raise RuntimeError("close")

        cleanup = FailingCleanup()
        subscription = FailingSubscription()
        agent = FailingAgent()
        manager.register(plugin, context)
        manager.record_cleanup("plugin", cleanup)
        manager.record_subscription("plugin", subscription)
        manager.record_agent_registration("plugin", "plugin.echo", agent)
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None

        refused = await manager.remove_plugin("plugin")

        self.assertIs(refused, record)
        self.assertIs(manager.get_record("plugin"), record)
        self.assertEqual(plugin.calls.count("stop"), 1)
        self.assertEqual(cleanup.calls, 1)
        self.assertEqual(subscription.calls, 1)
        self.assertEqual(agent.close_calls, 1)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])

        removed = await manager.remove_plugin("plugin", force=True)

        self.assertIs(removed, record)
        self.assertIsNone(manager.get_record("plugin"))
        self.assertIsNotNone(removed.error)
        self.assertIn("stop", str(removed.error))
        self.assertIn("cleanup", str(removed.error))
        self.assertTrue(removed.stop_failed)
        self.assertEqual(plugin.calls.count("stop"), 2)
        self.assertEqual(cleanup.calls, 2)
        self.assertEqual(subscription.calls, 2)
        self.assertEqual(agent.close_calls, 2)
        self.assertEqual(context.agents.unregistered, ["plugin.echo"])

    async def test_stopping_error_record_preserves_root_error(self) -> None:
        manager = DefaultPluginManager()
        root_error = RuntimeError("load root")

        class LoadErrorPlugin(FakePlugin):
            async def on_load(self, ctx: Any) -> None:
                self.calls.append("load")
                raise root_error

        manager.register(LoadErrorPlugin(), FakeContext())
        await manager.load_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None
        self.assertIs(record.error, root_error)

        await manager.stop_plugin("plugin")

        self.assertEqual(record.state, PluginState.ERROR)
        self.assertIs(record.error, root_error)
        refused = await manager.remove_plugin("plugin")
        self.assertIs(refused, record)
        self.assertIs(manager.get_record("plugin"), record)

        removed = await manager.remove_plugin("plugin", force=True)
        self.assertIs(removed, record)
        self.assertIs(removed.error, root_error)
        self.assertIsNone(manager.get_record("plugin"))

    async def test_error_cleanup_failure_aggregates_without_losing_root(self) -> None:
        manager = DefaultPluginManager()
        root_error = RuntimeError("load root")
        cleanup_error = RuntimeError("cleanup root")
        cleanup_calls = 0

        class LoadErrorPlugin(FakePlugin):
            async def on_load(self, ctx: Any) -> None:
                raise root_error

        def cleanup() -> None:
            nonlocal cleanup_calls
            cleanup_calls += 1
            raise cleanup_error

        manager.register(LoadErrorPlugin(), FakeContext())
        manager.record_cleanup("plugin", cleanup)
        await manager.load_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None
        original_error = record.error
        assert original_error is not None

        await manager.stop_plugin("plugin")

        assert record.error is not None
        leaves = exception_leaves(record.error)
        self.assertEqual(record.state, PluginState.ERROR)
        self.assertIn(root_error, leaves)
        self.assertIn(cleanup_error, leaves)
        self.assertIn("load root", str(record.error))
        self.assertIn("cleanup root", str(record.error))
        self.assertIn(original_error, record.error.exceptions)
        self.assertEqual(cleanup_calls, 2)

    async def test_reentrant_self_remove_in_failing_on_stop_reports_record_error(
        self,
    ) -> None:
        manager = DefaultPluginManager()
        stop_error = RuntimeError("stop root")

        class SelfRemovingPlugin(FakePlugin):
            def __init__(self) -> None:
                super().__init__()
                self.inner_record: Any = None

            async def on_stop(self) -> None:
                self.calls.append("stop")
                self.inner_record = await manager.remove_plugin("plugin")
                raise stop_error

        plugin = SelfRemovingPlugin()
        manager.register(plugin, FakeContext())
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None

        removed = await manager.remove_plugin("plugin")

        self.assertIs(removed, record)
        self.assertIs(plugin.inner_record, record)
        self.assertIs(manager.get_record("plugin"), record)
        self.assertEqual(record.state, PluginState.STOPPED)
        self.assertTrue(record.stop_failed)
        assert record.error is not None
        self.assertIs(plugin.inner_record.error, record.error)
        self.assertIn(stop_error, exception_leaves(record.error))

    async def test_force_remove_preserves_reentrant_on_stop_error_on_removed_record(
        self,
    ) -> None:
        manager = DefaultPluginManager()
        stop_error = RuntimeError("stop root")

        class SelfRemovingPlugin(FakePlugin):
            def __init__(self) -> None:
                super().__init__()
                self.inner_record: Any = None

            async def on_stop(self) -> None:
                self.calls.append("stop")
                self.inner_record = await manager.remove_plugin("plugin")
                raise stop_error

        plugin = SelfRemovingPlugin()
        manager.register(plugin, FakeContext())
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        record = manager.get_record("plugin")
        assert record is not None

        removed = await manager.remove_plugin("plugin", force=True)

        self.assertIs(removed, record)
        self.assertIs(plugin.inner_record, record)
        self.assertIsNone(manager.get_record("plugin"))
        self.assertTrue(removed.stop_failed)
        assert removed.error is not None
        self.assertIn(stop_error, exception_leaves(removed.error))

    async def test_reentrant_self_stop_does_not_get_overwritten_by_load_or_start(
        self,
    ) -> None:
        load_manager = DefaultPluginManager()

        class StopOnLoadPlugin(FakePlugin):
            async def on_load(self, ctx: Any) -> None:
                self.calls.append("load")
                await load_manager.stop_plugin("plugin")

        load_plugin = StopOnLoadPlugin()
        load_manager.register(load_plugin, FakeContext())
        await load_manager.load_plugin("plugin")
        self.assertEqual(load_manager.get_state("plugin"), PluginState.STOPPED)
        self.assertEqual(load_plugin.calls, ["load"])

        start_manager = DefaultPluginManager()

        class StopOnStartPlugin(FakePlugin):
            async def on_start(self) -> None:
                self.calls.append("start")
                await start_manager.stop_plugin("plugin")

        start_plugin = StopOnStartPlugin()
        start_manager.register(start_plugin, FakeContext())
        await start_manager.load_plugin("plugin")
        await start_manager.start_plugin("plugin")
        self.assertEqual(start_manager.get_state("plugin"), PluginState.STOPPED)
        self.assertEqual(start_plugin.calls, ["load", "start"])

    async def test_reentrant_self_remove_does_not_restore_load_or_start_state(
        self,
    ) -> None:
        load_manager = DefaultPluginManager()

        class RemoveOnLoadPlugin(FakePlugin):
            def __init__(self) -> None:
                super().__init__()
                self.removed: Any = None

            async def on_load(self, ctx: Any) -> None:
                self.calls.append("load")
                self.removed = await load_manager.remove_plugin("plugin")

        load_plugin = RemoveOnLoadPlugin()
        load_manager.register(load_plugin, FakeContext())
        await load_manager.load_plugin("plugin")
        self.assertIsNone(load_manager.get_record("plugin"))
        self.assertEqual(load_manager.get_state("plugin"), PluginState.UNLOADED)
        self.assertEqual(load_plugin.removed.state, PluginState.STOPPED)

        start_manager = DefaultPluginManager()

        class RemoveOnStartPlugin(FakePlugin):
            def __init__(self) -> None:
                super().__init__()
                self.removed: Any = None

            async def on_start(self) -> None:
                self.calls.append("start")
                self.removed = await start_manager.remove_plugin("plugin")

        start_plugin = RemoveOnStartPlugin()
        start_manager.register(start_plugin, FakeContext())
        await start_manager.load_plugin("plugin")
        await start_manager.start_plugin("plugin")
        self.assertIsNone(start_manager.get_record("plugin"))
        self.assertEqual(start_manager.get_state("plugin"), PluginState.UNLOADED)
        self.assertEqual(start_plugin.removed.state, PluginState.STOPPED)

    async def test_resource_registrations_are_rejected_during_and_after_stop(
        self,
    ) -> None:
        manager = DefaultPluginManager()
        rejected: list[str] = []
        late_agent = TrackingAgent()

        def attempt(label: str, register: Any) -> None:
            try:
                register()
            except RuntimeError:
                rejected.append(label)

        class RegisteringStopPlugin(FakePlugin):
            async def on_stop(self) -> None:
                self.calls.append("stop")
                attempt(
                    "subscription",
                    lambda: manager.record_subscription("plugin", FakeSubscription()),
                )
                attempt(
                    "agent",
                    lambda: manager.record_agent_registration(
                        "plugin", "plugin.late", late_agent
                    ),
                )
                attempt(
                    "cleanup", lambda: manager.record_cleanup("plugin", lambda: None)
                )

        def cleanup() -> None:
            attempt("teardown", lambda: manager.record_cleanup("plugin", lambda: None))

        plugin = RegisteringStopPlugin()
        manager.register(plugin, FakeContext())
        manager.record_cleanup("plugin", cleanup)
        await manager.load_plugin("plugin")
        await manager.start_plugin("plugin")
        await manager.stop_plugin("plugin")

        record = manager.get_record("plugin")
        assert record is not None
        self.assertCountEqual(
            rejected, ["subscription", "agent", "cleanup", "teardown"]
        )
        self.assertEqual(record.subscriptions, [])
        self.assertEqual(record.agent_registrations, [])
        self.assertEqual(record.cleanup_callbacks, [])
        self.assertEqual(late_agent.close_calls, 0)

        with self.assertRaises(RuntimeError):
            manager.record_subscription("plugin", FakeSubscription())
        with self.assertRaises(RuntimeError):
            manager.record_agent_registration("plugin", "plugin.late", late_agent)
        with self.assertRaises(RuntimeError):
            manager.record_cleanup("plugin", lambda: None)

    async def test_force_remove_expected_record_does_not_pop_replacement(self) -> None:
        manager = DefaultPluginManager()
        original = FakePlugin()
        manager.register(original, FakeContext())
        original_record = manager.get_record("plugin")
        assert original_record is not None
        lock = manager._plugin_locks["plugin"]

        async with lock:
            stale_remove = asyncio.create_task(
                manager.remove_plugin("plugin", expected=original_record, force=True)
            )
            await asyncio.sleep(0)
            manager._records.pop("plugin")
            replacement = FakePlugin()
            manager.register(replacement, FakeContext())

        removed = await stale_remove

        self.assertIsNone(removed)
        self.assertIs(manager.get_plugin("plugin"), replacement)
        self.assertEqual(original.calls, [])
        self.assertEqual(replacement.calls, [])


if __name__ == "__main__":
    unittest.main()

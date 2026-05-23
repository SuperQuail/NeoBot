from __future__ import annotations

import unittest
from typing import Any

from neobot_contracts.ports.output import CapturingOutput
from neobot_modloader.host import (
    DefaultCapabilityRegistry,
    DefaultCommandRegistry,
    DefaultLifecycleHooks,
    DefaultQueryRegistry,
    PluginHostFacade,
    TrackedPluginHostFacade,
)


class FakeHookBus:
    def __init__(self) -> None:
        self.seen: list[Any] = []

    def subscribe_runtime(self, handler: Any, **kwargs: Any) -> Any:
        self.seen.append(("subscribe_runtime", handler, kwargs))
        return type("_Sub", (), {"unsubscribe": lambda: None})()

    async def dispatch_envelope(self, envelope: Any) -> Any:
        self.seen.append(("dispatch_envelope", envelope))
        return envelope


class PluginHostTest(unittest.TestCase):
    def test_command_registry_register_and_call(self) -> None:
        import asyncio

        async def run() -> None:
            registry = DefaultCommandRegistry()
            registry.register("tts.speak", "发送 TTS", lambda text: f"spoken: {text}")

            self.assertIn("tts.speak", registry.names())
            self.assertEqual(await registry.call("tts.speak", text="hello"), "spoken: hello")
            with self.assertRaises(KeyError):
                await registry.call("missing")

        asyncio.run(run())

    def test_command_registry_rejects_duplicates_unless_override(self) -> None:
        import asyncio

        async def run() -> None:
            registry = DefaultCommandRegistry()
            registry.register("demo", "first", lambda: 1)
            with self.assertRaises(ValueError):
                registry.register("demo", "second", lambda: 2)
            registry.register("demo", "second", lambda: 2, override=True)
            self.assertEqual(await registry.call("demo"), 2)

        asyncio.run(run())

    def test_call_passes_all_arguments_to_kwargs_handlers(self) -> None:
        import asyncio

        async def run() -> None:
            registry = DefaultCommandRegistry()
            registry.register("kwargs", "kwargs", lambda **kwargs: kwargs)

            self.assertEqual(await registry.call("kwargs", a=1, b=2), {"a": 1, "b": 2})

        asyncio.run(run())

    def test_query_registry_register_and_query(self) -> None:
        async def run() -> None:
            registry = DefaultQueryRegistry()
            registry.register("memory.get", "读取记忆", lambda key: f"mem:{key}")

            self.assertEqual(await registry.query("memory.get", key="abc"), "mem:abc")
            with self.assertRaises(KeyError):
                await registry.query("missing")

        import asyncio

        asyncio.run(run())

    def test_query_and_capability_registries_reject_duplicates(self) -> None:
        queries = DefaultQueryRegistry()
        queries.register("demo", "first", lambda: 1)
        with self.assertRaises(ValueError):
            queries.register("demo", "second", lambda: 2)

        capabilities = DefaultCapabilityRegistry()
        capabilities.register("demo", "first", lambda: 1)
        with self.assertRaises(ValueError):
            capabilities.register("demo", "second", lambda: 2)

    def test_capability_registry_register_call_and_list(self) -> None:
        async def run() -> None:
            registry = DefaultCapabilityRegistry()
            registry.register("image.analyze", "分析图片", lambda path: f"analyzed:{path}")
            registry.register("echo", "回声", lambda text: text)

            specs = registry.list()
            self.assertEqual(len(specs), 2)
            self.assertEqual(specs[0]["name"], "image.analyze")
            self.assertEqual(await registry.call("echo", text="hi"), "hi")
            registry.unregister("echo")
            self.assertEqual(len(registry.list()), 1)

        import asyncio

        asyncio.run(run())

    def test_lifecycle_hooks_fire_in_priority_order(self) -> None:
        async def run() -> None:
            hooks = DefaultLifecycleHooks()
            seen: list[str] = []

            hooks.subscribe("startup", lambda stage: seen.append("high"), priority=10)
            hooks.subscribe("startup", lambda stage: seen.append("low"), priority=0)
            await hooks.fire("startup")

            self.assertEqual(seen, ["high", "low"])

        import asyncio

        asyncio.run(run())

    def test_lifecycle_unsubscribe(self) -> None:
        async def run() -> None:
            hooks = DefaultLifecycleHooks()
            seen: list[str] = []

            unsubscribe = hooks.subscribe("startup", lambda stage: seen.append(stage))
            unsubscribe()
            await hooks.fire("startup")

            self.assertEqual(seen, [])

        import asyncio

        asyncio.run(run())

    def test_tracked_host_records_cleanup_for_plugin_resources(self) -> None:
        async def run() -> None:
            host = PluginHostFacade()
            cleanups: list[Any] = []
            tracked = TrackedPluginHostFacade(host, cleanups.append)
            seen: list[str] = []

            tracked.commands.register("plugin.cmd", "cmd", lambda: "ok")
            tracked.queries.register("plugin.query", "query", lambda: "q")
            tracked.capabilities.register("plugin.cap", "cap", lambda: "c")
            tracked.lifecycle.subscribe("config.changed", lambda stage: seen.append(stage))

            self.assertEqual(await host.commands.call("plugin.cmd"), "ok")
            self.assertEqual(await host.queries.query("plugin.query"), "q")
            self.assertEqual(await host.capabilities.call("plugin.cap"), "c")
            await host.lifecycle.fire("config.changed")
            self.assertEqual(seen, ["config.changed"])

            for cleanup in reversed(cleanups):
                cleanup()

            self.assertNotIn("plugin.cmd", host.commands.names())
            self.assertNotIn("plugin.query", host.queries.names())
            self.assertNotIn("plugin.cap", host.capabilities.names())
            await host.lifecycle.fire("config.changed")
            self.assertEqual(seen, ["config.changed"])

        import asyncio

        asyncio.run(run())

    def test_tracked_cleanup_does_not_remove_later_override(self) -> None:
        async def run() -> None:
            host = PluginHostFacade()
            first_cleanups: list[Any] = []
            second_cleanups: list[Any] = []
            first = TrackedPluginHostFacade(host, first_cleanups.append)
            second = TrackedPluginHostFacade(host, second_cleanups.append)

            first.commands.register("shared.cmd", "first", lambda: "first")
            second.commands.register("shared.cmd", "second", lambda: "second", override=True)

            self.assertEqual(await host.commands.call("shared.cmd"), "second")
            for cleanup in reversed(first_cleanups):
                cleanup()
            self.assertIn("shared.cmd", host.commands.names())
            self.assertEqual(await host.commands.call("shared.cmd"), "second")

            for cleanup in reversed(second_cleanups):
                cleanup()
            self.assertNotIn("shared.cmd", host.commands.names())

        import asyncio

        asyncio.run(run())

    def test_host_facade_exposes_all_buses(self) -> None:
        output = CapturingOutput()
        hook_bus = FakeHookBus()
        commands = DefaultCommandRegistry()
        queries = DefaultQueryRegistry()
        capabilities = DefaultCapabilityRegistry()
        lifecycle = DefaultLifecycleHooks()

        host = PluginHostFacade(
            events=hook_bus,
            output=output,
            commands=commands,
            queries=queries,
            capabilities=capabilities,
            lifecycle=lifecycle,
        )

        self.assertIs(host.commands, commands)
        self.assertIs(host.queries, queries)
        self.assertIs(host.capabilities, capabilities)
        self.assertIs(host.lifecycle, lifecycle)
        self.assertIs(host.output, output)

    def test_command_registry_unregister(self) -> None:
        registry = DefaultCommandRegistry()
        registry.register("test", "测试", lambda: None)
        self.assertIn("test", registry.names())
        self.assertTrue(registry.unregister("test"))
        self.assertNotIn("test", registry.names())
        self.assertFalse(registry.unregister("nonexistent"))

    def test_config_reload_command_and_lifecycle_fire(self) -> None:
        import asyncio

        async def run() -> None:
            commands = DefaultCommandRegistry()
            lifecycle = DefaultLifecycleHooks()
            seen: list[str] = []

            lifecycle.subscribe("config.changed", lambda stage, config: seen.append("changed"), priority=10)

            async def reload(**kwargs: Any) -> dict[str, Any]:
                await lifecycle.fire("config.changed", config={"version": 2})
                return {"ok": True}

            commands.register("config.reload", "重载配置", reload)
            result = await commands.call("config.reload")

            self.assertTrue(result["ok"])
            self.assertEqual(seen, ["changed"])

        asyncio.run(run())

    def test_loguru_runtime_sink_dispatches_envelope(self) -> None:
        import asyncio

        async def run() -> None:
            from neobot_app.observability.logging import _loguru_runtime_sink, set_runtime_event_dispatcher

            captured: list[Any] = []

            class _FakeDispatcher:
                async def dispatch_envelope(self, envelope: Any) -> None:
                    captured.append(envelope)

            set_runtime_event_dispatcher(_FakeDispatcher().dispatch_envelope)

            class _FakeRecord:
                def __init__(self, **entries: Any) -> None:
                    self._data = entries
                    for k, v in entries.items():
                        setattr(self, k, v)

                def __getitem__(self, key: str) -> Any:
                    return self._data[key]

            class _FakeMessage:
                record = _FakeRecord(
                    level=_FakeRecord(name="INFO"),
                    message="test log",
                    time="2026-01-01T00:00:00",
                    extra={"module_name": "test.module"},
                    file=_FakeRecord(name="test.py"),
                    line=42,
                    function="test_fn",
                )

            _loguru_runtime_sink(_FakeMessage())
            await asyncio.sleep(0.1)

            self.assertEqual(len(captured), 1)
            self.assertEqual(captured[0].kind, "log")
            self.assertEqual(captured[0].stage, "info")
            self.assertEqual(captured[0].payload["level"], "INFO")
            self.assertEqual(captured[0].payload["message"], "test log")

            set_runtime_event_dispatcher(None)

        asyncio.run(run())

    def test_config_proxy_reload_transparent_to_holders(self) -> None:
        from neobot_app.config.proxy import ConfigProxy

        class _FakeChat:
            reply_mode = "common"
            max_tokens = 100

        class _FakeConfig:
            chat = _FakeChat()

        proxy = ConfigProxy(_FakeConfig())

        class _Holder:
            config = proxy

        holder = _Holder()
        self.assertEqual(holder.config.chat.reply_mode, "common")
        self.assertEqual(holder.config.chat.max_tokens, 100)

        class _FakeChat2:
            reply_mode = "agent"
            max_tokens = 200

        class _FakeConfig2:
            chat = _FakeChat2()

        proxy.reload(_FakeConfig2())
        self.assertEqual(holder.config.chat.reply_mode, "agent")
        self.assertEqual(holder.config.chat.max_tokens, 200)


if __name__ == "__main__":
    unittest.main()

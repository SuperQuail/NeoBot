"""通过真实插件加载代验证订阅持久化、停用和重载清理。"""

import asyncio
import shutil
import sys
from pathlib import Path

import pytest

from neobot_app.builtin_plugins import streaming_parser
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader.loader import LoadedPlugin
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.sdk import ActionError, ActionInvocation

from streaming_panel_helpers import Adapter, LiveClient


class LoggerFactory:
    def get_logger(self, name):
        return NullLogger()


async def test_real_runtime_keeps_subscriptions_and_replaces_only_one_poller(tmp_path, monkeypatch):
    original_tasks = set(asyncio.all_tasks())
    source = Path(streaming_parser.__file__).parent
    plugin_dir = tmp_path / "plugins" / "streaming_parser"
    shutil.copytree(source, plugin_dir, ignore=shutil.ignore_patterns("__pycache__", "tests", "docs"))
    runtime = PluginRuntime(
        plugin_dir=plugin_dir.parent, data_dir=tmp_path / "data", adapter=Adapter(), logger_factory=LoggerFactory()
    )
    clients = []
    modules = []
    load_package = runtime.loader._load_package

    def injected(path):
        loaded = load_package(path)
        if isinstance(loaded, LoadedPlugin):
            module = next(
                sys.modules[name]
                for name in loaded.module_names
                if getattr(sys.modules[name], "plugin", None) is loaded.plugin
            )

            def factory(*args, **kwargs):
                client = LiveClient()
                clients.append(client)
                return client

            monkeypatch.setattr(module, "BilibiliLiveClient", factory)
            modules.append(module)
        return loaded

    monkeypatch.setattr(runtime.loader, "_load_package", injected)
    caller = ActionInvocation("runtime-test", frozenset({"manage"}))
    runtime.load_all()
    try:
        await runtime.load_registered()
        await runtime.start_all()
        assert len(clients) == 1
        await runtime.control.invoke_action(
            "streaming_parser", "subscriptions.create", {"group_id": 20001, "target": "1001"}, caller
        )
        first_task = modules[0].state._task

        async def observed():
            while not (
                await runtime.control.invoke_action(
                    "streaming_parser",
                    "subscriptions.ready",
                    {},
                    caller,
                )
            )["completed"]:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(observed(), 2)
        result = await runtime.reload_plugin_result("streaming_parser")
        assert result.ok, result.error
        assert first_task.done()
        assert clients[0].closed == 1
        assert modules[-1].state._task is not first_task
        assert not modules[-1].state._task.done()
        rows = await runtime.control.invoke_action("streaming_parser", "subscriptions.list", {}, caller)
        assert len(rows["items"]) == 1
        assert rows["items"][0]["room_id"] == 610001
        disabled = await runtime.set_enabled("streaming_parser", False)
        assert disabled.ok, disabled.error
        assert modules[-1].state._task is None
        assert clients[-1].closed == 1
        with pytest.raises(ActionError) as error:
            await runtime.control.invoke_action("streaming_parser", "subscriptions.list", {}, caller)
        assert error.value.code == "plugin_not_ready"
        assert not [task for task in asyncio.all_tasks() - original_tasks if not task.done()]
    finally:
        for name in reversed(list(runtime.manager.names())):
            await runtime.unload_plugin(name, force=True)

"""从公开 Python 示例加载插件并验证真实消息派发，不依赖文档发布状态。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.loader import FilesystemPluginLoader


class _Adapter:
    def __init__(self) -> None:
        self.messages: list[Any] = []

    async def send(self, conversation: Any, message: Any) -> str:
        self.messages.append(message)
        return "example-message"


class _Event:
    def __init__(self, text: str) -> None:
        self.raw_event = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "raw_message": text,
        }
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("/ping", "pong!"),
        ("/ping example argument", "pong! args: example argument"),
        ("ping", [{"type": "text", "data": {"text": "ping"}}]),
    ],
)
async def test_public_ping_example_loads_and_sends_reply(tmp_path: Path, message: str, expected: Any) -> None:
    """示例的装饰器、参数注入和 Reply 必须共同产生实际回复。"""
    example = Path(__file__).resolve().parents[1] / "example_plugins" / "ping.py"
    loader = FilesystemPluginLoader()
    result = loader.load_one(example)
    assert result is not None and result.plugin is not None, result
    plugin = result.plugin
    adapter = _Adapter()
    hooks = PluginHookBus()
    context = RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=example.parent,
        data_dir=tmp_path,
        config={},
        logger=None,
        adapter=adapter,
        hook_bus=hooks,
    )

    try:
        await plugin.on_load(context)
        await plugin.on_start()
        await hooks.dispatch(_Event(message))
        assert adapter.messages == [expected]
    finally:
        await plugin.on_stop()
        loader.clear_module_cache(result.module_names)

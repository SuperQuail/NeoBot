"""消息链按注解注入，保持命令捕获和原始 Message 的现有边界。"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.message import Message, MessageChain
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.injection import parameter_injection_kind
from neobot_modloader.plugins.tools import build_tool_schema


class DispatchContext:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event

    def consume(self) -> None:
        pass

    def block_ai_reply(self) -> None:
        pass


def test_message_chain_annotation_uses_own_provider() -> None:
    assert parameter_injection_kind("content", MessageChain) == "message_chain"
    assert parameter_injection_kind("content", MessageChain | None) == "message_chain"
    assert parameter_injection_kind("content", Annotated[MessageChain, "消息"]) == "message_chain"
    assert parameter_injection_kind("message", Message) == "message"
    assert parameter_injection_kind("chain", str) is None


def test_message_chain_dependency_stays_out_of_tool_schema() -> None:
    async def handler(content: MessageChain, query: str) -> None:
        pass

    schema = build_tool_schema(handler)

    assert set(schema["properties"]) == {"query"}


@pytest.mark.parametrize("registration", ["message", "command"])
async def test_message_chain_is_injected_into_public_handlers(registration: str, tmp_path: Path) -> None:
    plugin = Plugin("chain_injection")
    hook_bus = PluginHookBus()
    seen: list[tuple[MessageChain, Message]] = []

    async def handler(content: MessageChain, message: Message) -> None:
        seen.append((content, message))

    if registration == "command":
        plugin.command("inspect")(handler)
    else:
        plugin.message()(handler)
    context = RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=tmp_path,
        data_dir=tmp_path / "data",
        config={},
        logger=None,
        adapter=object(),
        hook_bus=hook_bus,
    )
    raw_segments = [
        {"type": "text", "data": {"text": "/inspect"}},
        {"type": "image", "data": {"file": "first.image"}},
        {"type": "vendor.card", "data": {"nested": {"items": [1]}}},
    ]
    await plugin.on_load(context)
    try:
        await hook_bus.dispatch(
            DispatchContext(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 42,
                    "message": raw_segments,
                }
            )
        )
    finally:
        await plugin.on_stop()

    assert len(seen) == 1
    chain, message = seen[0]
    assert isinstance(chain, MessageChain)
    assert chain.to_list() == message.to_list() == raw_segments
    assert chain.has("image")
    chain.first("vendor.card").data["nested"]["items"].append(2)
    assert message.to_list() == raw_segments

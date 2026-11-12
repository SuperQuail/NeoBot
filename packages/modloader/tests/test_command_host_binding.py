"""宿主声明式命令：官方群 conv_id 是 openid 字符串，不能 int() 化（回归）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_contracts.ports.logging import NullLogger
from neobot_modloader import Plugin
from neobot_modloader.plugins.commands import bind_command

OPENID_GROUP = "group-openid-abcdef"
BOT = 123456789


class _AppCommands:
    available = True

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}

    def register(self, name: str, **kwargs: Any):
        def decorate(handler: Any) -> Any:
            self.handlers[name] = handler
            return handler

        return decorate


def _bind() -> tuple[_AppCommands, list[dict[str, Any]]]:
    plugin = Plugin("demo")
    seen_events: list[dict[str, Any]] = []

    @plugin.command("echo <text:str>", permission=1)
    async def echo(event: dict, text: str) -> str:
        seen_events.append(event)
        return f"OK:{text}"

    registry = _AppCommands()
    context = SimpleNamespace(
        app_commands=registry,
        logger=NullLogger(),
        adapter=SimpleNamespace(self_id=BOT),
    )
    bind_command(plugin, plugin._registrations[0], context)
    return registry, seen_events


def _official_group_message(*, text: str = "/echo hi") -> GroupMessage:
    return GroupMessage(
        message_id=1,
        user_id="member-openid-1",
        group_id=OPENID_GROUP,
        self_id=BOT,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        neobot_channel="official",
    )


def _onebot_group_message(*, group_id: int = 20001, text: str = "/echo hi") -> GroupMessage:
    return GroupMessage(
        message_id=2,
        user_id=42,
        group_id=group_id,
        self_id=10001,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        neobot_channel="onebot",
    )


def _command_context(*, conv_id: str, message: Any = None, raw_args: str = "hi") -> Any:
    async def reply(text: str) -> None:
        return None

    return SimpleNamespace(
        message=message,
        kind="group",
        conv_id=conv_id,
        user_id="member-openid-1",
        raw_args=raw_args,
        command=SimpleNamespace(name="echo"),
        reply=reply,
    )


async def test_official_group_openid_command_runs_and_keeps_string_group_id() -> None:
    """官方群 conv_id=openid：命令照常执行，事件里的 group_id 保持字符串 openid。"""
    registry, seen_events = _bind()
    context = _command_context(conv_id=OPENID_GROUP, message=_official_group_message())

    result = await registry.handlers["echo"](context)

    assert result == "OK:hi"
    assert seen_events[0]["group_id"] == OPENID_GROUP
    assert isinstance(seen_events[0]["group_id"], str)


async def test_official_group_openid_fallback_group_id_keeps_string() -> None:
    """命令上下文没有原始消息时：setdefault 兜底也不得 int() 化 openid。"""
    registry, seen_events = _bind()
    context = _command_context(conv_id=OPENID_GROUP)

    result = await registry.handlers["echo"](context)

    assert result == "OK:hi"
    assert seen_events[0]["group_id"] == OPENID_GROUP
    assert isinstance(seen_events[0]["group_id"], str)


async def test_onebot_group_message_keeps_numeric_group_id() -> None:
    """OneBot 群消息自带 int group_id：不被兜底值覆盖，行为不变。"""
    registry, seen_events = _bind()
    context = _command_context(conv_id="20001", message=_onebot_group_message())

    result = await registry.handlers["echo"](context)

    assert result == "OK:hi"
    assert seen_events[0]["group_id"] == 20001


async def test_onebot_group_fallback_group_id_stays_string() -> None:
    """OneBot 兜底同样保留 CommandContext.conv_id 的字符串形态。"""
    registry, seen_events = _bind()
    context = _command_context(conv_id="20001")

    result = await registry.handlers["echo"](context)

    assert result == "OK:hi"
    assert seen_events[0]["group_id"] == "20001"
    assert isinstance(seen_events[0]["group_id"], str)

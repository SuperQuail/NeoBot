"""插件消息意图的「交主管线 + 本轮预激活技能包」通路（spec(5) R13/R14）。

链路：插件消息处理器 ctx.agent_reply(...) -> EventContext 一次性意图 -> Gateway
随事件传递 -> EventPipeline 复用「命令 background 触发一次回复」的既有通路 ->
ReplyOrchestrator 把 preactivate 挂到 ReplyEvent -> 构建本轮工具表**之前**激活
指定技能包，使 minigame__<tool> 在本轮模型调用里即可直接调用。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.builtin_plugins import minigame as minigame_plugin
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.tools import ReplyToolExecutor, build_reply_toolset
from neobot_app.runtime.event_context import EventContext
from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.skills.base import SkillManager
from neobot_app.willing.models import WillingDecision
from neobot_adapter.model.message import (
    GroupMessage,
    MessageSegment,
    PostMessageMessagesender,
)
from neobot_adapter.model.message import MessageTypeEnum
from neobot_modloader import PluginHostFacade, RuntimePluginContext
from neobot_modloader.plugins.tools import bind_tools
from neobot_app.message.queue import MessageQueue

# ── 通用替身 ──────────────────────────────────────────────────────


class _RecordingLogger:
    def __init__(self) -> None:
        self.events: list[str] = []

    def debug(self, message: str, **kw: Any) -> None:
        self.events.append(f"debug:{message}")

    def info(self, message: str, **kw: Any) -> None:
        self.events.append(f"info:{message}")

    def warning(self, message: str, **kw: Any) -> None:
        self.events.append(f"warning:{message}")

    def error(self, message: str, **kw: Any) -> None:
        self.events.append(f"error:{message}")

    def exception(self, message: str, **kw: Any) -> None:
        self.events.append(f"exception:{message}")


class _StubOrchestrator:
    def __init__(self, *, started: Any = None) -> None:
        self.started = started if started is not None else SimpleNamespace()
        self.calls: list[dict[str, Any]] = []

    def start_reply(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.started


class _StubQueue:
    def get_last_message_id(self, queue_key: str) -> int:
        return 42


class _FakeChat:
    reply_mode = "agent"

    def __getattr__(self, name: str) -> Any:
        return None


class _FakeConfig:
    chat = _FakeChat()
    bot = SimpleNamespace(nick_name="Bot")


class _FakePromptBuilder:
    async def build_friend_chat_prompt(self, **kwargs: Any) -> str:
        return "私聊提示词"

    async def build_group_chat_prompt(self, **kwargs: Any) -> str:
        return "群聊提示词"

    async def build_group_chat_messages(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"role": "user", "content": "群聊历史"}]

    async def build_friend_chat_messages(self, **kwargs: Any) -> list[dict[str, Any]]:
        return [{"role": "user", "content": "私聊历史"}]


class _ScriptedProvider:
    max_tokens = 10000

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list, object]] = []

    async def chat(self, messages: list, tools: Any = None) -> dict[str, Any]:
        self.calls.append((list(messages), tools))
        return self._responses.pop(0)

    async def close(self) -> None:
        pass


class _FakeAdapter:
    async def send(self, conversation_ref: Any, payload: Any, wait_response: bool = True) -> Any:
        return {"status": "ok", "message_id": 2001}

    async def call_api(self, action: str, params: Any) -> Any:
        return {"status": "ok"}


class _PassThroughHookBus:
    async def dispatch(self, ctx: Any) -> None: ...


async def _build_minigame_skill_manager(tmp_path: Path) -> SkillManager:
    """把 minigame 插件的工具（按玩法的技能包）注册进真实 SkillManager。"""
    manager = SkillManager(eager_tool_skills=set())
    facade = PluginHostFacade(skills=manager)
    ctx = RuntimePluginContext(
        plugin_name="minigame",
        plugin_dir=Path(tmp_path),
        data_dir=Path(tmp_path) / "data",
        config={},
        logger=_RecordingLogger(),
        adapter=object(),
        host=facade,
        record_skill_cleanup=lambda _cleanup: None,
    )
    await bind_tools(minigame_plugin.plugin, minigame_plugin.plugin._tool_registrations, ctx)
    return manager


# ── EventContext 意图 ────────────────────────────────────────────


def test_event_context_intent_is_one_shot() -> None:
    ctx = EventContext(raw_event={"post_type": "message"})

    assert ctx.has_agent_reply_intent() is False
    ctx.agent_reply("事实 + 提示词", preactivate=["a", " ", "a", "b"])

    assert ctx.has_agent_reply_intent() is True
    assert ctx.agent_reply_requested is True
    assert ctx.take_agent_reply_intent() == {
        "background": "事实 + 提示词",
        "preactivate": ("a", "b"),
    }
    assert ctx.take_agent_reply_intent() is None


def test_event_context_empty_request_is_ignored() -> None:
    ctx = EventContext(raw_event={})
    ctx.agent_reply("", preactivate=())
    assert ctx.has_agent_reply_intent() is False


async def test_gateway_takes_intent_and_passes_it_down() -> None:
    from neobot_app.runtime.gateway import EventGateway

    captured: list[dict[str, Any]] = []

    class _Legacy:
        async def handle_group_message_event(self, event, *, skip_ai_reply=False, agent_intent=None):
            captured.append({"skip": skip_ai_reply, "intent": agent_intent})

        async def handle_private_message_event(self, event, *, skip_ai_reply=False, agent_intent=None):
            captured.append({"skip": skip_ai_reply, "intent": agent_intent})

    class _Bus:
        def __init__(self) -> None:
            self.ctx: Any = None

        async def dispatch(self, ctx: Any) -> None:
            self.ctx = ctx
            ctx.agent_reply("背景内容", preactivate=["minigame_bottle"])

    bus = _Bus()
    gateway = EventGateway(
        event_source=object(),
        hook_bus=bus,
        legacy_pipeline=_Legacy(),
        notice_handler=object(),
        request_handler=object(),
        lifecycle_handler=object(),
        logger=_RecordingLogger(),
    )

    await gateway.handle(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 888,
            "user_id": 7,
            "message": [{"type": "text", "data": {"text": "hi"}}],
        }
    )

    assert captured == [
        {
            "skip": False,
            "intent": {"background": "背景内容", "preactivate": ("minigame_bottle",)},
        }
    ]
    # 意图一次性：事件上下文里已被取走
    assert bus.ctx.take_agent_reply_intent() is None


async def test_gateway_without_intent_keeps_legacy_call_signature() -> None:
    from neobot_app.runtime.gateway import EventGateway

    captured: list[dict[str, Any]] = []

    class _Legacy:
        async def handle_private_message_event(self, event, *, skip_ai_reply=False):
            captured.append({"skip": skip_ai_reply})

    class _Bus:
        async def dispatch(self, ctx: Any) -> None: ...

    gateway = EventGateway(
        event_source=object(),
        hook_bus=_Bus(),
        legacy_pipeline=_Legacy(),
        notice_handler=object(),
        request_handler=object(),
        lifecycle_handler=object(),
        logger=_RecordingLogger(),
    )

    await gateway.handle(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 7,
            "message": [{"type": "text", "data": {"text": "hi"}}],
        }
    )
    assert captured == [{"skip": False}]


# ── Pipeline：复用命令 background 通路 ───────────────────────────


def test_command_sync_reply_forwards_preactivate() -> None:
    orchestrator = _StubOrchestrator()
    pipeline = EventPipeline.__new__(EventPipeline)
    pipeline._reply_orchestrator = orchestrator
    pipeline._replying_queues = set()
    pipeline._logger = _RecordingLogger()

    pipeline._start_command_sync_reply(
        message=SimpleNamespace(),
        queue=_StubQueue(),
        queue_key="group:1",
        background="事实 + 提示词",
        preactivate=("minigame_bottle", "minigame_base"),
    )

    assert orchestrator.calls[0]["background_content"] == "事实 + 提示词"
    assert orchestrator.calls[0]["preactivate"] == ("minigame_bottle", "minigame_base")


def test_start_reply_puts_preactivate_on_reply_event() -> None:
    orchestrator = _StubOrchestrator()
    event = ReplyEvent(preactivate=("minigame_bottle",))
    assert event.preactivate == ("minigame_bottle",)
    assert orchestrator.calls == []


# ── 落点：本轮工具表按玩法生效 ────────────────────────────────────


async def test_executor_preactivate_adds_only_that_playstyle_tools(tmp_path: Path) -> None:
    manager = await _build_minigame_skill_manager(tmp_path)
    toolset = build_reply_toolset(skill_manager=manager)
    executor = toolset.executor

    def tool_names() -> set[str]:
        return {tool["function"]["name"] for tool in executor.definitions()}

    # 未命中：工具表里没有小游戏工具，也没有任何激活
    assert "minigame__bottle_write" not in tool_names()
    assert executor.activated_skill_names() == []

    loaded = executor.preactivate_skills(("minigame_bottle", "minigame_base"))

    assert loaded == ["minigame_base", "minigame_bottle"]
    names = tool_names()
    assert "minigame__bottle_write" in names
    assert "minigame__bottle_pick" in names
    assert "minigame__help" in names
    assert "minigame__points" in names
    # 只激活了漂流瓶 + 通用包：其它玩法的工具仍然不在表里
    assert "minigame__chengyu_submit" not in names
    assert "minigame__checkin" not in names
    assert "minigame__fortune" not in names


async def test_orchestrator_preactivates_before_building_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = await _build_minigame_skill_manager(tmp_path)
    captured: dict[str, Any] = {}
    original = ReplyToolExecutor.preactivate_skills

    def spy(self: ReplyToolExecutor, names: Any) -> list[str]:
        result = original(self, names)
        captured["names"] = tuple(names)
        captured["tools"] = {tool["function"]["name"] for tool in self.definitions()}
        return result

    monkeypatch.setattr(ReplyToolExecutor, "preactivate_skills", spy)

    provider = _ScriptedProvider([{"content": "好的", "tool_calls": []}])
    orchestrator = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        skill_manager=manager,
    )
    message = GroupMessage(
        message_type=MessageTypeEnum.group,
        message_id=1,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": "想玩漂流瓶"})],
        raw_message="想玩漂流瓶",
        group_id=888888,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )
    event = orchestrator.start_reply(
        message=message,
        queue=MessageQueue(),
        queue_key="888888",
        decision=WillingDecision(
            manager_name="test",
            probability=1.0,
            should_reply=True,
            reasons=("测试触发",),
        ),
        background_content="事实 + 提示词",
        preactivate=("minigame_bottle", "minigame_base"),
    )
    assert event is not None

    for _ in range(200):
        if not orchestrator._active_pipelines:
            break
        await asyncio.sleep(0.01)

    assert captured.get("names") == ("minigame_bottle", "minigame_base")
    assert "minigame__bottle_write" in captured["tools"]
    assert "minigame__chengyu_submit" not in captured["tools"]
    # 背景内容仍然照常进入本轮消息
    assert {"role": "user", "content": "事实 + 提示词"} in provider.calls[0][0]
    await orchestrator.shutdown()

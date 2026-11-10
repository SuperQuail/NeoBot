"""回复选路：双通道下的通道透传、工具 channel 参数、提示词账号与 self-sent 归属。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import NullLogger

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.orchestrator_parts.lifecycle_start import LifecycleStartMixin
from neobot_app.reply.orchestrator_parts.prompt_build import PromptBuildMixin
from neobot_app.reply.sender import ReplySender, SelfSentSink
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_app.willing.models import WillingDecision


# ── 假件 ────────────────────────────────────────────────────────────


class _ChannelAdapter:
    """记录 adapter.send 收到的 channel 关键字（未传时不产生该键）。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send(self, conversation_ref, payload, wait_response: bool = True, **kwargs):
        self.calls.append(dict(kwargs))
        return {"status": "ok", "message_id": 1}


class _FileServer:
    _enabled = False

    def register_file(self, path):
        return f"file:///{path}"


class _Queue:
    def __init__(self) -> None:
        self.messages: list = []

    def push(self, key, message) -> None:
        self.messages.append(message)

    def get_last_message_id(self, key):
        return None


class _FakeUow:
    """self-sent 落盘的假 UoW（不触达数据库）。"""

    def __init__(self) -> None:
        self.messages = SimpleNamespace(save_message=AsyncMock())
        self.commit = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _ready_event(*, kind: str = "group", channel: str | None = None, account: int = 0) -> ReplyEvent:
    event = ReplyEvent(
        conversation_ref=ConversationRef(kind=kind, id="123"),
        neobot_channel=channel,
        bot_account=account,
    )
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return event


def _sender(**overrides) -> tuple[ReplySender, _ChannelAdapter]:
    adapter = overrides.pop("adapter", None) or _ChannelAdapter()
    sender = ReplySender(
        adapter=adapter,
        file_server=_FileServer(),
        bot_name="Bot",
        self_sent_uow_factory=_FakeUow,
        **overrides,
    )
    return sender, adapter


# ── ReplyEvent / start_reply ────────────────────────────────────────


def test_reply_event_defaults_for_channel_and_account():
    event = ReplyEvent()
    assert event.neobot_channel is None
    assert event.bot_account == 0


class _StartStub(LifecycleStartMixin, PromptBuildMixin):
    """只保留 start_reply 需要的最小编排器桩。"""

    def __init__(self) -> None:
        self._closed = False
        self._active_pipelines: dict = {}
        self._last_reply_time: dict = {}
        self._tasks: set = set()
        self._agent_tool_turns: dict = {}
        self._logger = NullLogger()
        self._config = None
        self._bot_profile = None
        self.runs: list[ReplyEvent] = []

    def _resolve_mode(self) -> str:
        return "common"

    def _record_debug(self, stage, event, **extra) -> None:
        pass

    def _get_cooldown_seconds(self) -> float:
        return 0.0

    def _release_executor(self, event_id: str) -> None:
        pass

    async def _run(self, event, queue, queue_key) -> None:
        self.runs.append(event)


def _decision() -> WillingDecision:
    return WillingDecision(manager_name="stub", probability=1.0, should_reply=True)


async def test_start_reply_copies_channel_and_bot_account_from_message():
    stub = _StartStub()
    message = SimpleNamespace(message_type="group", neobot_channel="official", self_id=222)

    event = stub.start_reply(message=message, queue=SimpleNamespace(), queue_key="42", decision=_decision())

    assert event is not None
    assert event.neobot_channel == "official"
    assert event.bot_account == 222
    await asyncio.gather(*stub._tasks)
    assert stub.runs == [event]


async def test_start_reply_without_channel_fields_uses_safe_defaults():
    stub = _StartStub()
    message = SimpleNamespace(message_type="group")

    event = stub.start_reply(message=message, queue=SimpleNamespace(), queue_key="42", decision=_decision())

    assert event is not None
    assert event.neobot_channel is None
    assert event.bot_account == 0
    await asyncio.gather(*stub._tasks)


# ── sender：channel 透传 ────────────────────────────────────────────


async def test_send_with_timeout_passes_channel_to_adapter():
    sender, adapter = _sender()

    await sender.send_with_timeout(ConversationRef(kind="private", id="1"), {"type": "text"}, channel="official")

    assert adapter.calls == [{"channel": "official"}]


async def test_send_with_timeout_omits_channel_for_legacy_adapters():
    """单通道/旧适配器的 send 没有 channel 参数，None 时不能传。"""
    sender, adapter = _sender()

    await sender.send_with_timeout(ConversationRef(kind="private", id="1"), {"type": "text"})

    assert adapter.calls == [{}]


async def test_send_reply_uses_event_channel_by_default():
    sender, adapter = _sender()

    assert await sender.send_reply(_ready_event(channel="official"), "你好") is True

    assert adapter.calls
    assert all(call.get("channel") == "official" for call in adapter.calls)


async def test_send_reply_explicit_channel_wins():
    sender, adapter = _sender()

    await sender.send_reply(_ready_event(channel="onebot"), "你好", channel="official")

    assert adapter.calls[0]["channel"] == "official"


async def test_send_reply_legacy_event_omits_channel():
    sender, adapter = _sender()

    await sender.send_reply(_ready_event(), "你好")

    assert "channel" not in adapter.calls[0]


# ── self-sent 归属 ─────────────────────────────────────────────────


async def test_self_sent_history_uses_event_bot_account():
    sender, _adapter = _sender()
    queue = _Queue()
    event = _ready_event(channel="official", account=222)

    await sender.send_reply(event, "你好", self_sent=SelfSentSink(queue=queue, queue_key="123"))

    assert queue.messages, "self-sent 历史没有写回队列"
    assert queue.messages[-1].user_id == 222


def test_resolve_bot_account_prefers_event_account():
    config = BotConfig()
    config.bot.account = 111
    sender = ReplySender(adapter=_ChannelAdapter(), file_server=_FileServer(), config=config)

    assert sender._resolve_bot_account(222) == 222
    assert sender._resolve_bot_account(0) == 111
    assert sender._resolve_bot_account() == 111


# ── send_reply 工具的 channel 参数 ─────────────────────────────────


def _executor(handler) -> ReplyToolExecutor:
    return ReplyToolExecutor(send_reply_handler=handler)


async def test_send_reply_tool_passes_explicit_channel():
    seen: dict = {}

    async def handler(**kwargs):
        seen.update(kwargs)
        return True

    await _executor(handler).execute("send_reply", {"text": "你好", "channel": "official"})

    assert seen["channel"] == "official"


async def test_send_reply_tool_auto_channel_is_omitted():
    seen: dict = {}

    async def handler(**kwargs):
        seen.update(kwargs)
        return True

    await _executor(handler).execute("send_reply", {"text": "你好", "channel": "auto"})

    assert "channel" not in seen


async def test_send_reply_tool_rejects_unknown_channel():
    async def handler(**kwargs):
        return True

    result = await _executor(handler).execute("send_reply", {"text": "你好", "channel": "bridge"})

    assert "错误" in result
    assert "channel" in result


def test_send_reply_tool_schema_exposes_channel_enum():
    definition = next(item for item in _executor(None).definitions() if item["function"]["name"] == "send_reply")
    channel = definition["function"]["parameters"]["properties"]["channel"]

    assert channel["enum"] == ["auto", "onebot", "official"]
    assert channel["default"] == "auto"


# ── 提示词账号 ─────────────────────────────────────────────────────


class _ProfileService:
    async def get_group_name(self, group_id):
        return "测试群"

    async def render_group_member_list(
        self, group_id, message_queue, *, archive_fetch_window=None, include_archives=False
    ):
        return ""

    async def render_bot_group_admin_status(self, group_id, bot_account, message_queue):
        return f"机器人QQ:{bot_account}"

    async def render_group_owner_text(self, group_id, message_queue):
        return ""

    async def ensure_user_profile(self, user_id):
        return SimpleNamespace(nick_name="小明", remark="", profile="")

    async def render_friend_info(self, user_id, *, profile=None):
        return ""


class _EmptyQueue:
    def to_text(self, key, last_reply_message_id=None, *, all_new=False):
        return ""

    def iterate_from_newest(self, key):
        raise KeyError(key)


def _builder(account: int = 0) -> PromptBuilder:
    config = BotConfig()
    config.bot.account = account
    return PromptBuilder(config, _ProfileService())


async def test_group_prompt_uses_event_bot_account_override():
    prompt = await _builder(account=111).build_group_chat_prompt(123, _EmptyQueue(), bot_account=777)

    assert "你的QQ号是777" in prompt
    assert "机器人QQ:777" in prompt


async def test_friend_prompt_falls_back_to_config_account():
    prompt = await _builder(account=111).build_friend_chat_prompt(456, _EmptyQueue())

    assert "你的QQ号是111" in prompt


async def test_friend_prompt_uses_event_bot_account_override():
    prompt = await _builder(account=111).build_friend_chat_prompt(456, _EmptyQueue(), bot_account=777)

    assert "你的QQ号是777" in prompt


async def test_role_messages_use_event_bot_account():
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = None
    orch._prompt_builder = SimpleNamespace(build_group_chat_messages=AsyncMock(return_value=[]))
    event = ReplyEvent(neobot_channel="onebot", bot_account=777)
    event.conversation_ref = ConversationRef(kind="group", id="42")

    await orch._build_role_messages(event, queue=SimpleNamespace(), queue_key="42")

    assert orch._prompt_builder.build_group_chat_messages.await_args.kwargs["bot_account"] == 777


async def test_role_messages_fall_back_to_config_bot_account():
    config = BotConfig()
    config.bot.account = 111
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = config
    orch._prompt_builder = SimpleNamespace(build_group_chat_messages=AsyncMock(return_value=[]))
    event = ReplyEvent()
    event.conversation_ref = ConversationRef(kind="group", id="42")

    await orch._build_role_messages(event, queue=SimpleNamespace(), queue_key="42")

    assert orch._prompt_builder.build_group_chat_messages.await_args.kwargs["bot_account"] == 111

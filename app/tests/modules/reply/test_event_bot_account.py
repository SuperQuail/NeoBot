"""回复管线取号的统一来源：双通道下按事件账号，未解析时回退提供者/配置。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import neobot_app.prompt.role_messages as role_messages
from neobot_app.bot_accounts import bind_bot_accounts
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.message.numbering import MessageNumbering
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.orchestrator_parts.agent_prompt import AgentPromptMixin
from neobot_contracts.ports.logging import NullLogger

ONEBOT_ACCOUNT = 11111
OFFICIAL_ACCOUNT = 22222


class _Detector:
    def __init__(self, accounts: dict[str, int], primary: int) -> None:
        self.accounts = dict(accounts)
        self.profile = SimpleNamespace(account=primary)

    def account_for(self, channel: str) -> int:
        return int(self.accounts.get(channel, 0) or 0)


@pytest.fixture(autouse=True)
def _reset_bot_accounts():
    bind_bot_accounts(None, None)
    yield
    bind_bot_accounts(None, None)


def _config(account: int = 0) -> BotConfig:
    config = BotConfig()
    config.bot.account = account
    return config


def _orchestrator(config=None, detector=None) -> ReplyOrchestrator:
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = config
    orch._bot_profile = detector
    return orch


# ── settings._get_bot_account ──────────────────────────────────────


def test_get_bot_account_prefers_resolved_primary():
    """身份已解析：主账号来自 API（双通道 OneBot 优先），不是 config 的单值。"""
    bind_bot_accounts(None, _Detector({"onebot": ONEBOT_ACCOUNT}, primary=ONEBOT_ACCOUNT))
    orch = _orchestrator(_config(99999), None)

    assert orch._get_bot_account() == ONEBOT_ACCOUNT


def test_get_bot_account_falls_back_to_config_before_resolution():
    config = _config(99999)
    orch = _orchestrator(config, None)

    assert orch._get_bot_account() == 99999


# ── agent_prompt：MessageNumbering ──────────────────────────────────


class _PromptStub(AgentPromptMixin):
    """只保留 _prepare_agent_messages 依赖的最小桩。"""

    def __init__(self) -> None:
        self._config = None
        self._bot_profile = None
        self._markdown_skills = None
        self._skill_manager = None
        self._provider = None
        self._prompt_store = None
        self.captured_numbering = None

    def _resolve_last_reply(self, queue, queue_key):
        return None, False

    async def _build_role_messages(
        self,
        event,
        queue,
        queue_key,
        *,
        numbering=None,
        last_reply_message_id=None,
        all_new=False,
    ):
        self.captured_numbering = numbering
        return []

    async def _build_prompt(self, event, queue, queue_key, **kwargs):
        return "prompt"

    def _record_flow_prompt(self, *args, **kwargs):
        pass

    def _record_debug(self, *args, **kwargs):
        pass

    def _take_unsent_marker(self, event):
        return False


class _Queue:
    def clone(self, key):
        return self


async def test_message_numbering_uses_event_bot_account():
    """事件自带通道账号：MessageNumbering 用它识别自身发言，不读 config。"""
    stub = _PromptStub()
    stub._config = _config(99999)
    event = ReplyEvent(bot_account=OFFICIAL_ACCOUNT)
    event.state = ReplyState.BUILDING_PROMPT

    await stub._prepare_agent_messages(event, _Queue(), "42")

    assert stub.captured_numbering is not None
    assert stub.captured_numbering._bot_account == OFFICIAL_ACCOUNT


async def test_message_numbering_falls_back_to_config_before_resolution():
    config = _config(99999)
    stub = _PromptStub()
    stub._config = config
    event = ReplyEvent(bot_account=0)
    event.state = ReplyState.BUILDING_PROMPT

    await stub._prepare_agent_messages(event, _Queue(), "42")

    assert stub.captured_numbering is not None
    assert stub.captured_numbering._bot_account == 99999


# ── agent_pipeline：增量角色消息 ────────────────────────────────────


def _capture_builder(monkeypatch, captured: dict, name: str) -> None:
    def fake_builder(entries, queue, queue_key="", **kwargs):
        captured.update(kwargs)
        return [{"role": "user", "content": "新消息"}]

    monkeypatch.setattr(role_messages, name, fake_builder)


async def test_agent_inject_new_entries_uses_event_bot_account(monkeypatch):
    """工具执行期间到达的新消息：assistant 判定用事件账号。"""
    captured: dict = {}
    _capture_builder(monkeypatch, captured, "build_role_messages_from_entries")
    orch = _orchestrator(_config(99999), None)
    orch._collect_new_entries = lambda queue, queue_copy, queue_key: [object()]
    orch._show_boundary_markers = lambda: False
    orch._record_debug = lambda *args, **kwargs: None
    event = ReplyEvent(bot_account=OFFICIAL_ACCOUNT)

    await orch._agent_inject_new_entries(
        event=event,
        queue_key="42",
        queue=SimpleNamespace(),
        queue_copy=SimpleNamespace(),
        numbering=MessageNumbering(),
        messages=[],
        is_group=False,
        rendered_user_ids=set(),
    )

    assert captured["bot_account"] == OFFICIAL_ACCOUNT


async def test_private_pipeline_tail_uses_event_bot_account(monkeypatch):
    """私聊挂起恢复注入新消息：assistant 判定用事件账号。"""
    captured: dict = {}
    _capture_builder(monkeypatch, captured, "build_role_messages_from_entries")
    orch = _orchestrator(_config(99999), None)
    orch._logger = NullLogger()
    orch._estimate_tokens = lambda messages: 1
    orch._get_private_chat_max_tokens = lambda: 1_000_000

    async def _suspend(queue, queue_copy, queue_key):
        return [object()], None

    orch._suspend_private_chat = _suspend
    orch._record_debug = lambda *args, **kwargs: None
    orch._show_boundary_markers = lambda: False
    event = ReplyEvent(bot_account=OFFICIAL_ACCOUNT)

    continued = await orch._agent_private_pipeline_tail(
        event=event,
        queue_key="7",
        queue=SimpleNamespace(),
        queue_copy=SimpleNamespace(),
        numbering=MessageNumbering(),
        messages=[],
        native_vision_active=False,
        vision_context=SimpleNamespace(request_messages=lambda messages: messages),
    )

    assert continued is True
    assert captured["bot_account"] == OFFICIAL_ACCOUNT


# ── observability：成本续用的重启渲染 ──────────────────────────────


class _Estimate:
    cost = 1.0

    @staticmethod
    def cheaper_than_full_miss() -> bool:
        return True


class _Calculator:
    def estimate_cost(self, key, text):
        return _Estimate()


def _cost_orchestrator(config) -> ReplyOrchestrator:
    orch = _orchestrator(config, None)
    orch._cost_pipeline_enabled = lambda: True
    orch._cache_calculator = _Calculator()
    orch._provider = None
    orch._show_boundary_markers = lambda: False
    return orch


def test_cost_restart_render_uses_explicit_event_account(monkeypatch):
    """重启成本渲染收到事件账号时优先使用它。"""
    captured: dict = {}

    def fake_build(queue, queue_key, **kwargs):
        captured.update(kwargs)
        return [{"role": "user", "content": "历史消息" * 5}]

    monkeypatch.setattr(role_messages, "build_role_messages", fake_build)
    orch = _cost_orchestrator(_config(99999))

    assert (
        orch._cache_continue_cheaper_than_restart(
            [{"role": "user", "content": "你好" * 20}],
            "system prompt",
            SimpleNamespace(),
            "42",
            MessageNumbering(),
            bot_account=OFFICIAL_ACCOUNT,
        )
        is True
    )
    assert captured["bot_account"] == OFFICIAL_ACCOUNT


def test_cost_restart_render_falls_back_to_config_account(monkeypatch):
    """未传事件账号时回退提供者主账号（未解析/单通道即 config）。"""
    captured: dict = {}

    def fake_build(queue, queue_key, **kwargs):
        captured.update(kwargs)
        return [{"role": "user", "content": "历史消息" * 5}]

    monkeypatch.setattr(role_messages, "build_role_messages", fake_build)
    orch = _cost_orchestrator(_config(99999))

    assert (
        orch._cache_continue_cheaper_than_restart(
            [{"role": "user", "content": "你好" * 20}],
            "system prompt",
            SimpleNamespace(),
            "42",
            MessageNumbering(),
        )
        is True
    )
    assert captured["bot_account"] == 99999

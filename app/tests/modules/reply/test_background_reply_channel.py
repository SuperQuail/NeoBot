"""后台/定时/跨聊天合成事件的通道钉定测试。

覆盖契约：start_background_reply 在合成消息上保留目标会话的来源通道
（neobot_channel），并在启动管线时把该通道钉进事件上下文，后续 call_api
查同一条通道；官方会话在后台轮次仍被识别为官方（能力限制照常生效）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from neobot_adapter.switchable import current_channel
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator_parts.lifecycle_shutdown import LifecycleShutdownMixin
from neobot_app.reply.orchestrator_parts.prompt_build import PromptBuildMixin
from neobot_contracts.ports.logging import NullLogger

#: 官方协议的合成会话 ID：13 位。
_OFFICIAL_ID = "9000000000001"
#: OneBot 的真实群号 / QQ 号：<= 12 位。
_REAL_GROUP = "123456"


class _FakeAdapter:
    """只暴露通道相关能力；active_channels 存在才算支持通道。"""

    def __init__(
        self,
        *,
        history: dict[tuple[str, str], tuple[str, ...]] | None = None,
        active: tuple[str, ...] = ("onebot", "official"),
    ) -> None:
        self.active_channels = active
        self._history = history or {}

    def channels_for_conversation(self, conversation: Any) -> tuple[str, ...]:
        return self._history.get((conversation.kind, str(conversation.id)), ())


class _Stub(LifecycleShutdownMixin, PromptBuildMixin):
    """只保留 start_background_reply 需要的编排器桩；start_reply 只记录参数。"""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self._closed = False
        self._active_pipelines: dict[str, Any] = {}
        self._logger = NullLogger()
        self._group_queue = SimpleNamespace()
        self._friend_queue = SimpleNamespace()
        self.started: dict[str, Any] | None = None
        self.ambient: str | None = None

    def start_reply(self, **kwargs: Any) -> object:
        self.started = kwargs
        self.ambient = current_channel()
        return object()


def _start(stub: _Stub, **overrides: Any) -> object | None:
    values: dict[str, Any] = {
        "kind": "group",
        "conversation_id": _OFFICIAL_ID,
        "content": "绘图完成",
    }
    values.update(overrides)
    return stub.start_background_reply(**values)


def _synthetic_channel(stub: _Stub) -> str | None:
    assert stub.started is not None
    message = stub.started["message"]
    return getattr(message, "neobot_channel", None)


def _official_platform(stub: _Stub, channel: str | None) -> bool:
    event = ReplyEvent(neobot_channel=channel)
    return stub._is_official_platform(event)


# ── 通道来源：显式 > 会话历史 > ID 规模 ────────────────────────────


def test_background_reply_uses_conversation_history_channel() -> None:
    adapter = _FakeAdapter(history={("group", _REAL_GROUP): ("official",)})
    stub = _Stub(adapter)

    _start(stub, conversation_id=_REAL_GROUP)

    assert _synthetic_channel(stub) == "official"


def test_background_reply_infers_official_from_13_digit_id() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub)  # 历史里没见过的官方会话 ID

    assert _synthetic_channel(stub) == "official"


def test_background_reply_infers_onebot_from_real_group_number() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub, conversation_id=_REAL_GROUP)

    assert _synthetic_channel(stub) == "onebot"


def test_background_reply_private_target_infers_channel() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub, kind="private", conversation_id="9000000000002")
    assert _synthetic_channel(stub) == "official"

    stub = _Stub(_FakeAdapter())
    _start(stub, kind="private", conversation_id="1234567")
    assert _synthetic_channel(stub) == "onebot"


def test_background_reply_explicit_channel_wins() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub, conversation_id=_REAL_GROUP, channel="official")

    assert _synthetic_channel(stub) == "official"


def test_background_reply_legacy_adapter_keeps_no_channel() -> None:
    """本地/旧适配器没有 active_channels：不猜通道，保持旧行为。"""
    stub = _Stub(SimpleNamespace(connected=True))

    _start(stub)

    assert _synthetic_channel(stub) is None
    assert stub.ambient is None


def test_background_reply_non_qq_target_keeps_no_channel() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub, kind="bilibili", conversation_id="1234")
    assert _synthetic_channel(stub) is None

    stub = _Stub(_FakeAdapter())
    _start(stub, conversation_id="not-a-number")
    assert _synthetic_channel(stub) is None


# ── 上下文与官方限制 ───────────────────────────────────────────────


def test_background_reply_pins_channel_in_reply_context() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub)

    assert stub.ambient == "official"
    assert current_channel() is None  # 管线启动后上下文已恢复


def test_background_reply_for_official_chat_keeps_official_restrictions() -> None:
    """官方会话的后台轮次：事件仍按官方通道处理，官方能力限制不能丢。"""
    stub = _Stub(_FakeAdapter())

    _start(stub)
    official_channel = _synthetic_channel(stub)

    assert _official_platform(stub, official_channel) is True


def test_background_reply_for_onebot_chat_is_not_official() -> None:
    stub = _Stub(_FakeAdapter())

    _start(stub, conversation_id=_REAL_GROUP)

    assert _official_platform(stub, _synthetic_channel(stub)) is False

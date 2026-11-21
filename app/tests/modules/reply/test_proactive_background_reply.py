"""官方主动消息回退：后台/定时/跨聊天轮次必须带 proactive 标志。

被动回复额度耗尽或没有可用被动 msg_id 时，官方适配器只有收到 proactive=True
才会改走主动消息；否则后台通知/定时任务在官方会话会直接发送失败。
本文件从 start_reply/start_background_reply 一路断言到假 adapter.send 的参数。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import (
    MessageSegment,
    MessageTypeEnum,
    PrivateMessage,
)
from neobot_contracts.ports.logging import NullLogger

from neobot_app.message.queue import MessageQueue
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.willing.models import WillingDecision


class _FakeChat:
    """除显式字段外，所有配置属性默认返回 None（触发源模块的默认分支）。"""

    reply_mode = "agent"

    def __getattr__(self, name: str):
        return None


class _FakeConfig:
    chat = _FakeChat()
    bot = SimpleNamespace(nick_name="Bot")


class _FakePromptBuilder:
    async def build_friend_chat_prompt(self, **kwargs):
        return "私聊提示词"

    async def build_group_chat_prompt(self, **kwargs):
        return "群聊提示词"

    async def build_group_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "群聊历史消息"}]

    async def build_friend_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "私聊历史消息"}]


class _CapturingAdapter:
    """假官方适配器：记录 adapter.send 的全部参数（含 proactive/channel）。"""

    def __init__(self) -> None:
        self.active_channels = ("official",)
        self.sends: list[dict] = []

    def channels_for_conversation(self, conversation) -> tuple[str, ...]:
        return ("official",)

    async def send(self, conversation_ref, payload, wait_response: bool = True, **kwargs) -> dict:
        self.sends.append(
            {
                "conversation": conversation_ref,
                "payload": payload,
                "wait_response": wait_response,
                **kwargs,
            }
        )
        return {"status": "ok", "message_id": 1}

    async def call_api(self, action: str, params: dict) -> dict:
        return {"status": "ok"}


class _ScriptedProvider:
    """按脚本返回模型响应；脚本耗尽视为模型停止调用工具。"""

    max_tokens = 10000

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def chat(self, messages, tools=None):
        self.calls += 1
        if not self._responses:
            return {"content": "", "tool_calls": []}
        return self._responses.pop(0)

    async def close(self) -> None:
        pass


def _send_reply_call(text: str) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {
                "id": "call-send-reply",
                "type": "function",
                "function": {
                    "name": "send_reply",
                    "arguments": json.dumps({"text": text}),
                },
            }
        ],
    }


def _send_markdown_call(content: str) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {
                "id": "call-markdown",
                "type": "function",
                "function": {
                    "name": "send_official_markdown",
                    "arguments": json.dumps({"content": content}),
                },
            }
        ],
    }


def _orchestrator(adapter: _CapturingAdapter, provider: _ScriptedProvider) -> ReplyOrchestrator:
    return ReplyOrchestrator(
        adapter=adapter,
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        group_message_queue=MessageQueue(),
        friend_message_queue=MessageQueue(),
        config=_FakeConfig(),
        logger=NullLogger(),
    )


def _decision() -> WillingDecision:
    return WillingDecision(
        manager_name="test",
        probability=1.0,
        should_reply=True,
        reasons=("测试触发",),
    )


async def _wait_for_send(
    adapter: _CapturingAdapter,
    predicate=None,
    *,
    timeout: float = 5.0,
) -> dict:
    """等管线真的发出消息（agent 模式发送后会挂起等待后续消息，不能等任务结束）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        for send in adapter.sends:
            if predicate is None or predicate(send):
                return send
        await asyncio.sleep(0.01)
    raise AssertionError(f"等待发送超时；当前 sends={adapter.sends}")


def _private_message(text: str = "你好") -> PrivateMessage:
    return PrivateMessage(
        message_type=MessageTypeEnum.private,
        message_id=1,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )


async def test_background_official_reply_sends_proactive_text() -> None:
    """后台通知在官方会话没有被动目标：event.proactive=True 并透传到 adapter.send。"""
    adapter = _CapturingAdapter()
    provider = _ScriptedProvider([_send_reply_call("该喝水了")])
    orch = _orchestrator(adapter, provider)
    try:
        event = orch.start_background_reply(
            kind="private",
            conversation_id="9000000000001",
            content="提醒用户喝水",
        )
        assert event is not None
        assert event.proactive is True

        send = await _wait_for_send(adapter)

        assert send.get("proactive") is True
        assert send.get("channel") == "official"
        assert send["wait_response"] is False
    finally:
        await orch.shutdown()


async def test_background_official_markdown_passes_proactive() -> None:
    """send_official_markdown 后台 handler 也要透传 proactive（卡片同样走主动消息）。"""
    adapter = _CapturingAdapter()
    provider = _ScriptedProvider([_send_markdown_call("## 提醒\n\n记得喝水")])
    orch = _orchestrator(adapter, provider)
    try:
        event = orch.start_background_reply(
            kind="private",
            conversation_id="9000000000001",
            content="提醒用户喝水",
        )
        assert event is not None

        send = await _wait_for_send(
            adapter,
            lambda item: any(
                segment.get("type") == "official_markdown" for segment in item["payload"]
            ),
        )

        assert send.get("proactive") is True
        assert send.get("channel") == "official"
    finally:
        await orch.shutdown()


async def test_foreground_official_reply_keeps_passive_semantics() -> None:
    """前台回复不改行为：事件不加 proactive，发送仍走被动消息。"""
    adapter = _CapturingAdapter()
    provider = _ScriptedProvider([_send_reply_call("收到")])
    orch = _orchestrator(adapter, provider)
    queue = MessageQueue()
    try:
        event = orch.start_reply(
            message=_private_message(),
            queue=queue,
            queue_key="1234567",
            decision=_decision(),
        )
        assert event is not None
        assert event.proactive is False

        send = await _wait_for_send(adapter)

        assert "proactive" not in send
    finally:
        await orch.shutdown()


async def test_start_reply_proactive_parameter_reaches_event() -> None:
    """显式传 proactive=True 时事件携带该标志（供调用方自行开主动消息）。"""
    adapter = _CapturingAdapter()
    provider = _ScriptedProvider([_send_reply_call("收到")])
    orch = _orchestrator(adapter, provider)
    queue = MessageQueue()
    try:
        event = orch.start_reply(
            message=_private_message(),
            queue=queue,
            queue_key="1234567",
            decision=_decision(),
            proactive=True,
        )
        assert event is not None
        assert event.proactive is True

        send = await _wait_for_send(adapter)

        assert send.get("proactive") is True
    finally:
        await orch.shutdown()

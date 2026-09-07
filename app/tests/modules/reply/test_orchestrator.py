"""ReplyOrchestrator 测试：agent 模式 wait 工具 previous_entries 初始化、管线去重、shutdown、队列差集逻辑。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import (
    GroupMessage,
    MessageSegment,
    MessageTypeEnum,
    PrivateMessage,
)
from neobot_app.message.queue import MessageQueue, QueueEntry, QueueEntryType
from neobot_app.reply.orchestrator import (
    ReplyOrchestrator,
    _parse_tool_args,
    _redacted_tool_text,
    _safe_tool_args,
)
from neobot_app.willing.models import WillingDecision


class _FakeChat:
    """除显式字段外，所有配置属性默认返回 None（触发源模块的默认分支）。"""

    reply_mode = "agent"

    def __getattr__(self, name: str):
        return None


class _FakeBot:
    nick_name = "Bot"


class _FakeConfig:
    chat = _FakeChat()
    bot = _FakeBot()


class _FakePromptBuilder:
    async def build_friend_chat_prompt(self, **kwargs):
        return "私聊提示词"

    async def build_group_chat_prompt(self, **kwargs):
        return "群聊提示词"

    async def build_group_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "群聊历史消息"}]

    async def build_friend_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "私聊历史消息"}]


class _HangingProvider:
    """chat 永远挂起，用于保持管线活跃。"""

    async def chat(self, messages, tools=None):
        await asyncio.Event().wait()

    async def close(self):
        pass


class _ScriptedProvider:
    """按脚本依次返回响应，用于最小 agent 循环。"""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list, object]] = []

    async def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        return self._responses.pop(0)

    async def close(self):
        pass


class _FakeAdapter:
    async def send(self, conversation_ref, payload):
        return {"status": "ok", "message_id": 2001}

    async def call_api(self, action, params):
        return {"status": "ok"}


def _make_private_message(message_id: int = 1, text: str = "你好") -> PrivateMessage:
    return PrivateMessage(
        message_type=MessageTypeEnum.private,
        message_id=message_id,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )


def _make_group_message(message_id: int = 1) -> GroupMessage:
    return GroupMessage(
        message_type=MessageTypeEnum.group,
        message_id=message_id,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": "群消息"})],
        raw_message="群消息",
        group_id=888888,
        sender=PostMessageMessagesender(user_id=10001, nickname="用户1"),
    )


def _make_decision() -> WillingDecision:
    return WillingDecision(
        manager_name="test",
        probability=1.0,
        should_reply=True,
        reasons=("测试触发",),
    )


def _make_orchestrator(
    *,
    provider=None,
    prompt_builder=None,
    config=None,
    group_queue=None,
    friend_queue=None,
) -> ReplyOrchestrator:
    return ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=prompt_builder or _FakePromptBuilder(),
        provider=provider,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
        config=config or _FakeConfig(),
        logger=None,
    )


# ── 管线去重（并发用例）──────────────────────────────────────────


async def test_start_reply_same_pipeline_key_concurrent_deduplicates():
    """同一 queue_key 并发调用两次 start_reply，必须只创建一条管线，第二次返回 None。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    decision = _make_decision()

    async def _start():
        return orch.start_reply(
            message=_make_private_message(),
            queue=queue,
            queue_key="123456",
            decision=decision,
        )

    results = await asyncio.gather(_start(), _start())

    assert [r for r in results if r is not None] == [results[0]]
    assert len(orch._active_pipelines) == 1
    assert orch.is_pipeline_active("private", "123456") is True
    await orch.shutdown()
    assert not orch._active_pipelines


async def test_start_reply_different_pipeline_keys_both_allowed():
    """不同 queue_key（私聊 vs 群聊）并发调用不得互相阻塞，两条管线都创建。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    friend_queue = MessageQueue()
    group_queue = MessageQueue()
    orch._group_queue = group_queue
    orch._friend_queue = friend_queue
    decision = _make_decision()

    first = orch.start_reply(
        message=_make_private_message(),
        queue=friend_queue,
        queue_key="123456",
        decision=decision,
    )
    second = orch.start_reply(
        message=_make_group_message(),
        queue=group_queue,
        queue_key="888888",
        decision=decision,
    )

    assert first is not None
    assert second is not None
    assert len(orch._active_pipelines) == 2
    await orch.shutdown()


# ── shutdown 取消任务 ────────────────────────────────────────────


async def test_shutdown_cancels_active_pipeline():
    """shutdown 必须取消所有运行中的管线任务并清空注册表，事件被标记 cancelled。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    await asyncio.sleep(0.05)

    await orch.shutdown()

    assert not orch._active_pipelines
    assert not orch._tasks
    assert event.error == "cancelled"


async def test_shutdown_without_active_tasks_is_noop():
    """无活跃任务时 shutdown 必须正常返回且不抛异常。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    await orch.shutdown()
    assert not orch._active_pipelines
    assert not orch._tasks


# ── agent 模式 wait 工具 previous_entries 初始化 ─────────────────


async def test_wait_tool_agent_loop_previous_entries_initialized(monkeypatch):
    """agent 模式首次调用 wait 工具时 previous_entries 已初始化，不得 UnboundLocalError，工具结果注入消息列表。"""
    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "wait",
                            "arguments": json.dumps({"seconds": 1}),
                        },
                    }
                ],
            },
            {"content": "收到", "tool_calls": []},
        ]
    )
    orch = _make_orchestrator(provider=provider)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    for _ in range(200):
        if not orch._active_pipelines:
            break
        await asyncio.sleep(0.1)

    assert provider.calls, "provider 必须被调用"
    tool_messages = [m for m in provider.calls[1][0] if m.get("role") == "tool"]
    assert any("没有收到新消息" in m["content"] for m in tool_messages)
    assert event.generated_text == "收到"
    assert event.error is None
    await orch.shutdown()


async def test_private_pipeline_event_reaches_completed_state(monkeypatch):
    """私聊回复管线结束后事件必须进入 COMPLETED 终态并写入 completed_at。"""
    provider = _ScriptedProvider([{"content": "你好", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None
    for _ in range(200):
        if not orch._active_pipelines:
            break
        await asyncio.sleep(0.1)

    assert event.state.name == "COMPLETED"
    assert event.completed_at is not None
    await orch.shutdown()


# ── _collect_new_entries 队列差集逻辑 ────────────────────────────


async def test_collect_new_entries_returns_only_new_and_updates_snapshot():
    """_collect_new_entries 只返回快照之后的新消息，且更新快照后再次调用返回空。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    source.push(key, _make_private_message(message_id=1, text="第一条"))
    snapshot = source.clone(key)
    source.push(key, _make_private_message(message_id=2, text="第二条"))

    first = orch._collect_new_entries(source, snapshot, key)
    second = orch._collect_new_entries(source, snapshot, key)

    assert [e.message.message_id for e in first] == [2]
    assert second == []


async def test_collect_new_entries_deduplicates_by_fingerprint():
    """相同 message_id 的消息重复推入源队列时，指纹去重后不得再次作为新条目返回。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    snapshot = MessageQueue()
    source.push(key, _make_private_message(message_id=1, text="第一条"))
    snapshot.append_entries(key, source.entries(key))

    source.push(key, _make_private_message(message_id=1, text="重复的旧消息"))
    new = orch._collect_new_entries(source, snapshot, key)

    assert new == []


async def test_collect_new_entries_skips_command_consumed_messages():
    """命令系统已消费的消息不得作为新条目注入挂起管线，但仍计入快照避免反复收集。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    snapshot = source.clone(key)
    source.push(key, _make_private_message(message_id=1, text="/help"))
    source.mark_command_consumed(key, 1)

    first = orch._collect_new_entries(source, snapshot, key)
    second = orch._collect_new_entries(source, snapshot, key)

    assert first == []
    assert second == []


async def test_collect_new_entries_keeps_normal_messages_alongside_consumed():
    """命令已消费消息被过滤时，同批到达的普通消息仍正常返回。"""
    orch = _make_orchestrator()
    source = MessageQueue()
    key = "123456"
    snapshot = source.clone(key)
    source.push(key, _make_private_message(message_id=1, text="/help"))
    source.mark_command_consumed(key, 1)
    source.push(key, _make_private_message(message_id=2, text="普通消息"))

    new = orch._collect_new_entries(source, snapshot, key)

    assert [e.message.message_id for e in new] == [2]


async def test_consume_ai_reply_blocked_entries_filters_blocked():
    """reply_block_registry.consume_message 命中时必须过滤被插件拦截的消息条目。"""
    registry = type(
        "BlockRegistry",
        (),
        {
            "consume_message": lambda self, m: m.message_id == 2,
        },
    )()
    orch = _make_orchestrator()
    orch._reply_block_registry = registry
    entries = [
        QueueEntry(
            kind=QueueEntryType.MESSAGE,
            message=_make_private_message(message_id=1, text="a"),
        ),
        QueueEntry(
            kind=QueueEntryType.MESSAGE,
            message=_make_private_message(message_id=2, text="b"),
        ),
        QueueEntry(
            kind=QueueEntryType.MESSAGE,
            message=_make_private_message(message_id=3, text="c"),
        ),
    ]

    kept = orch._consume_ai_reply_blocked_entries(entries)

    assert [e.message.message_id for e in kept] == [1, 3]


async def test_consume_ai_reply_blocked_entries_without_registry_keeps_all():
    """未配置 reply_block_registry 时，_consume_ai_reply_blocked_entries 必须原样返回条目。"""
    orch = _make_orchestrator()
    entries = [
        QueueEntry(
            kind=QueueEntryType.MESSAGE,
            message=_make_private_message(message_id=1, text="a"),
        ),
    ]

    kept = orch._consume_ai_reply_blocked_entries(entries)

    assert kept == entries


# ── start_background_reply ───────────────────────────────────────


async def test_start_background_reply_creates_and_deduplicates_pipeline():
    """后台回复首次创建管线，同 key 重复调用返回 None；kind 为空时必须拒绝。"""
    orch = _make_orchestrator(provider=_HangingProvider())
    orch._group_queue = MessageQueue()

    first = orch.start_background_reply(
        kind="group",
        conversation_id="123456",
        content="绘图完成",
    )
    second = orch.start_background_reply(
        kind="group",
        conversation_id="123456",
        content="绘图完成",
    )
    invalid = orch.start_background_reply(kind="", conversation_id="", content="x")

    assert first is not None
    assert second is None
    assert invalid is None
    assert orch.is_pipeline_active("group", "123456") is True
    await orch.shutdown()


# ── 静态纯逻辑 ───────────────────────────────────────────────────


def test_build_conversation_ref_detects_kind():
    """GroupMessage 与 message_type='group' 的合成消息识别为群聊，PrivateMessage 识别为私聊。"""
    assert (
        ReplyOrchestrator._build_conversation_ref(_make_group_message(), "g1").kind
        == "group"
    )
    assert (
        ReplyOrchestrator._build_conversation_ref(_make_private_message(), "p1").kind
        == "private"
    )

    synthetic = type("Synthetic", (), {"message_type": "group"})()
    assert ReplyOrchestrator._build_conversation_ref(synthetic, "g2").kind == "group"


def test_api_succeeded_judges_status():
    """_api_succeeded：None 视为失败，status=='ok' 视为成功，其余 status 视为失败，非 dict 视为成功。"""
    assert ReplyOrchestrator._api_succeeded(None) is False
    assert ReplyOrchestrator._api_succeeded({"status": "ok"}) is True
    assert (
        ReplyOrchestrator._api_succeeded({"status": "failed", "message": "err"})
        is False
    )
    assert ReplyOrchestrator._api_succeeded({"message_id": 1}) is True
    assert ReplyOrchestrator._api_succeeded("raw string") is True


def test_last_user_text_skips_bot_self_messages():
    """bot 自己发送的消息（语音/图片追踪）不得计入技能匹配上下文：
    最后一条是 bot 消息时，取它之前最后一条用户消息的全部文本段。"""
    bot = _FakeBot()
    bot.account = 12345
    config = _FakeConfig()
    config.bot = bot
    orch = _make_orchestrator(config=config)
    queue = MessageQueue()
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="用户问天气"))
    bot_msg = _make_private_message(message_id=2, text="[语音消息:天气]")
    bot_msg.user_id = 12345
    queue.push(key, bot_msg)

    assert orch._last_user_text(queue, key) == "用户问天气"


def test_last_user_text_without_bot_account_keeps_all():
    """未配置 bot account 时无法识别自身消息，不过滤 bot 消息：取最后一条消息的全部文本段。"""
    orch = _make_orchestrator()
    queue = MessageQueue()
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="用户问天气"))
    other_msg = _make_private_message(message_id=2, text="其他消息")
    other_msg.user_id = 99999
    queue.push(key, other_msg)

    assert orch._last_user_text(queue, key) == "其他消息"


def test_last_user_text_uses_only_last_user_message():
    """只取最后一条用户消息的全部文本段：更早消息中的旧关键词不得被激活。"""
    orch = _make_orchestrator()
    queue = MessageQueue()
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="我想画一张图"))
    queue.push(key, _make_private_message(message_id=2, text="其实不用了，谢谢"))

    assert orch._last_user_text(queue, key) == "其实不用了，谢谢"


def test_last_user_text_skips_bot_then_takes_next_user_message():
    """bot 消息之后有新用户消息时，取该新用户消息；bot 消息不算用户消息。"""
    bot = _FakeBot()
    bot.account = 12345
    config = _FakeConfig()
    config.bot = bot
    orch = _make_orchestrator(config=config)
    queue = MessageQueue()
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="用户问天气"))
    bot_msg = _make_private_message(message_id=2, text="[语音消息:天气]")
    bot_msg.user_id = 12345
    queue.push(key, bot_msg)
    queue.push(key, _make_private_message(message_id=3, text="天气怎么样呢"))

    assert orch._last_user_text(queue, key) == "天气怎么样呢"


def test_last_user_text_joins_all_text_segments_of_last_user_message():
    """最后一条用户消息的多个文本段必须全部拼接（跳过非文本段）。"""
    orch = _make_orchestrator()
    queue = MessageQueue()
    key = "123456"
    msg = _make_private_message(message_id=1, text="画一只猫")
    msg.message = [
        MessageSegment(type="text", data={"text": "画一只猫"}),
        MessageSegment(type="image", data={"file": "x.png"}),
        MessageSegment(type="text", data={"text": "要写实风格"}),
    ]
    queue.push(key, msg)

    assert orch._last_user_text(queue, key) == "画一只猫 要写实风格"


def test_last_user_text_returns_empty_when_all_messages_are_bot():
    """队列中只有 bot 消息时返回空字符串（不激活任何技能）。"""
    bot = _FakeBot()
    bot.account = 12345
    config = _FakeConfig()
    config.bot = bot
    orch = _make_orchestrator(config=config)
    queue = MessageQueue()
    key = "123456"
    bot_msg = _make_private_message(message_id=1, text="[语音消息:天气]")
    bot_msg.user_id = 12345
    queue.push(key, bot_msg)

    assert orch._last_user_text(queue, key) == ""


def test_last_user_text_malformed_account_does_not_crash():
    """bot.account 为畸形配置（非数字，如 "your_qq"）时 _last_user_text 不崩溃，
    且无法识别自身消息时不作过滤（保持旧行为）。"""
    bot = _FakeBot()
    bot.account = "your_qq"
    config = _FakeConfig()
    config.bot = bot
    orch = _make_orchestrator(config=config)
    queue = MessageQueue()
    key = "123456"
    bot_msg = _make_private_message(message_id=1, text="[语音消息:天气]")
    bot_msg.user_id = 12345
    queue.push(key, bot_msg)

    assert orch._last_user_text(queue, key) == "[语音消息:天气]"


def test_last_user_text_uses_queue_bot_account_first():
    """queue.bot_account（bootstrap 注入）优先于 config.bot.account 使用：
    即使 config 中 bot.account 畸形（"your_qq"），只要队列注入过 account 就仍能过滤 bot 自推消息。"""
    bot = _FakeBot()
    bot.account = "your_qq"
    config = _FakeConfig()
    config.bot = bot
    orch = _make_orchestrator(config=config)
    queue = MessageQueue(bot_account=12345)
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="用户问天气"))
    bot_msg = _make_private_message(message_id=2, text="[语音消息:天气]")
    bot_msg.user_id = 12345
    queue.push(key, bot_msg)

    assert orch._last_user_text(queue, key) == "用户问天气"


def test_render_skills_escapes_xml_fully():
    """_render_skills 必须完整转义 XML 特殊字符（& < > \" '），防止注入破坏 XML 结构。"""

    class _Skill:
        qualified_name = "p:weather&<"
        name = "weather"
        description = "说\"好\"<a> & '引'"

    text = ReplyOrchestrator._render_skills([_Skill()])

    assert "&amp;" in text
    assert "&lt;" in text
    assert "&gt;" in text
    assert "&quot;" in text
    assert "&apos;" in text
    assert text.count("<skill") == 1
    assert "&<" not in text


def test_match_markdown_skills_limits_to_three():
    """_match_markdown_skills 最多注入 3 个相关技能，与文档「最多 3 个相关技能」一致。"""
    calls: list[tuple[str, int]] = []

    class _FakeRegistry:
        def match(self, query: str, limit: int = 0):
            calls.append((query, limit))
            return ["s1", "s2", "s3", "s4"]

    orch = _make_orchestrator()
    orch._markdown_skills = _FakeRegistry()
    queue = MessageQueue()
    key = "123456"
    queue.push(key, _make_private_message(message_id=1, text="天气"))

    matched = orch._match_markdown_skills(queue, key)

    assert calls == [("天气", 3)]
    assert len(matched) == 4  # 截断由注册表 match 完成，此处仅透传 limit=3


def test_estimate_tokens_scales_with_message_length():
    """_estimate_tokens 必须随消息体字符数增长（约 1 字符 ≈ 1.33 token）。"""
    short = ReplyOrchestrator._estimate_tokens([{"role": "user", "content": "短"}])
    long_ = ReplyOrchestrator._estimate_tokens(
        [{"role": "user", "content": "长" * 300}]
    )
    assert long_ > short
    assert long_ >= 300


# ── allowed-tools 传递 ───────────────────────────────────────────


class _AllowedSkill:
    qualified_name = "p:weather"
    name = "weather"
    description = "天气"
    allowed_tools = ("skills__read_manifest", "agents__delegate")


class _AllowedSkill2:
    qualified_name = "p:calc"
    name = "calc"
    description = "计算"
    allowed_tools = ("demo__ping",)


class _NoAllowedSkill:
    qualified_name = "p:math"
    name = "math"
    description = "数学"
    allowed_tools = ()


class _MissingAllowedSkill:
    qualified_name = "p:math"
    name = "math"
    description = "数学"
    # 未声明 allowed_tools 属性（等同未声明）


class _FakeMarkdownSkills:
    def __init__(self, matched: list) -> None:
        self._matched = matched

    def match(self, query: str, limit: int = 0):
        return list(self._matched)


async def _run_agent_turn(orch: ReplyOrchestrator, queue: MessageQueue, queue_key: str):
    queue.push(queue_key, _make_private_message(message_id=1, text="今天天气怎么样"))
    event = orch.start_reply(
        message=_make_private_message(message_id=2),
        queue=queue,
        queue_key=queue_key,
        decision=_make_decision(),
    )
    assert event is not None
    for _ in range(300):
        if not orch._active_pipelines:
            break
        await asyncio.sleep(0.1)
    return event


async def test_agent_mode_all_skills_declare_allowed_tools_passes_union(monkeypatch):
    """所有命中技能都声明了非空 allowed-tools 时，并集传给 build_reply_toolset，
    提示词追加与实际限制一致的限制说明。"""
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset
    from neobot_app.reply.tools import ReplyToolExecutor

    captured: dict = {}

    def fake_build_reply_toolset(**kwargs):
        captured.update(kwargs)
        executor = ReplyToolExecutor(send_reply_handler=kwargs["send_reply_handler"])
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", fake_build_reply_toolset)

    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills([_AllowedSkill(), _AllowedSkill2()])
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    assert captured.get("allowed_tools") == {
        "skills__read_manifest",
        "agents__delegate",
        "demo__ping",
    }
    chat_context = captured["chat_context"]
    assert "限制了可用工具" in chat_context
    assert "仅允许：agents__delegate, demo__ping, skills__read_manifest" in chat_context
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_agent_mode_one_skill_without_allowed_tools_disables_restriction(
    monkeypatch,
):
    """一个命中技能声明了 allowed-tools、另一个声明为空时，本轮不启用限制：
    allowed_tools 传 None，提示词无限制说明（未声明技能的工具不得被误伤）。"""
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset
    from neobot_app.reply.tools import ReplyToolExecutor

    captured: dict = {}

    def fake_build_reply_toolset(**kwargs):
        captured.update(kwargs)
        executor = ReplyToolExecutor(send_reply_handler=kwargs["send_reply_handler"])
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", fake_build_reply_toolset)

    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills([_AllowedSkill(), _NoAllowedSkill()])
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    assert captured.get("allowed_tools") is None
    assert "限制了可用工具" not in captured["chat_context"]
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_agent_mode_one_skill_without_allowed_tools_attribute_disables_restriction(
    monkeypatch,
):
    """一个命中技能未声明 allowed_tools 属性（等同未声明）时同样不启用限制。"""
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset
    from neobot_app.reply.tools import ReplyToolExecutor

    captured: dict = {}

    def fake_build_reply_toolset(**kwargs):
        captured.update(kwargs)
        executor = ReplyToolExecutor(send_reply_handler=kwargs["send_reply_handler"])
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", fake_build_reply_toolset)

    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills(
        [_AllowedSkill(), _MissingAllowedSkill()]
    )
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    assert captured.get("allowed_tools") is None
    assert "限制了可用工具" not in captured["chat_context"]
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_agent_mode_no_allowed_tools_passes_none(monkeypatch):
    """命中技能无 allowed_tools 时不限制：build_reply_toolset 收到 None，提示词无限制说明。"""
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset
    from neobot_app.reply.tools import ReplyToolExecutor

    captured: dict = {}

    def fake_build_reply_toolset(**kwargs):
        captured.update(kwargs)
        executor = ReplyToolExecutor(send_reply_handler=kwargs["send_reply_handler"])
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", fake_build_reply_toolset)

    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills([_NoAllowedSkill()])
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    assert captured.get("allowed_tools") is None
    assert "限制了可用工具" not in captured["chat_context"]
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


# ── allowed-tools 下表情包搜索提示一致性 ──────────────────────────


class _FakeEmojiService:
    """假表情包服务：图库数量超过分页上限（50）时触发搜索提示。"""

    def __init__(self, count: int = 200) -> None:
        self.emoji_count = count

    def build_prompt_text(self, limit: int = 50) -> str:
        limit = limit or 50  # _FakeChat.__getattr__ 缺失配置属性返回 None
        return "\n".join(f"#{i}" for i in range(1, min(self.emoji_count, limit) + 1))

    def get_entry(self, number: int):
        return None

    async def record_usage(self, number: int) -> None:
        pass


def _capture_toolset_build(monkeypatch) -> dict:
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset
    from neobot_app.reply.tools import ReplyToolExecutor

    captured: dict = {}

    def fake_build_reply_toolset(**kwargs):
        captured.update(kwargs)
        executor = ReplyToolExecutor(send_reply_handler=kwargs["send_reply_handler"])
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", fake_build_reply_toolset)
    return captured


async def test_agent_mode_allowed_tools_omits_search_custom_emoji_hint(monkeypatch):
    """限制激活时提示词省略 search_custom_emoji 搜索提示（该工具已被 definitions
    过滤），表情包段其余内容与限制说明保留。"""
    captured = _capture_toolset_build(monkeypatch)
    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills([_AllowedSkill()])
    orch._config.chat.emoji_page_size = 50  # 假配置缺失属性返回 None，需显式给定
    orch._emoji_service = _FakeEmojiService(count=200)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    chat_context = captured["chat_context"]
    assert captured.get("allowed_tools") is not None
    assert "<可用的表情包>" in chat_context
    assert "可用 search_custom_emoji 按关键词搜索" not in chat_context
    assert "限制了可用工具" in chat_context
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_agent_mode_no_restriction_keeps_search_custom_emoji_hint(monkeypatch):
    """无限制时提示词保留 search_custom_emoji 搜索提示。"""
    captured = _capture_toolset_build(monkeypatch)
    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    orch._markdown_skills = _FakeMarkdownSkills([_NoAllowedSkill()])
    orch._config.chat.emoji_page_size = 50  # 假配置缺失属性返回 None，需显式给定
    orch._emoji_service = _FakeEmojiService(count=200)
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)

    event = await _run_agent_turn(orch, queue, "123456")

    chat_context = captured["chat_context"]
    assert captured.get("allowed_tools") is None
    assert "可用 search_custom_emoji 按关键词搜索" in chat_context
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_disallowed_tool_is_rejected_before_consuming_before_hook(monkeypatch):
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _ConsumeToolHook:
        def __init__(self) -> None:
            self.before_tool_calls = 0

        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "tool.call.before":
                self.before_tool_calls += 1
                envelope.consume("hook bypassed authorization")
            return envelope

    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-forged",
                        "type": "function",
                        "function": {
                            "name": "poke_user",
                            "arguments": '{"user_id": 1}',
                        },
                    }
                ],
            },
            {"content": "收到", "tool_calls": []},
        ]
    )
    events = _ConsumeToolHook()
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        runtime_events=events,
    )
    orch._markdown_skills = _FakeMarkdownSkills([_AllowedSkill()])
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = await _run_agent_turn(orch, queue, "123456")
    tool_messages = [m for m in provider.calls[1][0] if m.get("role") == "tool"]

    assert events.before_tool_calls == 0
    assert any("不在当前技能允许的工具列表内" in m["content"] for m in tool_messages)
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_tool_after_hook_result_is_finally_capped_and_logs_redact_args(
    monkeypatch,
):
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _AfterHook:
        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "tool.call.after":
                envelope.payload["tool_result"] = "result-secret-" + "x" * 30000
            return envelope

    class _Logger:
        def __init__(self) -> None:
            self.records: list[tuple[tuple, dict]] = []

        def __getattr__(self, name):
            def record(*args, **kwargs):
                self.records.append((args, kwargs))

            return record

    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-cap",
                        "type": "function",
                        "function": {
                            "name": "split_reply",
                            "arguments": json.dumps(
                                {
                                    "text": "ok",
                                    "api_key": "model-secret",
                                    "_delegate_context": "full-private-context",
                                }
                            ),
                        },
                    }
                ],
            },
            {"content": "收到", "tool_calls": []},
        ]
    )
    logger = _Logger()
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        runtime_events=_AfterHook(),
        logger=logger,
    )
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = await _run_agent_turn(orch, queue, "123456")
    tool_message = next(m for m in provider.calls[1][0] if m.get("role") == "tool")
    logged = repr(logger.records)

    assert len(tool_message["content"]) <= 16400
    assert tool_message["content"].endswith("...[truncated]")
    assert "model-secret" not in logged
    assert "full-private-context" not in logged
    assert "<redacted>" in logged
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


# ── 工具参数/结果脱敏 ────────────────────────────────────────────


@pytest.mark.parametrize(
    "key",
    [
        "passwd",
        "credential",
        "access_key",
        "private_key",
        "bearer",
        "api_key",
        "password",
        "secret",
        "token",
        "authorization",
        "cookie",
        "client_secret",
    ],
)
def test_safe_tool_args_redacts_sensitive_keys(key: str):
    out = _safe_tool_args({key: "super-secret-value", "text": "hello"})
    assert "super-secret-value" not in out
    assert "<redacted>" in out
    assert "hello" in out


def test_safe_tool_args_keeps_innocuous_keys_and_types():
    out = _safe_tool_args({"keyword": "猫", "text": "hi", "number": 3, "flag": True})
    assert "猫" in out
    assert "hi" in out
    assert "3" in out
    assert "flag" in out


def test_safe_tool_args_drops_delegate_context_and_bounds_values():
    out = _safe_tool_args({"_delegate_context": "secret-context", "text": "x" * 10000})
    assert "secret-context" not in out
    assert len(out) <= 2048 + 32


def test_redacted_tool_text_redacts_nested_keys_and_keeps_others():
    text = _redacted_tool_text(
        json.dumps({"ok": True, "data": {"api_key": "sek", "name": "n"}}), 4096
    )
    assert "sek" not in text
    assert "<redacted>" in text
    assert "n" in text


def test_redacted_tool_text_leaves_plain_strings_capped_only():
    text = _redacted_tool_text("x" * 5000, 2048)
    assert len(text) <= 2048 + 32
    assert "x" in text


def test_redacted_tool_text_parses_large_json_before_truncation():
    """超过日志上限的 JSON 必须先完整解析脱敏再截断，敏感值不得泄漏。"""
    payload = {
        "ok": True,
        "data": {"api_key": "deep-secret", "items": ["x" * 2000]},
    }
    text = _redacted_tool_text(json.dumps(payload), 2048)
    assert "deep-secret" not in text
    assert "<redacted>" in text


def test_redacted_tool_text_scrubs_bearer_and_token_values():
    """字符串值内嵌的 Bearer/token= 形态密钥必须被值级清洗。"""
    text = _redacted_tool_text(
        json.dumps({"error": "unauthorized: Bearer sk-1234567890 token=abc"}), 4096
    )
    assert "sk-1234567890" not in text
    assert "token=abc" not in text
    assert "Bearer <redacted>" in text


def test_safe_tool_args_scrubs_secret_patterns_in_values():
    out = _safe_tool_args(
        {"url": "https://x.example?token=abc123", "text": "Bearer sk-xyz"}
    )
    assert "abc123" not in out
    assert "sk-xyz" not in out
    assert "<redacted>" in out


async def test_tool_after_event_payload_args_are_redacted(monkeypatch):
    """tool.call.after 事件参数必须已脱敏，不得携带原始密钥/上下文。"""
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _Hook:
        def __init__(self) -> None:
            self.after_args: object = None

        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "tool.call.after":
                self.after_args = envelope.payload.get("tool_args")
            return envelope

    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-after",
                        "type": "function",
                        "function": {
                            "name": "split_reply",
                            "arguments": json.dumps(
                                {
                                    "text": "ok",
                                    "api_key": "model-secret",
                                    "_delegate_context": "ctx-secret",
                                }
                            ),
                        },
                    }
                ],
            },
            {"content": "收到", "tool_calls": []},
        ]
    )
    hook = _Hook()
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        runtime_events=hook,
    )
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = await _run_agent_turn(orch, queue, "123456")

    assert hook.after_args is not None
    assert "model-secret" not in str(hook.after_args)
    assert "ctx-secret" not in str(hook.after_args)
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


def test_redacted_tool_text_handles_oversized_camel_case_json_key():
    payload = json.dumps(
        {
            "apiKey": "camel-secret-value",
            "padding": "x" * 20000,
        }
    )

    text = _redacted_tool_text(payload, 4096)

    assert "camel-secret-value" not in text
    assert "<redacted>" in text


def test_safe_tool_args_avoids_sensitive_key_substring_false_positives():
    out = _safe_tool_args(
        {
            "token_count": 3,
            "authentication_method": "oauth",
            "cookie_policy": "strict",
        }
    )

    assert "token_count" in out
    assert "authentication_method" in out
    assert "cookie_policy" in out
    assert "<redacted>" not in out


def test_safe_tool_args_scrubs_non_dict_values():
    out = _safe_tool_args("request failed: Bearer top-secret-token")

    assert "top-secret-token" not in out
    assert "<redacted>" in out


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"x": 1}, {"x": 1}),
        (None, {}),
        ("null", {}),
        ("[]", {}),
        ([{"x": 1}], {}),
        ('{"x": 1}', {"x": 1}),
    ],
)
def test_parse_tool_args_normalizes_dict_null_and_non_dict(raw, expected):
    assert _parse_tool_args(raw) == expected


async def test_shutdown_closes_tracked_reply_tool_executor_after_pipeline(
    monkeypatch,
):
    import neobot_app.reply.tools as tools_module
    from neobot_chat.tools.toolset import Toolset

    class _Executor:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

        def definitions(self) -> list:
            return []

    executor = _Executor()

    def _build_toolset(**kwargs):
        return Toolset(executor=executor, specs=[])

    monkeypatch.setattr(tools_module, "build_reply_toolset", _build_toolset)
    orch = _make_orchestrator(
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}])
    )
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    await _run_agent_turn(orch, queue, "123456")

    assert executor.close_calls == 0
    await orch.shutdown()
    assert executor.close_calls == 1


async def test_shutdown_guard_rejects_new_foreground_and_background_replies():
    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    orch._friend_queue = queue

    await orch.shutdown()

    foreground = orch.start_reply(
        message=_make_private_message(),
        queue=queue,
        queue_key="123456",
        decision=_make_decision(),
    )
    background = orch.start_background_reply(
        kind="private",
        conversation_id="123456",
        content="late notification",
    )
    assert foreground is None
    assert background is None
    assert not orch._tasks


async def test_shutdown_continues_when_manager_surfaces_cancelled_error():
    class _CancelledManager:
        async def shutdown(self) -> None:
            raise asyncio.CancelledError

    class _Provider:
        def __init__(self) -> None:
            self.close_calls = 0

        async def close(self) -> None:
            self.close_calls += 1

    provider = _Provider()
    scheduled = AsyncMock()
    orch = _make_orchestrator(provider=provider)
    orch._drawing_manager = _CancelledManager()
    orch._scheduled_task_manager = SimpleNamespace(shutdown=scheduled)

    await orch.shutdown()

    scheduled.assert_awaited_once()
    assert provider.close_calls == 1


class _CommonChat(_FakeChat):
    reply_mode = "common"
    random_sticker_probability = 0.0


class _CommonConfig:
    chat = _CommonChat()
    bot = _FakeBot()


async def _wait_until_idle(orch: ReplyOrchestrator) -> None:
    for _ in range(200):
        if not orch._active_pipelines:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("reply pipeline did not finish")


async def test_common_mode_applies_post_reply_hook_once():
    provider = _ScriptedProvider([{"content": "hello", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider, config=_CommonConfig())
    hook_calls = 0

    async def _post_hook(event, text):
        nonlocal hook_calls
        hook_calls += 1
        return f"{text}!"

    orch.register_post_reply_hook(_post_hook)
    event = orch.start_reply(
        message=_make_group_message(),
        queue=MessageQueue(),
        queue_key="888888",
        decision=_make_decision(),
    )
    assert event is not None

    await _wait_until_idle(orch)

    assert hook_calls == 1
    await orch.shutdown()


async def test_private_prompt_rewrite_and_common_background_content_are_used():
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _PromptRewrite:
        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "prompt.build.after":
                envelope.payload["prompt"] = "rewritten private prompt"
            return envelope

    provider = _ScriptedProvider([{"content": "hello", "tool_calls": []}])
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_CommonConfig(),
        runtime_events=_PromptRewrite(),
    )
    event = orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
        background_content="background payload",
    )
    assert event is not None

    await _wait_until_idle(orch)

    messages = provider.calls[0][0]
    assert messages[0] == {
        "role": "system",
        "content": "rewritten private prompt",
    }
    assert {"role": "user", "content": "background payload"} in messages
    await orch.shutdown()


async def test_reply_decide_before_consume_cancels_without_model_call():
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _ConsumeDecision:
        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "reply.decide.before":
                envelope.consume("blocked")
            return envelope

    provider = _ScriptedProvider([{"content": "must not run", "tool_calls": []}])
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_CommonConfig(),
        runtime_events=_ConsumeDecision(),
    )
    event = orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
    )
    assert event is not None

    await _wait_until_idle(orch)

    assert event.state.name == "CANCELLED"
    assert provider.calls == []
    await orch.shutdown()


async def test_tool_before_rewrite_updates_execution_and_redacted_after_args(
    monkeypatch,
):
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _RewriteTool:
        def __init__(self) -> None:
            self.after_args = None

        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "tool.call.before":
                envelope.payload["tool_args"] = {
                    "text": "rewritten text",
                    "clientSecret": "hook-secret",
                }
            elif envelope.stage == "tool.call.after":
                self.after_args = envelope.payload.get("tool_args")
            return envelope

    hook = _RewriteTool()
    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "rewrite",
                        "type": "function",
                        "function": {
                            "name": "split_reply",
                            "arguments": {"text": "original text"},
                        },
                    }
                ],
            },
            {"content": "done", "tool_calls": []},
        ]
    )
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        runtime_events=hook,
    )
    queue = MessageQueue()

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = await _run_agent_turn(orch, queue, "123456")
    tool_message = next(m for m in provider.calls[1][0] if m.get("role") == "tool")

    assert "rewritten text" in tool_message["content"]
    assert "rewritten text" in str(hook.after_args)
    assert "hook-secret" not in str(hook.after_args)
    assert "<redacted>" in str(hook.after_args)
    assert event.state.name == "COMPLETED"
    await orch.shutdown()


async def test_cancelled_group_event_cannot_resume_to_completed(monkeypatch):
    class _LifespanChat(_FakeChat):
        group_chat_reply_lifespan = 2
        random_sticker_probability = 0.0

    class _LifespanConfig:
        chat = _LifespanChat()
        bot = _FakeBot()

    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "cancel",
                        "type": "function",
                        "function": {"name": "cancel", "arguments": None},
                    }
                ],
            },
            {"content": "late reply", "tool_calls": []},
        ]
    )
    orch = _make_orchestrator(provider=provider, config=_LifespanConfig())
    suspend_calls = 0

    async def _suspend(source, snapshot, queue_key):
        nonlocal suspend_calls
        suspend_calls += 1
        return [], "resume", None

    monkeypatch.setattr(orch, "_suspend_group_chat", _suspend)
    event = orch.start_reply(
        message=_make_group_message(),
        queue=MessageQueue(),
        queue_key="888888",
        decision=_make_decision(),
    )
    assert event is not None

    await _wait_until_idle(orch)

    assert event.state.name == "CANCELLED"
    assert suspend_calls == 0
    assert len(provider.calls) == 1
    await orch.shutdown()


async def test_silent_heartbeat_is_restored_after_early_hook_return():
    from neobot_app.reply.event import ReplyEvent
    from neobot_chat.runtime.agent import SILENT_HEARTBEAT

    orch = _make_orchestrator(provider=_HangingProvider())
    queue = MessageQueue()
    message = _make_private_message()
    event = ReplyEvent(
        mode="agent",
        message=message,
        conversation_ref=orch._build_conversation_ref(message, "123456"),
        willing_decision=_make_decision(),
    )

    async def _pre_hook(_event):
        return "short circuit"

    orch.register_pre_reply_hook(_pre_hook)

    def sentinel() -> None:
        pass

    token = SILENT_HEARTBEAT.set(sentinel)
    try:
        await orch._run_agent_mode(event, queue, "123456")
        assert SILENT_HEARTBEAT.get() is sentinel
    finally:
        SILENT_HEARTBEAT.reset(token)
        await orch.shutdown()


async def test_silent_heartbeat_is_restored_after_agent_exception():
    from neobot_app.reply.event import ReplyEvent
    from neobot_chat.runtime.agent import SILENT_HEARTBEAT

    class _FailingProvider:
        async def chat(self, messages, tools=None):
            raise RuntimeError("provider exploded")

        async def close(self):
            pass

    orch = _make_orchestrator(provider=_FailingProvider())
    queue = MessageQueue()
    message = _make_private_message()
    event = ReplyEvent(
        mode="agent",
        message=message,
        conversation_ref=orch._build_conversation_ref(message, "123456"),
        willing_decision=_make_decision(),
    )

    def sentinel() -> None:
        pass

    token = SILENT_HEARTBEAT.set(sentinel)
    try:
        with pytest.raises(RuntimeError, match="provider exploded"):
            await orch._run_agent_mode(event, queue, "123456")
        assert SILENT_HEARTBEAT.get() is sentinel
    finally:
        SILENT_HEARTBEAT.reset(token)
        await orch.shutdown()


async def test_tool_timeout_emits_after_event_with_safe_diagnostics(
    monkeypatch,
):
    import neobot_app.reply.tools as tools_module
    from neobot_contracts.ports.runtime_event import RuntimeEnvelope

    class _TimeoutExecutor:
        async def execute(self, name, args):
            await asyncio.Event().wait()

        async def close(self):
            pass

        def is_tool_authorized(self, name):
            return True

        def authorization_error(self, name):
            return "unauthorized"

    class _Toolset:
        def __init__(self) -> None:
            self.executor = _TimeoutExecutor()

        def definitions(self):
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "slow_tool",
                        "description": "slow",
                        "parameters": {"type": "object"},
                    },
                }
            ]

    class _Events:
        def __init__(self) -> None:
            self.timeouts: list[dict] = []

        async def dispatch_envelope(self, envelope: RuntimeEnvelope) -> RuntimeEnvelope:
            if envelope.stage == "tool.call.after" and envelope.payload.get(
                "timed_out"
            ):
                self.timeouts.append(dict(envelope.payload))
            return envelope

    monkeypatch.setattr(
        tools_module,
        "build_reply_toolset",
        lambda **kwargs: _Toolset(),
    )
    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "slow",
                        "type": "function",
                        "function": {
                            "name": "slow_tool",
                            "arguments": {
                                "value": "visible",
                                "apiToken": "timeout-secret",
                            },
                        },
                    }
                ],
            },
            {"content": "done", "tool_calls": []},
        ]
    )
    events = _Events()
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_FakeConfig(),
        runtime_events=events,
    )
    monkeypatch.setattr(orch, "_get_dependency_timeout_seconds", lambda: 0.01)
    monkeypatch.setattr(orch, "_get_model_response_timeout_seconds", lambda event: 0.01)

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = await _run_agent_turn(orch, MessageQueue(), "123456")

    assert event.state.name == "COMPLETED"
    assert len(events.timeouts) == 1
    safe_args = str(events.timeouts[0]["tool_args"])
    assert "visible" in safe_args
    assert "timeout-secret" not in safe_args
    assert "<redacted>" in safe_args
    await orch.shutdown()

# ── 成本计算管线(字符级缓存命中) ───────────────────────────────


class _CostFakeChat(_FakeChat):
    cost_pipeline_enabled = True
    cost_pipeline_threshold = 20


class _CostFakeConfig(_FakeConfig):
    chat = _CostFakeChat()


def _cost_orchestrator(*, calculator=None):
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=_ScriptedProvider([{"content": "收到", "tool_calls": []}]),
        config=_CostFakeConfig(),
        cache_calculator=calculator,
    )
    return orch


async def test_cost_pipeline_gating_and_defaults():
    """成本管线开启判定与阈值读取。"""
    orch = _cost_orchestrator(calculator=__import__("neobot_app.cache", fromlist=["CacheCalculator"]).CacheCalculator())
    assert orch._cost_pipeline_enabled() is True
    assert orch._get_cost_pipeline_threshold() == 20

    # 未配置计算器 -> 不启用
    orch2 = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        config=_CostFakeConfig(),
        cache_calculator=None,
    )
    assert orch2._cost_pipeline_enabled() is False

    # 默认配置(未显式开启) -> 不启用
    orch3 = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        config=_FakeConfig(),
        cache_calculator=__import__("neobot_app.cache", fromlist=["CacheCalculator"]).CacheCalculator(),
    )
    assert orch3._cost_pipeline_enabled() is False
    await orch.shutdown()
    await orch2.shutdown()
    await orch3.shutdown()


async def test_cache_continue_cheaper_decision():
    """缓存命中后继续成本低于重启成本 -> 可续用;无命中/开关关闭 -> 不续用。"""
    from neobot_app.cache import CacheCalculator, serialize_messages

    calc = CacheCalculator(price_difference=120)
    orch = _cost_orchestrator(calculator=calc)
    provider_key = orch._provider_cache_key()  # 无 model 属性的桩 provider -> "chat"

    base = [
        {"role": "system", "content": "你是一位乐于助人的助手" * 5},
        {"role": "user", "content": "中国的首都是哪里？"},
    ]
    continuation = base + [
        {"role": "assistant", "content": "中国的首都是北京。"},
        {"role": "user", "content": "美国的首都是哪里？"},
    ]
    # 先记录一次请求(模拟上一轮调用)
    calc.record(provider_key, serialize_messages(base), output_text="中国的首都是北京。")
    # 续用输入能完整命中上次请求前缀 -> 继续更便宜
    assert orch._cache_continue_cheaper_than_restart(continuation) is True
    # 全新输入无命中 -> 不续用(与不启用时行为一致)
    fresh = [{"role": "user", "content": "全新话题" * 40}]
    assert orch._cache_continue_cheaper_than_restart(fresh) is False
    # 关闭成本管线 -> 不续用(用独立实例,避免污染共享的类属性)
    orch._config.chat = _CostFakeChat()
    orch._config.chat.cost_pipeline_enabled = False
    assert orch._cache_continue_cheaper_than_restart(continuation) is False
    await orch.shutdown()


async def test_cache_continue_cheaper_without_calculator():
    """未注入计算器时,续用决策恒为 False(不改变既有寿命行为)。"""
    orch = _cost_orchestrator(calculator=None)
    assert orch._cache_continue_cheaper_than_restart(
        [{"role": "user", "content": "任何内容" * 30}]
    ) is False
    await orch.shutdown()


async def test_cost_pipeline_extends_group_lifespan(monkeypatch):
    """成本管线开启时,基础寿命(1)耗尽后因缓存命中续用,总回复次数 = 1+阈值(2)=3。"""
    from neobot_app.cache import CacheCalculator

    class _LifespanChat(_FakeChat):
        group_chat_reply_lifespan = 1
        cost_pipeline_enabled = True
        cost_pipeline_threshold = 2
        random_sticker_probability = 0.0

    class _LifespanConfig(_FakeConfig):
        chat = _LifespanChat()

    provider = _ScriptedProvider(
        [
            {"content": "回复1", "tool_calls": []},
            {"content": "回复2", "tool_calls": []},
            {"content": "回复3", "tool_calls": []},
            {"content": "回复4", "tool_calls": []},
        ]
    )
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_LifespanConfig(),
        cache_calculator=CacheCalculator(),
    )
    suspend_calls = 0

    async def _suspend(source, snapshot, queue_key):
        nonlocal suspend_calls
        suspend_calls += 1
        return [], "resume", None  # 后台通知保持管线存活

    monkeypatch.setattr(orch, "_suspend_group_chat", _suspend)
    event = orch.start_reply(
        message=_make_group_message(),
        queue=MessageQueue(),
        queue_key="888888",
        decision=_make_decision(),
    )
    assert event is not None
    await _wait_until_idle(orch)

    # 基础寿命 1 + 阈值 2 = 3 次回复;第 4 条脚本未被消费
    assert len(provider.calls) == 3, provider.calls
    assert suspend_calls == 2
    await orch.shutdown()


async def test_cost_pipeline_disabled_keeps_base_lifespan(monkeypatch):
    """成本管线关闭(或未命中缓存)时,管线在基础寿命后正常结束。"""
    from neobot_app.cache import CacheCalculator

    class _LifespanChat(_FakeChat):
        group_chat_reply_lifespan = 1
        cost_pipeline_enabled = False
        random_sticker_probability = 0.0

    class _LifespanConfig(_FakeConfig):
        chat = _LifespanChat()

    provider = _ScriptedProvider(
        [
            {"content": "回复1", "tool_calls": []},
            {"content": "回复2", "tool_calls": []},
        ]
    )
    orch = ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=_LifespanConfig(),
        cache_calculator=CacheCalculator(),
    )

    async def _suspend(source, snapshot, queue_key):
        return [], "resume", None

    monkeypatch.setattr(orch, "_suspend_group_chat", _suspend)
    event = orch.start_reply(
        message=_make_group_message(),
        queue=MessageQueue(),
        queue_key="888888",
        decision=_make_decision(),
    )
    assert event is not None
    await _wait_until_idle(orch)

    # 基础寿命 1 耗尽后直接结束,不再调用挂起
    assert len(provider.calls) == 1, provider.calls
    await orch.shutdown()


@pytest.mark.parametrize("degrade", [False, True])
async def test_native_vision_tool_images_and_live_fallback(monkeypatch, degrade):
    """Real skill/executor path: images survive bounding and follow the complete tool batch."""
    import base64
    from io import BytesIO
    from PIL import Image
    from neobot_app.skills.base import SkillManager
    from neobot_app.skills.image_context_skill import ImageContextSkill
    from neobot_app.skills.image_parse_skill import ImageParseSkill

    buffer = BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()

    class VisionProvider(_ScriptedProvider):
        native_vision = True
        vision_degradation = None

        async def chat(self, messages, tools=None):
            if degrade and len(self.calls) == 1:
                self.native_vision = False
                self.vision_degradation = {"reason": "This model does not support image"}
            return await super().chat(messages, tools=tools)

    first = {
        "role": "assistant", "content": "", "tool_calls": [
            {"id": f"image-{i}", "type": "function", "function": {
                "name": "image_context__add_image",
                "arguments": json.dumps({"image_base64": encoded}),
            }} for i in range(2)
        ],
    }
    responses = [first, {"role": "assistant", "content": "未看到图" if degrade else "红色", "tool_calls": []}]
    if degrade:
        responses.append({"role": "assistant", "content": "已回退", "tool_calls": []})
    provider = VisionProvider(responses)
    skills = SkillManager()
    skills.register(ImageContextSkill())
    skills.register(ImageParseSkill(vision_provider=object()))
    orch = _make_orchestrator(provider=provider)
    orch._skill_manager = skills

    no_suspend = AsyncMock(return_value=([], None))
    monkeypatch.setattr(orch, "_suspend_private_chat", no_suspend)
    monkeypatch.setattr(orch, "_get_private_chat_max_tokens", lambda: 7000)
    event = orch.start_reply(
        message=_make_private_message(), queue=MessageQueue(),
        queue_key="123456", decision=_make_decision(),
    )
    await _wait_until_idle(orch)
    assert event.error is None
    assert event.generated_text == ("已回退" if degrade else "红色")
    first_tools = {t["function"]["name"] for t in provider.calls[0][1]}
    assert "image_context__add_image" in first_tools
    assert "image_parse__parse_image" not in first_tools
    messages = provider.calls[1][0]
    tool_positions = [i for i, message in enumerate(messages) if message.get("role") == "tool"]
    assert len(tool_positions) == 2
    vision_message = messages[tool_positions[-1] + 1]
    assert vision_message["role"] == "user"
    assert len([p for p in vision_message["content"] if p.get("type") == "image_url"]) == 2
    assert all(encoded not in messages[i]["content"] for i in tool_positions)
    assert all("data:image/" not in messages[i]["content"] for i in tool_positions)
    if not degrade:
        no_suspend.assert_not_awaited()  # image appendix counts toward context lifetime
    if degrade:
        restored = {t["function"]["name"] for t in provider.calls[2][1]}
        assert "image_parse__parse_image" in restored
        assert "image_context__add_image" not in restored
    await orch.shutdown()


async def test_common_native_vision_loads_current_message_without_tools():
    import base64
    from io import BytesIO
    from PIL import Image
    from neobot_app.reply.event import ReplyEvent, ReplyState

    buffer = BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    message = _make_private_message()
    message.message = [MessageSegment(type="image", data={"file": f"base64://{encoded}"})]
    provider = _ScriptedProvider([{"role": "assistant", "content": "蓝色"}])
    provider.native_vision = True
    orch = _make_orchestrator(provider=provider)
    event = ReplyEvent(mode="common", message=message)
    event.transition(ReplyState.BUILDING_PROMPT)
    result = await orch._generate_reply(event, "描述图片")
    assert result == "蓝色"
    messages, tools = provider.calls[0]
    assert tools is None
    assert messages[-1]["role"] == "user"
    assert any(part.get("type") == "image_url" for part in messages[-1]["content"])
    await orch.shutdown()


async def test_vision_fallback_on_final_iteration_gets_one_recovery_turn(monkeypatch):
    class Provider(_ScriptedProvider):
        native_vision = True

        async def chat(self, messages, tools=None):
            self.native_vision = False
            return await super().chat(messages, tools)

    class Config(_FakeConfig):
        class chat(_FakeChat):
            agent_max_iterations = 1

    provider = Provider([
        {"role": "assistant", "content": "尚未看到图", "tool_calls": []},
        {"role": "assistant", "content": "已恢复", "tool_calls": []},
    ])
    orch = _make_orchestrator(provider=provider, config=Config())
    monkeypatch.setattr(orch, "_suspend_private_chat", AsyncMock(return_value=([], None)))
    event = orch.start_reply(message=_make_private_message(), queue=MessageQueue(), queue_key="123456", decision=_make_decision())
    await _wait_until_idle(orch)
    assert event.error is None
    assert event.generated_text == "已恢复"
    assert len(provider.calls) == 2
    await orch.shutdown()


@pytest.mark.parametrize("default_count", [0, 1, 4])
async def test_agent_default_images_are_labelled_only_at_prompt_end(monkeypatch, default_count):
    import base64
    from io import BytesIO
    from PIL import Image

    class PromptBuilder(_FakePromptBuilder):
        async def build_friend_chat_messages(self, **kwargs):
            from neobot_app.prompt.role_messages import build_role_messages

            return build_role_messages(
                kwargs["message_queue"], str(kwargs["user_id"]), numbering=kwargs["numbering"],
            )

    buffer = BytesIO()
    Image.new("RGB", (8, 8), "green").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode()
    queue = MessageQueue()
    for i in range(1, 7):
        message = _make_private_message(message_id=i)
        message.message = [MessageSegment(type="image", data={"file": f"base64://{encoded}"})]
        queue.push("123456", message)
    provider = _ScriptedProvider([{"role": "assistant", "content": "绿色", "tool_calls": []}])
    provider.native_vision = True
    orch = _make_orchestrator(provider=provider, prompt_builder=PromptBuilder())
    monkeypatch.setattr(orch, "_get_native_vision_default_image_count", lambda: default_count)
    monkeypatch.setattr(orch, "_suspend_private_chat", AsyncMock(return_value=([], None)))
    event = orch.start_reply(message=message, queue=queue, queue_key="123456", decision=_make_decision())
    await _wait_until_idle(orch)
    assert event.error is None
    request = provider.calls[0][0]
    text_messages = [m["content"] for m in request if isinstance(m["content"], str)]
    assert sum("[图片]" in content for content in text_messages) == 6
    assert all(encoded not in content for content in text_messages)
    if default_count:
        assert all(isinstance(m["content"], str) for m in request[:-1])
        parts = request[-1]["content"]
        assert sum(p["type"] == "image_url" for p in parts) == default_count
        assert any("消息ID 6" in p.get("text", "") for p in parts)
    else:
        assert all(isinstance(m["content"], str) for m in request)
    await orch.shutdown()

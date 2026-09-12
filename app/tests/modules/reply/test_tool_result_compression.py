"""回复管线的消息装配测试(工具输出压缩 / 时间块 / 原生视觉说明)。

覆盖:
- 重新构建/续用提示词的新一轮开始前,较早的工具返回被压缩,只保留最近 N 条完整;
- 基础回复类工具压缩后只表示"调用成功";
- 其它工具压缩后保留一段结果摘要;
- 压缩幂等,且不会让 assistant.tool_calls 与结果消息失配;
- <当前时间> user 块每次调用前追加一条,保留历史并位于请求末尾;
- 原生视觉说明进 system 提示词(可缓存),不占用对话末尾的位置。
"""

from __future__ import annotations

import asyncio
import json

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import (
    GroupMessage,
    MessageSegment,
    MessageTypeEnum,
    PrivateMessage,
)

from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.store import sync_default_prompts
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.willing.models import WillingDecision


class _Chat:
    """除显式字段外，所有配置属性默认返回 None（触发默认分支）。"""

    reply_mode = "agent"
    random_sticker_probability = 0.0
    group_chat_reply_lifespan = 0
    tool_result_full_keep = 10
    tool_result_summary_chars = 12
    show_last_reply_markers = False

    def __getattr__(self, name: str):
        return None


class _Bot:
    nick_name = "Bot"
    account = 10001
    alias_name = []


class _Config:
    chat = _Chat()
    bot = _Bot()


def _config_with(keep: int, summary_chars: int = 12):
    """构造指定压缩参数的配置对象(keep = 保留完整的最近工具返回条数)。"""

    class _CustomChat(_Chat):
        tool_result_full_keep = keep
        tool_result_summary_chars = summary_chars

    class _CustomConfig:
        chat = _CustomChat()
        bot = _Bot()

    return _CustomConfig()


class _FakePromptBuilder:
    """最小提示词构建器替身:只提供编排器实际调用的接口。"""

    async def build_friend_chat_prompt(self, **kwargs):
        blocks = kwargs.get("context_blocks")
        if blocks is not None:
            blocks.append({"role": "user", "content": "<聊天对象>小明</聊天对象>"})
        return "私聊提示词"

    async def build_group_chat_prompt(self, **kwargs):
        blocks = kwargs.get("context_blocks")
        if blocks is not None:
            blocks.append({"role": "user", "content": "<群友信息>小明</群友信息>"})
        return "群聊提示词"

    async def build_group_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "1: 小明: 你好"}]

    async def build_friend_chat_messages(self, **kwargs):
        return [{"role": "user", "content": "1: 小明: 你好"}]

    def build_current_time_message(self):
        return {"role": "user", "content": "<当前时间>现在的时间是2026-01-01 00:00:00</当前时间>"}


class _ScriptedProvider:
    """按脚本依次返回响应,并记录每次请求的消息列表。"""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[list, object]] = []

    async def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        return self._responses.pop(0)

    async def close(self):
        pass


class _FakeAdapter:
    async def send(self, conversation_ref, payload, wait_response: bool = True):
        return {"status": "ok", "message_id": 2001}

    async def call_api(self, action, params):
        return {"status": "ok"}


def _make_decision() -> WillingDecision:
    return WillingDecision(
        manager_name="test", probability=1.0, should_reply=True, reasons=("测试触发",)
    )


def _make_private_message(message_id: int = 1) -> PrivateMessage:
    return PrivateMessage(
        message_type=MessageTypeEnum.private,
        message_id=message_id,
        user_id=10001,
        message=[MessageSegment(type="text", data={"text": "你好"})],
        raw_message="你好",
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


def _make_orchestrator(
    *, provider=None, config=None, prompt_store=None, flow_registry=None
) -> ReplyOrchestrator:
    return ReplyOrchestrator(
        adapter=_FakeAdapter(),
        prompt_builder=_FakePromptBuilder(),
        provider=provider,
        config=config or _Config(),
        prompt_store=prompt_store,
        flow_registry=flow_registry,
        logger=None,
    )


def _tool_call(call_id: str, name: str, arguments: dict | None = None) -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments or {})},
    }


def _tool_message(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


# ── 压缩语义(单元) ───────────────────────────────────────────


def test_compress_keeps_last_n_full_and_compresses_earlier_results():
    """12 条工具返回、保留 10 条时，只压缩最早 2 条，其余内容逐字不变。"""
    orch = _make_orchestrator()
    messages: list[dict] = [{"role": "user", "content": "开始"}]
    names: dict[str, str] = {}
    originals: dict[str, str] = {}
    for index in range(12):
        call_id = f"c{index}"
        content = f"result-{index}-" + "x" * 80
        names[call_id] = "web_search"
        originals[call_id] = content
        messages.append(_tool_message(call_id, content))

    changed = orch._compress_stale_tool_results(messages, set(), names)

    assert changed == 2
    assert messages[1]["content"].startswith("[已压缩]")
    assert messages[2]["content"].startswith("[已压缩]")
    assert messages[1]["content"] != originals["c0"]
    for index in range(2, 12):
        assert messages[1 + index]["content"] == originals[f"c{index}"]


def test_compress_dedups_by_tool_call_id_and_is_idempotent():
    """已压缩过的 tool_call_id 不会重复处理，消息数量与顺序保持不变。"""
    orch = _make_orchestrator(config=_config_with(keep=2))
    messages: list[dict] = [{"role": "user", "content": "开始"}]
    names: dict[str, str] = {}
    for index in range(5):
        call_id = f"c{index}"
        names[call_id] = "web_search"
        messages.append(_tool_message(call_id, f"result-{index}"))

    compressed: set[str] = set()
    first = orch._compress_stale_tool_results(messages, compressed, names)
    snapshot = [dict(message) for message in messages]
    second = orch._compress_stale_tool_results(messages, compressed, names)

    assert first == 3
    assert second == 0
    assert messages == snapshot


def test_basic_tool_compression_only_reports_success():
    """基础回复类工具(send_reply 等)压缩后只表示调用成功，不再保留结果内容。"""
    orch = _make_orchestrator(config=_config_with(keep=1))
    messages: list[dict] = [{"role": "user", "content": "开始"}]
    names = {"a": "send_reply", "b": "web_search", "c": "web_search"}
    messages.append(_tool_message("a", "已发送 3 条消息:分条内容 A/B/C"))
    messages.append(_tool_message("b", "搜索结果:1. 标题 2. 标题"))
    messages.append(_tool_message("c", "最近的完整结果"))

    changed = orch._compress_stale_tool_results(messages, set(), names)

    assert changed == 2
    assert messages[1]["content"] == "[已压缩] 工具 send_reply 调用成功。"
    assert "分条内容" not in messages[1]["content"]
    assert messages[2]["content"].startswith("[已压缩] 工具 web_search 调用成功。结果摘要:")
    assert "搜索结果" in messages[2]["content"]
    # 最近一条保持完整
    assert messages[3]["content"] == "最近的完整结果"


def test_compression_uses_custom_prompt_templates(tmp_path):
    """压缩文案来自 prompts.toml 分区，用户自定义后必须生效。"""
    sync_default_prompts(tmp_path)
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.write_text(
        '[tool_result_compressed]\ntemplate = "基础工具 {tool_name} OK"\n'
        '[tool_result_compressed_detail]\ntemplate = "工具 {tool_name} 摘要:{summary}"\n',
        encoding="utf-8",
    )
    from neobot_app.prompt.store import PromptStore

    orch = _make_orchestrator(
        config=_config_with(keep=1), prompt_store=PromptStore(tmp_path)
    )
    messages: list[dict] = [
        {"role": "user", "content": "开始"},
        _tool_message("a", "已发送"),
        _tool_message("b", "搜索结果"),
        _tool_message("c", "最近结果"),
    ]

    orch._compress_stale_tool_results(
        messages, set(), {"a": "send_reply", "b": "web_search", "c": "web_search"}
    )

    assert messages[1]["content"] == "基础工具 send_reply OK"
    assert messages[2]["content"] == "工具 web_search 摘要:搜索结果"
    assert messages[3]["content"] == "最近结果"


def test_compression_disabled_when_keep_is_zero():
    """tool_result_full_keep = 0 时全部工具返回都被压缩。"""

    class _NoKeepChat(_Chat):
        tool_result_full_keep = 0

    class _NoKeepConfig:
        chat = _NoKeepChat()
        bot = _Bot()

    orch = _make_orchestrator(config=_NoKeepConfig())
    messages: list[dict] = [{"role": "user", "content": "开始"}]
    names: dict[str, str] = {}
    for index in range(3):
        call_id = f"c{index}"
        names[call_id] = "web_search"
        messages.append(_tool_message(call_id, f"result-{index}"))

    changed = orch._compress_stale_tool_results(messages, set(), names)

    assert changed == 3
    assert all(message["content"].startswith("[已压缩]") for message in messages[1:])


# ── 编排器接线(集成) ─────────────────────────────────────────


async def _wait_until_idle(orch: ReplyOrchestrator) -> None:
    for _ in range(300):
        if not orch._active_pipelines:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("reply pipeline did not finish")


async def test_current_time_block_is_appended_per_model_call(monkeypatch):
    """<当前时间> 块每次调用模型前追加一条并保留历史，且始终是本次请求的最后一条。"""
    provider = _ScriptedProvider(
        [
            {
                "content": "",
                "tool_calls": [_tool_call("t1", "wait", {"seconds": 1})],
            },
            {"content": "回复", "tool_calls": []},
        ]
    )
    orch = _make_orchestrator(provider=provider)

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)

    assert event.error is None
    assert len(provider.calls) == 2

    def _time_blocks(request):
        return [
            message
            for message in request
            if message.get("role") == "user"
            and "<当前时间>" in str(message.get("content"))
        ]

    first_request = provider.calls[0][0]
    assert len(_time_blocks(first_request)) == 1
    assert first_request[-1] is _time_blocks(first_request)[0]

    second_request = provider.calls[1][0]
    blocks = _time_blocks(second_request)
    # 旧的时间块保留在历史里,第二次调用再追加一条
    assert len(blocks) == 2
    assert second_request[-1] is blocks[-1]
    await orch.shutdown()


async def test_context_block_is_injected_right_after_system(monkeypatch):
    """上下文 user 块必须紧跟在 system 之后、聊天记录之前。"""
    provider = _ScriptedProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)

    request = provider.calls[0][0]
    assert request[0]["role"] == "system"
    assert request[1]["role"] == "user"
    assert "<聊天对象>" in request[1]["content"]
    assert request[2]["content"] == "1: 小明: 你好"
    await orch.shutdown()


async def test_tool_results_compressed_only_on_later_rounds(monkeypatch):
    """工具输出压缩只在"重新构建/续用提示词"的后续轮次开始前触发一次。"""
    provider = _ScriptedProvider(
        [
            {"content": "第一轮", "tool_calls": []},
            {"content": "第二轮", "tool_calls": []},
        ]
    )

    class _LifespanChat(_Chat):
        group_chat_reply_lifespan = 2

    class _LifespanConfig:
        chat = _LifespanChat()
        bot = _Bot()

    orch = _make_orchestrator(provider=provider, config=_LifespanConfig())
    calls: list[int] = []
    original = ReplyOrchestrator._compress_stale_tool_results

    def _spy(self, messages, compressed, names, **kwargs):
        calls.append(len(messages))
        return original(self, messages, compressed, names, **kwargs)

    monkeypatch.setattr(ReplyOrchestrator, "_compress_stale_tool_results", _spy)

    suspend_calls = 0

    async def _suspend(source, snapshot, queue_key):
        nonlocal suspend_calls
        suspend_calls += 1
        if suspend_calls > 1:
            return [], None, None
        return [], "续接", None

    monkeypatch.setattr(orch, "_suspend_group_chat", _suspend)
    orch.start_reply(
        message=_make_group_message(),
        queue=MessageQueue(),
        queue_key="888888",
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)

    # 第 1 轮开始前不压缩;进入第 2 轮前压缩一次
    assert len(calls) == 1
    await orch.shutdown()


async def test_flow_registry_receives_prompt_request_and_state(monkeypatch):
    """回复管线必须把 system 提示词、模型请求与活动状态登记到聊天流登记处。"""
    from neobot_app.reply.flow_registry import ChatFlowRegistry

    registry = ChatFlowRegistry()
    provider = _ScriptedProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider, flow_registry=registry)

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)

    flows = registry.list_flows()
    assert [flow["pipeline_key"] for flow in flows] == ["private:123456"]
    assert flows[0]["active"] is False  # 管线结束后必须复位,避免面板显示一直运行中

    snapshot = await registry.snapshot("private:123456")
    assert snapshot is not None
    assert snapshot["system_prompt"] == "私聊提示词"
    roles = [message["role"] for message in snapshot["messages"]]
    assert roles[0] == "system"
    assert "user" in roles
    await orch.shutdown()


async def test_flow_recording_is_optional(monkeypatch):
    """未注入登记处时（默认装配之外）不得影响回复管线。"""
    provider = _ScriptedProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)

    async def _no_suspend(source, snapshot, queue_key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key="123456",
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)

    assert event.error is None
    await orch.shutdown()


class _VisionProvider(_ScriptedProvider):
    """声明支持原生视觉的 provider(说明文字只在此时才会注入)。"""

    native_vision = True


async def _run_once(orch, monkeypatch, *, queue_key: str = "123456"):
    """跑完一轮私聊回复(挂起直接返回空,管线随即结束)。"""

    async def _no_suspend(source, snapshot, key):
        return [], None

    monkeypatch.setattr(orch, "_suspend_private_chat", _no_suspend)
    event = orch.start_reply(
        message=_make_private_message(),
        queue=MessageQueue(),
        queue_key=queue_key,
        decision=_make_decision(),
    )
    await _wait_until_idle(orch)
    return event


async def test_native_vision_note_is_part_of_system_prompt(monkeypatch):
    """原生视觉说明必须追加在 system 提示词里,而不是对话末尾的 user 消息。"""
    provider = _VisionProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)

    event = await _run_once(orch, monkeypatch)

    assert event.error is None
    request = provider.calls[0][0]
    assert request[0]["role"] == "system"
    assert "<原生视觉>" in request[0]["content"]
    # 说明只出现在 system 里:后面的消息不再重复携带
    assert all("<原生视觉>" not in str(m.get("content", "")) for m in request[1:])
    await orch.shutdown()


async def test_native_vision_note_absent_without_native_vision(monkeypatch):
    """不支持原生视觉的 provider 不应该多出这段 token。"""
    provider = _ScriptedProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(provider=provider)

    event = await _run_once(orch, monkeypatch)

    assert event.error is None
    request = provider.calls[0][0]
    assert all("<原生视觉>" not in str(m.get("content", "")) for m in request)
    await orch.shutdown()


async def test_native_vision_note_can_be_disabled(tmp_path, monkeypatch):
    """[native_vision] 写 enabled = false 后不再注入该说明。"""
    from neobot_app.prompt.store import PromptStore, sync_default_prompts

    sync_default_prompts(tmp_path)
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.write_text("[native_vision]\nenabled = false\n", encoding="utf-8")

    provider = _VisionProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(
        provider=provider, prompt_store=PromptStore(tmp_path)
    )

    event = await _run_once(orch, monkeypatch)

    assert event.error is None
    request = provider.calls[0][0]
    assert all("<原生视觉>" not in str(m.get("content", "")) for m in request)
    await orch.shutdown()


async def test_native_vision_note_can_be_customized(tmp_path, monkeypatch):
    """自定义 [native_vision] 模板必须生效,且只注入一次。"""
    from neobot_app.prompt.store import PromptStore, sync_default_prompts

    sync_default_prompts(tmp_path)
    custom = tmp_path / "prompts" / "custom" / "prompts.toml"
    custom.write_text(
        '[native_vision]\ntemplate = "自定义视觉说明"\n', encoding="utf-8"
    )

    provider = _VisionProvider([{"content": "回复", "tool_calls": []}])
    orch = _make_orchestrator(
        provider=provider, prompt_store=PromptStore(tmp_path)
    )

    event = await _run_once(orch, monkeypatch)

    assert event.error is None
    request = provider.calls[0][0]
    assert request[0]["content"].endswith("自定义视觉说明")
    assert "<原生视觉>" not in request[0]["content"]
    await orch.shutdown()


async def test_tool_call_and_result_pairing_survives_compression():
    """压缩只改写内容:assistant 的 tool_calls 与 tool 结果消息仍一一配对。"""
    orch = _make_orchestrator()
    messages: list[dict] = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "开始"},
    ]
    names: dict[str, str] = {}
    for index in range(4):
        call_id = f"c{index}"
        names[call_id] = "web_search"
        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [_tool_call(call_id, "web_search")],
            }
        )
        messages.append(_tool_message(call_id, f"result-{index}"))

    orch._compress_stale_tool_results(messages, set(), names)

    assistant_calls = [
        call["id"]
        for message in messages
        if message.get("role") == "assistant"
        for call in message.get("tool_calls", [])
    ]
    tool_ids = [
        message["tool_call_id"]
        for message in messages
        if message.get("role") == "tool"
    ]
    assert assistant_calls == tool_ids

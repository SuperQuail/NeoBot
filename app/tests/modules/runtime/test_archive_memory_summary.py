"""ArchiveMemoryAutoSummaryService 计数器、摘要失败语义、flush_all 与锁生命周期测试。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from neobot_chat.providers.deepseek_offical import DeepSeekOfficalProvider
from neobot_chat.providers.openai import OpenAIProvider
from neobot_contracts.ports.logging import NullLogger

from neobot_app.runtime.archive_memory_summary import (
    MAX_STORED_MESSAGE_CHARS,
    MAX_TOOL_FAILURES,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOOL_RESULT_TOTAL_CHARS,
    RETRY_BACKOFF_MAX_SECONDS,
    ArchiveMemoryAutoSummaryService,
    _TOOL_DROPPED_MARKER,
    _trim_tool_history,
)
from neobot_app.time_context import epoch_seconds


class _FakeArchive:
    """内存版 ArchiveMemoryService：实现 get/set/list，按 (table, key) 存储。"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, table_name: str, key: str):
        entry = self._items.get((table_name, key))
        if entry is None:
            return None
        return self._to_model(table_name, key, entry)

    async def set(self, table_name: str, key: str, value: str, tags: list[str]):
        self._items[(table_name, key)] = {"value": value, "tags": list(tags)}
        return self._to_model(table_name, key, self._items[(table_name, key)])

    async def list(
        self,
        table_name: str,
        *,
        tags: list[str] | None = None,
        key_query: str | None = None,
        value_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        result = []
        for (table, key), entry in self._items.items():
            if table != table_name:
                continue
            if tags and not any(tag in entry["tags"] for tag in tags):
                continue
            result.append(self._to_model(table_name, key, entry))
        return result[offset : offset + limit]

    def raw(self, table_name: str, key: str) -> dict[str, Any] | None:
        return self._items.get((table_name, key))

    @staticmethod
    def _to_model(table_name: str, key: str, entry: dict[str, Any]):
        from neobot_contracts.models.memory import ArchiveMemory

        return ArchiveMemory(
            id=1,
            table_name=table_name,
            key=key,
            value=entry["value"],
            tags=entry["tags"],
            created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            version=1,
        )


class _FakeProvider:
    """可配置失败行为的假 LLM Provider，记录每次 chat 调用。"""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("provider boom")
        return {"role": "assistant", "content": "ok", "tool_calls": None}

    async def close(self) -> None:
        pass


def _make_config(group_interval: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                trigger=SimpleNamespace(
                    group_interval=group_interval,
                    private_interval=group_interval,
                )
            )
        )
    )


def _make_service(
    archive: _FakeArchive | None = None,
    provider: _FakeProvider | None = None,
    group_interval: int = 3,
) -> ArchiveMemoryAutoSummaryService:
    return ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive or _FakeArchive(),
        provider=provider or _FakeProvider(),
        config=_make_config(group_interval),
    )


@pytest.mark.asyncio
async def test_record_message_increments_counter_and_triggers_at_interval():
    """Arrange 间隔为 3 的群聊服务，Act 逐条 record 三条消息，
    Assert 前两条只累计计数不触发摘要，第三条达到阈值触发一次摘要并复位为 0。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)

    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="  你好，世界  ",
        sender_id="10001",
        sender_name="小弥",
    )
    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="第二条",
    )

    state = json.loads(archive.raw("memory_counter", "group:111")["value"])
    assert state["count"] == 2
    assert state["messages"][0] == {
        "sender_id": "10001",
        "sender_name": "小弥",
        "text": "你好，世界",
    }
    assert len(provider.calls) == 0

    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="第三条",
    )

    assert len(provider.calls) == 1
    state = json.loads(archive.raw("memory_counter", "group:111")["value"])
    assert state == {"count": 0, "messages": []}


@pytest.mark.asyncio
async def test_summary_failure_keeps_counter_for_retry():
    """Arrange provider 必然失败的间隔 3 服务并累计三条消息，Act 触发摘要失败，
    Assert 计数器必须保留 count=3 与全部消息以便后续重试，不得清空丢失。"""
    archive = _FakeArchive()
    provider = _FakeProvider(fail=True)
    service = _make_service(archive=archive, provider=provider, group_interval=3)

    for i in range(3):
        await service.record_message(
            conversation_kind="group",
            conversation_id="222",
            message_text=f"消息 {i}",
        )

    assert len(provider.calls) == 1
    state = json.loads(archive.raw("memory_counter", "group:222")["value"])
    assert state["count"] == 3
    assert len(state["messages"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls", [OpenAIProvider, DeepSeekOfficalProvider], ids=["openai", "deepseek"]
)
@pytest.mark.parametrize(
    "final_fields", [{}, {"tool_calls": None}, {"tool_calls": []}],
    ids=["missing", "null", "empty"],
)
@pytest.mark.parametrize("call_tool_first", [False, True], ids=["immediate", "after-tool"])
async def test_real_provider_no_tool_completion_resets_counter(
    provider_cls, final_fields, call_tool_first
):
    """Tools are optional: a final no-tool HTTP response completes the summary."""
    archive = _FakeArchive()
    logger = Mock(spec=NullLogger)
    executor = AsyncMock(return_value="stored")
    tools = [{
        "type": "function",
        "function": {
            "name": "archive_set",
            "description": "Update an archive record",
            "parameters": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        },
    }]
    arguments = {"value": "Likes Python"}
    tool_call = {
        "id": "archive-call-1",
        "type": "function",
        "function": {"name": "archive_set", "arguments": json.dumps(arguments)},
    }
    responses = []
    if call_tool_first:
        responses.append({
            "message": {"role": "assistant", "content": None, "tool_calls": [tool_call]},
            "finish_reason": "tool_calls",
        })
    responses.append({
        "message": {"role": "assistant", "content": "Done", **final_fields},
        "finish_reason": "stop",
    })
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        assert request.method == "POST"
        assert request.url.path == "/chat/completions"
        assert len(requests) <= len(responses), "HTTP loop continued after completion"
        return httpx.Response(200, json={"choices": [responses[len(requests) - 1]]})

    provider = provider_cls(api_key="test-key", model="test-model")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://archive.test"
    )
    service = ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive,
        provider=provider,
        config=_make_config(group_interval=2),
        logger=logger,
        tool_definitions=tools,
        tool_executor=executor,
    )
    try:
        await service.record_message(
            conversation_kind="group", conversation_id="111", message_text="I like Python"
        )
        assert requests == []
        assert json.loads(archive.raw("memory_counter", "group:111")["value"])["count"] == 1
        await service.record_message(
            conversation_kind="group", conversation_id="111", message_text="Still do"
        )

        assert len(requests) == (2 if call_tool_first else 1)
        assert all(payload["tools"] == tools for payload in requests)
        assert all(payload["tool_choice"] == "auto" for payload in requests)
        assert [message["role"] for message in requests[0]["messages"]] == ["system", "user"]
        if call_tool_first:
            executor.assert_called_once_with("archive_set", arguments)
            executor.assert_awaited_once_with("archive_set", arguments)
            assert requests[1]["messages"][-2]["tool_calls"] == [tool_call]
            assert requests[1]["messages"][-1] == {
                "role": "tool", "tool_call_id": "archive-call-1", "content": "stored"
            }
        else:
            executor.assert_not_called()
        assert json.loads(archive.raw("memory_counter", "group:111")["value"]) == {
            "count": 0, "messages": []
        }
        logger.warning.assert_not_called()
    finally:
        await provider.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_cls", [OpenAIProvider, DeepSeekOfficalProvider], ids=["openai", "deepseek"]
)
async def test_real_provider_http_failure_preserves_counter(provider_cls):
    """A genuine HTTP error must not be mistaken for successful no-tool completion."""
    archive = _FakeArchive()
    logger = Mock(spec=NullLogger)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": "invalid test key"}})

    provider = provider_cls(api_key="test-key", model="test-model")
    provider._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://archive.test"
    )
    service = ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive,
        provider=provider,
        config=_make_config(group_interval=2),
        logger=logger,
    )
    try:
        for text in ("first", "second"):
            await service.record_message(
                conversation_kind="group", conversation_id="222", message_text=text
            )

        assert len(requests) == 1  # Non-retryable HTTP error, not a tool loop.
        state = json.loads(archive.raw("memory_counter", "group:222")["value"])
        assert state["count"] == 2
        assert state["messages"] == [
            {"sender_id": "", "sender_name": "", "text": "first"},
            {"sender_id": "", "sender_name": "", "text": "second"},
        ]
        # 失败必须写入冷却窗口：否则计数器越过阈值后，每条新消息都会重跑一次总结。
        assert state["failures"] == 1
        assert state["retry_after"] > epoch_seconds()
        logger.warning.assert_called_once()
        assert logger.warning.call_args.args == ("档案自动总结失败，进入冷却后重试",)
        assert "401" in logger.warning.call_args.kwargs["error"]
        logger.info.assert_not_called()
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_flush_all_summarizes_partial_counters_and_resets():
    """Arrange 一个未达阈值(2/3)、一个空计数、一个已达标(3/3)和一个畸形 key 的计数器，
    Act 调用 flush_all，Assert 只对部分计数器摘要并复位，其余状态原样保留。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)
    await archive.set(
        "memory_counter",
        "group:111",
        json.dumps({"count": 2, "messages": [{"text": "a"}, {"text": "b"}]}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:222",
        json.dumps({"count": 0, "messages": []}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:333",
        json.dumps({"count": 3, "messages": [{"text": "x"}]}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "nocolon",
        json.dumps({"count": 1, "messages": [{"text": "y"}]}),
        ["auto_summary_counter"],
    )

    await service.flush_all()

    assert len(provider.calls) == 1
    assert json.loads(archive.raw("memory_counter", "group:111")["value"]) == {
        "count": 0,
        "messages": [],
    }
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 0
    assert json.loads(archive.raw("memory_counter", "group:333")["value"])["count"] == 3
    assert json.loads(archive.raw("memory_counter", "nocolon")["value"])["count"] == 1


@pytest.mark.asyncio
async def test_flush_all_skips_counters_without_pending_messages():
    """Arrange 空计数与已达标(3/3)两个计数器，Act 调用 flush_all，
    Assert 不产生任何摘要调用且状态保持不变。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)
    await archive.set(
        "memory_counter",
        "group:111",
        json.dumps({"count": 0, "messages": []}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:222",
        json.dumps({"count": 3, "messages": [{"text": "x"}]}),
        ["auto_summary_counter"],
    )

    await service.flush_all()

    assert len(provider.calls) == 0
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 3


@pytest.mark.asyncio
async def test_flush_all_concurrent_calls_summarize_each_counter_once():
    """Arrange 两个部分计数(3/5)计数器，Act 用 asyncio.gather 并发调用两次 flush_all，
    Assert 每个计数器只被摘要一次，总调用数恰为 2（per-key 锁互斥）。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=5)
    for cid in ("111", "222"):
        await archive.set(
            "memory_counter",
            f"group:{cid}",
            json.dumps(
                {
                    "count": 3,
                    "messages": [{"text": "a"}, {"text": "b"}, {"text": "c"}],
                }
            ),
            ["auto_summary_counter"],
        )

    await asyncio.gather(service.flush_all(), service.flush_all())

    assert len(provider.calls) == 2
    assert json.loads(archive.raw("memory_counter", "group:111")["value"])["count"] == 0
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 0


@pytest.mark.asyncio
async def test_lock_is_released_after_summarize():
    """Arrange 间隔 2 的服务，Act 两条消息触发摘要后再连记两条消息，
    Assert 摘要完成后 per-key 锁已释放且已从注册表回收，后续消息可继续计数并可再次触发。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=2)

    await service.record_message(conversation_kind="group", conversation_id="333", message_text="一")
    await service.record_message(conversation_kind="group", conversation_id="333", message_text="二")

    assert len(provider.calls) == 1
    assert service._locks == {}

    await service.record_message(conversation_kind="group", conversation_id="333", message_text="三")
    assert len(provider.calls) == 1
    await service.record_message(conversation_kind="group", conversation_id="333", message_text="四")
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_locks_registry_is_cleaned_after_summarize():
    """Arrange 三个会话各触发一次摘要，Act 全部完成后检查注册表，
    Assert _locks 中不再残留任何会话锁（防无界增长）。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=2)

    for cid in ("111", "222", "333"):
        await service.record_message(conversation_kind="group", conversation_id=cid, message_text="一")
        await service.record_message(conversation_kind="group", conversation_id=cid, message_text="二")

    assert len(provider.calls) == 3
    assert len(service._locks) == 0


@pytest.mark.asyncio
async def test_record_message_truncates_long_text_to_max_stored_chars():
    """Arrange 一条 2×MAX_STORED_MESSAGE_CHARS 的超长消息，Act record_message，
    Assert 计数器存储的文本被截断到 MAX_STORED_MESSAGE_CHARS。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=10)

    await service.record_message(
        conversation_kind="group",
        conversation_id="444",
        message_text="长" * (MAX_STORED_MESSAGE_CHARS * 2),
    )

    state = json.loads(archive.raw("memory_counter", "group:444")["value"])
    assert len(state["messages"]) == 1
    assert len(state["messages"][0]["text"]) == MAX_STORED_MESSAGE_CHARS


@pytest.mark.asyncio
async def test_record_message_ignores_unknown_conversation_kind():
    """Arrange 合法服务，Act 记录一条未知会话类型（channel）的消息，
    Assert 直接忽略，不产生任何计数状态也不触发摘要。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider)

    await service.record_message(
        conversation_kind="channel",
        conversation_id="555",
        message_text="x",
    )

    assert archive.raw("memory_counter", "channel:555") is None
    assert len(provider.calls) == 0

# ── 工具调用保护:失败重试风暴与轮次上限 ──────────────────────────


class _ToolCallProvider:
    """每轮都返回同一个工具调用的假 Provider，用于测试工具循环保护。"""

    def __init__(self, tool_name: str = "archive_crud__save_archive") -> None:
        self.tool_name = tool_name
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call-{len(self.calls)}",
                    "type": "function",
                    "function": {"name": self.tool_name, "arguments": "{}"},
                }
            ],
        }

    async def close(self) -> None:
        pass


def _make_service_with_loop_config(
    *,
    archive: _FakeArchive,
    provider: Any,
    executor: Any,
    group_interval: int = 1,
    max_tool_rounds: int = 20,
    snippet_chars: int = 120,
) -> ArchiveMemoryAutoSummaryService:
    config = SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                trigger=SimpleNamespace(
                    group_interval=group_interval,
                    private_interval=group_interval,
                    prompt_snippet_chars=snippet_chars,
                    max_tool_rounds=max_tool_rounds,
                )
            )
        )
    )
    return ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive,
        provider=provider,
        config=config,
        logger=NullLogger(),
        tool_definitions=[],
        tool_executor=executor,
    )


@pytest.mark.asyncio
async def test_summary_aborts_after_repeated_tool_failures_and_keeps_counter():
    """工具连续失败达到上限即中止，且一次都没写成功时保留计数器待重试。"""
    archive = _FakeArchive()
    provider = _ToolCallProvider()
    logger = Mock(spec=NullLogger)
    executor = AsyncMock(return_value="未知工具: archive_crud__save_archive")
    service = _make_service_with_loop_config(
        archive=archive, provider=provider, executor=executor, group_interval=1
    )
    service._logger = logger

    await service.record_message(
        conversation_kind="group", conversation_id="777", message_text="一"
    )

    assert len(provider.calls) == MAX_TOOL_FAILURES
    assert json.loads(archive.raw("memory_counter", "group:777")["value"])["count"] == 1
    logger.info.assert_not_called()
    warnings = [call.args[0] for call in logger.warning.call_args_list]
    assert "档案自动总结因工具连续失败而中止" in warnings
    assert "档案自动总结未写入任何内容，进入冷却后重试" in warnings


@pytest.mark.asyncio
async def test_summary_resets_counter_when_a_tool_call_succeeds():
    """只要有一次工具调用成功，就按完成处理并复位计数器。"""
    archive = _FakeArchive()
    provider = _ToolCallProvider()
    executor = AsyncMock(return_value='{"ok": true}')
    service = _make_service_with_loop_config(
        archive=archive,
        provider=provider,
        executor=executor,
        group_interval=1,
        max_tool_rounds=2,
    )

    await service.record_message(
        conversation_kind="group", conversation_id="888", message_text="一"
    )

    # 轮次上限为 2，模型每轮都要求调用工具，因此在第 2 轮后结束
    assert len(provider.calls) == 2
    assert json.loads(archive.raw("memory_counter", "group:888")["value"]) == {
        "count": 0,
        "messages": [],
    }


@pytest.mark.asyncio
async def test_summary_prompt_snippet_chars_zero_keeps_full_text():
    """prompt_snippet_chars=0 时消息全文注入，不做截断。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service_with_loop_config(
        archive=archive,
        provider=provider,
        executor=AsyncMock(),
        group_interval=1,
        snippet_chars=0,
    )
    long_text = "很长的消息" * 50

    await service.record_message(
        conversation_kind="group", conversation_id="999", message_text=long_text
    )

    prompt = provider.calls[0][1]["content"]
    assert long_text in prompt
    assert "read_pending_messages" not in prompt

# ── 装配回归:工具定义必须带 skill 前缀且能真正写库 ────────────────


@pytest.mark.asyncio
async def test_bootstrap_summary_tools_are_prefixed_and_write_archives(monkeypatch):
    """回归:总结 agent 的工具定义必须带 {skill}__ 前缀，否则 skill_manager.execute
    无法路由，模型每次调用都返回"未知工具"并反复重试烧 token。"""
    from neobot_app.bootstrap import _providers as providers_module
    from neobot_app.bootstrap._services import build_archive_summary_service
    from neobot_app.skills.archive_crud import ArchiveCRUDSkill
    from neobot_app.skills.base import SkillManager

    # 强制回退到本测试的假 provider：其他测试可能已加载真实配置并注册真实模型
    def _no_provider(_name):
        raise RuntimeError("test: no real provider")

    monkeypatch.setattr(providers_module, "create_provider", _no_provider)

    archive = _FakeArchive()
    skill_manager = SkillManager()
    skill_manager.register(ArchiveCRUDSkill(archive_service=archive))

    class _LoggerFactory:
        def get_logger(self, name: str) -> NullLogger:
            return NullLogger()

    config = SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                trigger=SimpleNamespace(group_interval=1, private_interval=1),
                archive=SimpleNamespace(
                    max_chars=500,
                    group_profile_max_chars=1500,
                    allow_delete=False,
                    allowed_tables=[],
                ),
                favorability=SimpleNamespace(max_change_per_summary=5),
                item_archive=SimpleNamespace(enabled=False, table_name="item_archive"),
            )
        )
    )

    calls: list[dict] = []

    class _PatchProvider:
        """第一轮要求 patch_archive 追加事实，第二轮结束。"""

        async def chat(self, messages, tools=None):
            calls.append({"messages": messages, "tools": tools})
            if len(calls) == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "archive_crud__patch_archive",
                                "arguments": json.dumps(
                                    {
                                        "table_name": "group_profile",
                                        "key": "888",
                                        "operations": [
                                            {"op": "append", "text": "群友喜欢豆浆"}
                                        ],
                                    },
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "done", "tool_calls": None}

        async def close(self) -> None:
            pass

    provider = _PatchProvider()
    service = build_archive_summary_service(
        config=config,
        archive_memory_service=archive,
        provider=provider,
        fallback_provider=provider,
        logger_factory=_LoggerFactory(),
        skill_manager=skill_manager,
    )

    names = [tool["function"]["name"] for tool in service._tool_definitions]
    assert names, "总结 agent 必须挂载档案工具"
    assert all(name.startswith("archive_crud__") for name in names), names
    assert "archive_crud__patch_archive" in names

    await service.record_message(
        conversation_kind="group", conversation_id="888", message_text="我喜欢豆浆"
    )

    # 工具真的写进了档案（前缀修复前这里永远是空的）
    assert archive.raw("group_profile", "888")["value"] == "群友喜欢豆浆"
    assert json.loads(archive.raw("memory_counter", "group:888")["value"]) == {
        "count": 0,
        "messages": [],
    }


@pytest.mark.asyncio
async def test_summary_records_token_usage(monkeypatch):
    """总结调用必须计入 agent:memory 用量，否则成本在统计里是黑盒。"""
    from neobot_app.statistics import tracker as tracker_module

    recorded: list[dict] = []

    class _Tracker:
        async def record(self, **kwargs):
            recorded.append(kwargs)

    monkeypatch.setattr(tracker_module, "_tracker", _Tracker())

    class _UsageProvider:
        model = "deepseek-chat"

        async def chat(self, messages, tools=None):
            return {
                "role": "assistant",
                "content": "ok",
                "tool_calls": None,
                "extensions": {
                    "usage": {
                        "input_tokens": 1000,
                        "output_tokens": 200,
                        "cache_hit_tokens": 400,
                        "cache_miss_tokens": 600,
                    }
                },
            }

        async def close(self) -> None:
            pass

    archive = _FakeArchive()
    service = _make_service_with_loop_config(
        archive=archive,
        provider=_UsageProvider(),
        executor=AsyncMock(),
        group_interval=1,
    )

    await service.record_message(
        conversation_kind="group", conversation_id="555", message_text="一"
    )

    assert recorded == [
        {
            "module": "agent:memory",
            "model_name": "deepseek-chat",
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_hit_tokens": 400,
            "cache_miss_tokens": 600,
            "conversation_kind": "group",
            "conversation_id": "555",
        }
    ]


# ── 失败冷却:防止「每条消息重跑一次总结」的 token 风暴 ──────────────


@pytest.mark.asyncio
async def test_failed_summary_enters_cooldown_and_does_not_rerun_per_message():
    """间隔 1 + 必然失败的 provider：连续 5 条消息只允许触发 1 次总结。

    这是 token 风暴的回归测试——修复前计数器越过阈值后每条消息都会重跑
    一整轮工具循环(现实中表现为每 60 秒一次超时，连续烧数小时)。
    """
    archive = _FakeArchive()
    provider = _FakeProvider(fail=True)
    service = _make_service(archive=archive, provider=provider, group_interval=1)

    for i in range(5):
        await service.record_message(
            conversation_kind="group",
            conversation_id="990",
            message_text=f"消息 {i}",
        )

    assert len(provider.calls) == 1
    state = json.loads(archive.raw("memory_counter", "group:990")["value"])
    # 计数继续累计(冷却期内消息不丢)，但模型调用只发生了一次
    assert state["count"] == 5
    assert state["failures"] == 1
    assert state["retry_after"] > epoch_seconds()
    assert len(state["messages"]) == 1


@pytest.mark.asyncio
async def test_cooldown_expiry_allows_one_retry():
    """冷却到期后只补一次重试，失败则再次进入更长的冷却。"""
    archive = _FakeArchive()
    provider = _FakeProvider(fail=True)
    service = _make_service(archive=archive, provider=provider, group_interval=1)

    await service.record_message(
        conversation_kind="group", conversation_id="991", message_text="一"
    )
    assert len(provider.calls) == 1

    # 手动把冷却时间拨到过去，模拟冷却到期
    state = json.loads(archive.raw("memory_counter", "group:991")["value"])
    first_retry_after = state["retry_after"]
    state["retry_after"] = epoch_seconds() - 1
    await archive.set(
        "memory_counter", "group:991", json.dumps(state), ["auto_summary_counter"]
    )

    await service.record_message(
        conversation_kind="group", conversation_id="991", message_text="二"
    )

    assert len(provider.calls) == 2
    state = json.loads(archive.raw("memory_counter", "group:991")["value"])
    assert state["failures"] == 2
    # 退避翻倍：第二次失败的冷却窗口必须晚于第一次
    assert state["retry_after"] > first_retry_after


def test_backoff_is_capped():
    """退避必须封顶，避免长时间完全不总结。"""
    delays = [ArchiveMemoryAutoSummaryService._backoff_seconds(n) for n in range(1, 12)]
    assert delays[0] < delays[1] < delays[2]
    assert max(delays) <= RETRY_BACKOFF_MAX_SECONDS


@pytest.mark.asyncio
async def test_summary_concurrency_guard_skips_overlapping_runs():
    """同一会话的总结不得并发：消息在总结期间到达只累计，不叠加新任务。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=1)

    assert service._begin_summary("group:1") is True
    try:
        await service.record_message(
            conversation_kind="group", conversation_id="1", message_text="一"
        )
    finally:
        service._end_summary("group:1")

    assert provider.calls == []
    state = json.loads(archive.raw("memory_counter", "group:1")["value"])
    assert state["count"] == 1


@pytest.mark.asyncio
async def test_summary_stops_at_total_time_budget():
    """工具循环必须在总时长预算内收口，不能无限轮次耗尽 token。"""
    archive = _FakeArchive()
    provider = _ToolCallProvider()
    service = _make_service_with_loop_config(
        archive=archive,
        provider=provider,
        executor=AsyncMock(return_value='{"ok": true}'),
        group_interval=1,
        max_tool_rounds=20,
    )
    service._summary_budget_seconds = 0.05

    await service.record_message(
        conversation_kind="group", conversation_id="992", message_text="一"
    )

    assert len(provider.calls) < 20
    state = json.loads(archive.raw("memory_counter", "group:992")["value"])
    assert state["count"] == 1
    assert state["retry_after"] > epoch_seconds()


# ── 工具返回与上下文体积极限 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_result_is_truncated_before_entering_context():
    """单条工具返回必须先截断再进上下文，否则下一轮会把它整块重发。"""
    archive = _FakeArchive()
    provider = _ToolCallProvider()
    huge = "档" * (MAX_TOOL_RESULT_CHARS * 3)
    service = _make_service_with_loop_config(
        archive=archive,
        provider=provider,
        executor=AsyncMock(return_value=huge),
        group_interval=1,
        max_tool_rounds=2,
    )

    await service.record_message(
        conversation_kind="group", conversation_id="993", message_text="一"
    )

    assert len(provider.calls) == 2
    # provider.calls 保存的是同一个可变列表，因此这里校验全部 tool 消息的规模
    tool_messages = [
        message for message in provider.calls[1] if message.get("role") == "tool"
    ]
    assert tool_messages
    for message in tool_messages:
        assert len(message["content"]) <= MAX_TOOL_RESULT_CHARS + 100
        assert "已截断" in message["content"]


def test_old_tool_results_are_dropped_when_over_total_budget():
    """工具返回总量超预算时，从最早的一批开始替换为占位符。"""
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prompt"},
    ]
    rounds = 5
    per_round = MAX_TOOL_RESULT_TOTAL_CHARS // 2
    for index in range(rounds):
        messages.append({"role": "assistant", "content": None})
        messages.append({"role": "tool", "content": "x" * per_round})

    _trim_tool_history(messages)

    kept = [
        message
        for message in messages
        if message.get("role") == "tool" and message["content"] != _TOOL_DROPPED_MARKER
    ]
    dropped = [
        message
        for message in messages
        if message.get("role") == "tool" and message["content"] == _TOOL_DROPPED_MARKER
    ]
    # 最近的保留、最早的被丢弃，且保留量在预算内
    assert len(kept) <= 2
    assert len(dropped) == rounds - len(kept)
    assert sum(len(message["content"]) for message in kept) <= (
        MAX_TOOL_RESULT_TOTAL_CHARS
    )
    # system / user 消息不受影响
    assert messages[0]["content"] == "sys"
    assert messages[1]["content"] == "prompt"


def test_trim_tool_history_keeps_non_tool_messages_intact():
    """裁剪只针对 tool 消息，assistant 的工具调用结构必须保持可用。"""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 10},
    ]
    _trim_tool_history(messages)
    assert messages[1]["tool_calls"] == [{"id": "c1"}]
    assert messages[2]["content"] == "x" * 10


# ── 超时调用的可观测性 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_timed_out_model_call_is_logged_with_request_size():
    """超时调用不会返回 usage，本地统计彻底看不到，必须留下带请求规模的告警。"""

    class _HangingProvider:
        async def chat(self, messages, tools=None):
            await asyncio.sleep(30)
            raise AssertionError("wait_for 应当先超时")

        async def close(self) -> None:
            pass

    archive = _FakeArchive()
    logger = Mock(spec=NullLogger)
    service = _make_service(archive=archive, provider=_HangingProvider(), group_interval=1)
    service._logger = logger
    service._summary_budget_seconds = 2.0

    await service.record_message(
        conversation_kind="group", conversation_id="994", message_text="一"
    )

    warnings = [call for call in logger.warning.call_args_list]
    timeout_warnings = [
        call
        for call in warnings
        if call.args and call.args[0] == "档案自动总结模型调用超时，本次调用不会计入用量统计"
    ]
    assert len(timeout_warnings) == 1
    kwargs = timeout_warnings[0].kwargs
    assert kwargs["conversation_id"] == "994"
    assert kwargs["request_chars"] > 0
    assert kwargs["messages_count"] >= 2
    # 超时同样要进入冷却，避免连续重跑
    state = json.loads(archive.raw("memory_counter", "group:994")["value"])
    assert state["retry_after"] > epoch_seconds()



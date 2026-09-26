"""ContextRecorder 测试:写入内容、滚动淘汰、线程安全、参数校验与 orchestrator 集成。

存储形态见 test_context_recorder_history（纯内存 + 逐份 diff）。
"""

from __future__ import annotations

import threading

import pytest

from neobot_app.observability.context_recorder import ContextRecorder


def _payload(index: int = 0) -> dict:
    return {
        "recorded_at": "2025-01-01T00:00:00+00:00",
        "event_id": f"evt-{index}",
        "messages_count": 2,
        "total_chars": 10,
        "estimated_tokens": 13,
        "messages": [
            {"role": "system", "content": "人设"},
            {"role": "user", "content": "你好"},
        ],
    }


def test_record_context_keeps_full_payload() -> None:
    """写入的 payload 完整可读：messages 与统计字段都在。"""
    recorder = ContextRecorder(limit=10)

    seq = recorder.record_context(_payload())

    assert seq == 1
    data = recorder.read_entry(seq)
    assert data is not None
    assert data["event_id"] == "evt-0"
    assert data["messages"][0]["role"] == "system"
    assert data["messages"][1]["content"] == "你好"
    assert data["total_chars"] == 10
    assert recorder.read_latest() == data


def test_record_context_prunes_to_limit() -> None:
    """超过 limit 后只保留最新 N 份，最旧的被淘汰。"""
    recorder = ContextRecorder(limit=3)
    for index in range(5):
        recorder.record_context(_payload(index))

    assert [item.seq for item in recorder.list_entries()] == [3, 4, 5]
    assert recorder.read_entry(1) is None
    assert recorder.read_entry(2) is None
    latest = recorder.read_entry(5)
    assert latest is not None and latest["event_id"] == "evt-4"


def test_record_context_is_thread_safe_and_unique() -> None:
    """并发写入不丢份数、seq 不重号。"""
    recorder = ContextRecorder(limit=50)
    errors: list[Exception] = []

    def worker(worker_id: int) -> None:
        try:
            for _ in range(20):
                recorder.record_context(_payload(worker_id))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    entries = recorder.list_entries()
    assert len(entries) == 50
    assert len({item.seq for item in entries}) == 50


def test_context_recorder_rejects_bad_limit() -> None:
    with pytest.raises(ValueError):
        ContextRecorder(limit=0)
    with pytest.raises(ValueError):
        ContextRecorder(limit=-5)


def test_read_entry_tolerates_bad_seq_input() -> None:
    recorder = ContextRecorder(limit=3)
    recorder.record_context(_payload())
    assert recorder.read_entry("bad") is None  # type: ignore[arg-type]
    assert recorder.read_entry(999) is None


# ── orchestrator 集成 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_record_context_skips_without_recorder() -> None:
    """未配置 context_recorder 时 _record_context 无副作用。"""
    from types import SimpleNamespace

    from neobot_app.reply.orchestrator import ReplyOrchestrator

    orch = object.__new__(ReplyOrchestrator)
    orch._context_recorder = None
    orch._logger = None
    event = SimpleNamespace(
        event_id="evt-x",
        mode="agent",
        conversation_ref=SimpleNamespace(kind="group", id="42"),
    )
    messages = [{"role": "system", "content": "sys"}]

    await orch._record_context(event, messages, iteration=1, stage="agent_model_call")


@pytest.mark.asyncio
async def test_orchestrator_record_context_keeps_message_stats() -> None:
    """配置 context_recorder 时记录完整 messages 与统计字段。"""
    from types import SimpleNamespace

    from neobot_app.reply.orchestrator import ReplyOrchestrator

    recorder = ContextRecorder(limit=3)
    orch = object.__new__(ReplyOrchestrator)
    orch._context_recorder = recorder
    orch._logger = None
    event = SimpleNamespace(
        event_id="evt-y",
        mode="agent",
        conversation_ref=SimpleNamespace(kind="group", id="42"),
    )
    messages = [
        {"role": "system", "content": "人设提示词"},
        {"role": "user", "content": "你好"},
    ]

    await orch._record_context(event, messages, iteration=2, stage="agent_model_call")

    data = recorder.read_latest()
    assert data is not None
    assert data["event_id"] == "evt-y"
    assert data["mode"] == "agent"
    assert data["conversation_kind"] == "group"
    assert data["conversation_id"] == "42"
    assert data["pipeline_key"] == "group:42"
    assert data["iteration"] == 2
    assert data["stage"] == "agent_model_call"
    assert data["messages_count"] == 2
    assert data["total_chars"] > 0
    assert data["estimated_tokens"] > 0
    assert len(data["messages"]) == 2
    # 未传 response 时输出/usage 字段为空
    assert data["output_chars"] == 0
    assert data["usage"] is None
    assert data["cache_hit_rate"] is None


@pytest.mark.asyncio
async def test_orchestrator_record_context_includes_response_and_usage() -> None:
    """传入 response 时记录完整输出与 usage/缓存命中率。"""
    from types import SimpleNamespace

    from neobot_app.reply.orchestrator import ReplyOrchestrator

    recorder = ContextRecorder(limit=3)
    orch = object.__new__(ReplyOrchestrator)
    orch._context_recorder = recorder
    orch._logger = None
    event = SimpleNamespace(
        event_id="evt-z",
        mode="agent",
        conversation_ref=SimpleNamespace(kind="group", id="42"),
    )
    messages = [{"role": "system", "content": "人设提示词"}]
    response = {
        "role": "assistant",
        "content": "这是模型回复的内容",
        "extensions": {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_hit_tokens": 70,
                "cache_miss_tokens": 30,
            }
        },
    }

    await orch._record_context(
        event, messages, iteration=1, stage="agent_model_call", response=response
    )

    data = recorder.read_latest()
    assert data is not None
    assert data["response"]["content"] == "这是模型回复的内容"
    assert data["output_chars"] == len("这是模型回复的内容")
    assert data["output_estimated_tokens"] > 0
    assert data["usage"]["cache_hit_tokens"] == 70
    assert data["usage"]["cache_miss_tokens"] == 30
    assert data["cache_hit_tokens"] == 70
    assert data["cache_miss_tokens"] == 30
    assert data["cache_hit_rate"] == 0.7
    assert data["messages"][0]["role"] == "system"
    assert data["messages_count"] == 1

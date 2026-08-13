"""ContextRecorder 测试:写入内容、滚动清理、参数校验与 orchestrator 集成。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from neobot_app.observability.context_recorder import ContextRecorder


def test_record_context_writes_full_payload(tmp_path) -> None:
    """写入的 JSON 包含完整 messages 与统计字段。"""
    recorder = ContextRecorder(tmp_path, max_files=10)
    payload = {
        "recorded_at": "2025-01-01T00:00:00+00:00",
        "event_id": "evt-1",
        "messages_count": 2,
        "total_chars": 10,
        "estimated_tokens": 13,
        "messages": [
            {"role": "system", "content": "人设"},
            {"role": "user", "content": "你好"},
        ],
    }

    target = recorder.record_context(payload)

    assert target.exists()
    assert target.suffix == ".json"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["event_id"] == "evt-1"
    assert data["messages"][0]["role"] == "system"
    assert data["messages"][1]["content"] == "你好"
    assert data["total_chars"] == 10


def test_record_context_prunes_to_max_files(tmp_path) -> None:
    """超过 max_files 后自动删除最旧文件,只保留最新 N 个。"""
    recorder = ContextRecorder(tmp_path, max_files=3)
    for i in range(5):
        recorder.record_context({"seq": i, "messages": []})

    files = sorted(tmp_path.glob("ctx_*.json"))
    assert len(files) == 3
    seqs = [json.loads(f.read_text(encoding="utf-8"))["seq"] for f in files]
    assert seqs == [2, 3, 4]


def test_record_context_is_thread_safe_and_unique(tmp_path) -> None:
    """并发写入不丢文件、不重名覆盖。"""
    recorder = ContextRecorder(tmp_path, max_files=50)
    import threading

    errors: list[Exception] = []

    def worker(seq: int) -> None:
        try:
            for _ in range(20):
                recorder.record_context({"seq": seq, "messages": []})
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    files = list(tmp_path.glob("ctx_*.json"))
    assert len(files) == 50
    assert len({f.name for f in files}) == len(files)


def test_context_recorder_rejects_bad_max_files(tmp_path) -> None:
    with pytest.raises(ValueError):
        ContextRecorder(tmp_path, max_files=0)


# ── orchestrator 集成 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_orchestrator_record_context_skips_without_recorder() -> None:
    """未配置 context_recorder 时 _record_context 无副作用。"""
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
async def test_orchestrator_record_context_writes_file(tmp_path) -> None:
    """配置 context_recorder 时写入包含统计字段的上下文文件。"""
    from neobot_app.reply.orchestrator import ReplyOrchestrator

    orch = object.__new__(ReplyOrchestrator)
    orch._context_recorder = ContextRecorder(tmp_path, max_files=3)
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

    files = list(tmp_path.glob("ctx_*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["event_id"] == "evt-y"
    assert data["mode"] == "agent"
    assert data["conversation_kind"] == "group"
    assert data["conversation_id"] == "42"
    assert data["iteration"] == 2
    assert data["stage"] == "agent_model_call"
    assert data["messages_count"] == 2
    assert data["total_chars"] > 0
    assert data["estimated_tokens"] > 0
    assert len(data["messages"]) == 2

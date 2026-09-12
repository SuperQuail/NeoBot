"""ContextRecorder 提示词历史(落盘 + 元数据索引)测试。

覆盖 spec(3) 验收点 A4/A6/A8/A10/A15 的后端部分。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace

from neobot_contracts.ports.logging import NullLogger

from neobot_app.observability import context_recorder as recorder_module
from neobot_app.observability.context_recorder import ContextRecorder, PromptMeta


def _payload(
    index: int,
    *,
    pipeline_key: str = "group:1",
    iteration: int = 1,
    body: str = "",
) -> dict:
    """构造一份与回复管线 payload 同形的完整上下文。"""
    kind, _, conversation_id = pipeline_key.partition(":")
    return {
        "recorded_at": f"2026-01-01T00:00:{index % 60:02d}+00:00",
        "stage": "agent_model_call",
        "event_id": f"evt-{index}",
        "mode": "agent",
        "conversation_kind": kind,
        "conversation_id": conversation_id,
        "pipeline_key": pipeline_key,
        "iteration": iteration,
        "model": "deepseek-chat",
        "messages_count": 2,
        "messages": [
            {"role": "system", "content": body or f"系统提示词 {index}"},
            {"role": "user", "content": "你好"},
        ],
        "response": None,
    }


def _contains(value: object, needle: str, seen: set[int]) -> bool:
    """深度扫描对象图里是否出现 needle(用于证明正文没常驻内存)。"""
    if isinstance(value, str):
        return needle in value
    if isinstance(value, (bytes, bytearray)):
        return False
    if id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, dict):
        return any(
            _contains(key, needle, seen) or _contains(item, needle, seen)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains(item, needle, seen) for item in value)
    attributes = getattr(value, "__dict__", None)
    if isinstance(attributes, dict):
        return any(_contains(item, needle, seen) for item in attributes.values())
    return False


# ── 元数据索引 ──────────────────────────────────────────────────


def test_meta_index_filter_and_read_entry(tmp_path: Path) -> None:
    """索引字段齐全；可按 pipeline_key 过滤；read_entry 返回完整 JSON。"""
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    recorder.record_context(_payload(1, pipeline_key="group:1"))
    recorder.record_context(_payload(2, pipeline_key="private:9", iteration=3))
    recorder.record_context(_payload(3, pipeline_key="group:1"))

    entries = recorder.list_entries()
    assert [item.seq for item in entries] == [1, 2, 3]
    assert [item.pipeline_key for item in entries] == [
        "group:1",
        "private:9",
        "group:1",
    ]
    second = entries[1]
    assert isinstance(second, PromptMeta)
    assert second.iteration == 3
    assert second.model == "deepseek-chat"
    assert second.total_messages == 2
    assert second.recorded_at == "2026-01-01T00:00:02+00:00"
    assert second.bytes == Path(second.path).stat().st_size
    assert Path(second.path).exists()

    assert [item.seq for item in recorder.list_entries("group:1")] == [1, 3]
    assert recorder.list_entries("group:missing") == []
    assert [item.seq for item in recorder.list_entries(None)] == [1, 2, 3]

    full = recorder.read_entry(2)
    assert full is not None
    assert full["event_id"] == "evt-2"
    assert full["messages"][0]["content"] == "系统提示词 2"
    assert recorder.read_entry(999) is None
    assert recorder.read_entry("bad") is None  # type: ignore[arg-type]
    latest = recorder.read_latest()
    assert latest is not None and latest["event_id"] == "evt-3"
    assert recorder.latest_seq == 3


def test_meta_pipeline_key_falls_back_to_conversation_ids(tmp_path: Path) -> None:
    """payload 缺 pipeline_key 时按 conversation_kind:id 兜底(方便旧数据)。"""
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    payload = _payload(1, pipeline_key="group:42")
    payload.pop("pipeline_key")

    recorder.record_context(payload)

    assert recorder.list_entries()[0].pipeline_key == "group:42"


# ── A4：全局保留最近 N 份 ────────────────────────────────────────


def test_prune_keeps_only_latest_limit_files(tmp_path: Path) -> None:
    """连续写入 120 次后磁盘只保留全局最近 100 份，最旧整份被删。"""
    recorder = ContextRecorder(tmp_path, max_files=100, logger=NullLogger())
    for index in range(1, 121):
        recorder.record_context(_payload(index))

    files = sorted(tmp_path.glob("ctx_*.json"))
    assert len(files) == 100
    entries = recorder.list_entries()
    assert [item.seq for item in entries] == list(range(21, 121))
    assert {str(item) for item in files} == {item.path for item in entries}
    for seq in range(1, 21):
        assert recorder.read_entry(seq) is None
    kept = recorder.read_entry(21)
    assert kept is not None and kept["event_id"] == "evt-21"


# ── A6：默认模式内存里只有索引 ──────────────────────────────────


def test_default_mode_keeps_no_prompt_body_in_memory(tmp_path: Path) -> None:
    """默认模式下常驻内存只有索引，正文只存在于磁盘。"""
    secret = "PROMPT-BODY-" + "x" * 20000
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    recorder.record_context(_payload(1, body=secret))

    assert recorder.latest_in_memory is False
    assert not _contains(vars(recorder), secret, set())
    meta = recorder.list_entries()[0]
    assert secret not in json.dumps(meta.to_dict(), ensure_ascii=False)
    assert recorder.read_entry(meta.seq) is not None
    assert recorder.read_entry(meta.seq)["messages"][0]["content"] == secret  # type: ignore[index]

    # 正文只在磁盘：删掉文件就读不到了（证明没有内存副本）
    Path(meta.path).unlink()
    assert recorder.read_entry(meta.seq) is None


def test_latest_in_memory_serves_without_disk_read(tmp_path: Path) -> None:
    """latest_in_memory=True 时最新一份留在内存，常规轮询不必读盘。"""
    secret = "LATEST-" + "y" * 20000
    recorder = ContextRecorder(
        tmp_path, max_files=10, logger=NullLogger(), latest_in_memory=True
    )
    recorder.record_context(_payload(1, body=secret))
    seq = recorder.latest_seq
    assert seq is not None

    Path(recorder.list_entries()[0].path).unlink()

    full = recorder.read_entry(seq)
    assert full is not None and full["messages"][0]["content"] == secret


# ── 重启后重建索引 ──────────────────────────────────────────────


def test_index_rebuilt_from_disk_after_restart(tmp_path: Path) -> None:
    """重启(新实例)后能扫描既有文件重建索引，且新写入不与旧文件冲突。"""
    first = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    for index in range(1, 4):
        first.record_context(_payload(index, pipeline_key="group:7"))
    first.record_context(_payload(4, pipeline_key="private:5", iteration=2))

    second = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    entries = second.list_entries()
    assert [item.seq for item in entries] == [1, 2, 3, 4]
    assert entries[0].pipeline_key == "group:7"
    assert entries[3].pipeline_key == "private:5"
    assert entries[3].iteration == 2
    assert entries[3].model == "deepseek-chat"
    assert entries[3].total_messages == 2
    assert entries[3].recorded_at == "2026-01-01T00:00:04+00:00"
    assert entries[0].bytes > 0
    full = second.read_entry(3)
    assert full is not None and full["event_id"] == "evt-3"

    second.record_context(_payload(5))
    names = [path.name for path in tmp_path.glob("ctx_*.json")]
    assert len(names) == len(set(names)) == 5
    assert second.latest_seq == 5

    # latest_in_memory=True 时启动即把最新一份读进内存
    warmed = ContextRecorder(
        tmp_path, max_files=10, logger=NullLogger(), latest_in_memory=True
    )
    Path(warmed.list_entries()[-1].path).unlink()
    cached = warmed.read_entry(5)
    assert cached is not None and cached["event_id"] == "evt-5"


def test_index_rebuild_extracts_metadata_from_large_file(tmp_path: Path) -> None:
    """超过探针长度的文件也能从 JSON 前缀提取元数据(不做全量解析)。"""
    big = "z" * 400_000
    recorder = ContextRecorder(tmp_path, max_files=5, logger=NullLogger())
    recorder.record_context(_payload(1, pipeline_key="group:8", body=big))
    assert (tmp_path / next(iter(tmp_path.glob("ctx_*.json"))).name).stat().st_size > (
        recorder_module._META_PROBE_CHARS
    )

    rebuilt = ContextRecorder(tmp_path, max_files=5, logger=NullLogger())
    meta = rebuilt.list_entries()[0]
    assert meta.pipeline_key == "group:8"
    assert meta.iteration == 1
    assert meta.model == "deepseek-chat"
    assert meta.total_messages == 2
    assert meta.recorded_at == "2026-01-01T00:00:01+00:00"
    full = rebuilt.read_entry(1)
    assert full is not None and full["messages"][0]["content"] == big


# ── A8 / A10：原子写与异常吞掉 ──────────────────────────────────


def test_atomic_write_failure_leaves_no_partial_file(
    tmp_path: Path, monkeypatch
) -> None:
    """注入写盘中断（原子替换失败）后，目标文件要么不存在要么完整。"""
    import neobot_app.utils.atomic as atomic_module

    def _boom(source: str, target: Path) -> None:
        raise OSError("模拟目标文件被占用")

    monkeypatch.setattr(atomic_module, "_replace_with_retry", _boom)
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())

    target = recorder.record_context(_payload(1))

    assert target.name.startswith("ctx_")
    assert not target.exists()
    assert list(tmp_path.glob("ctx_*.json")) == []
    assert list(tmp_path.glob(".*.tmp")) == []
    assert recorder.list_entries() == []


def test_write_exception_never_propagates(tmp_path: Path, monkeypatch) -> None:
    """写盘抛异常时只记 debug，调用方不受影响。"""

    def _boom(path: Path, text: str) -> None:
        raise OSError("磁盘写失败")

    monkeypatch.setattr(recorder_module, "atomic_write_text", _boom)
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())

    recorder.record_context(_payload(1))

    assert list(tmp_path.glob("ctx_*.json")) == []
    assert recorder.list_entries() == []


def test_concurrent_readers_never_observe_partial_json(tmp_path: Path) -> None:
    """写入过程中并发读取只会看到完整 JSON，不会拿到半截文件。"""
    recorder = ContextRecorder(tmp_path, max_files=200, logger=NullLogger())
    body = "b" * 200_000
    stop = threading.Event()
    errors: list[str] = []

    def writer() -> None:
        try:
            for index in range(1, 21):
                recorder.record_context(_payload(index, body=f"{body}{index}"))
        finally:
            stop.set()

    def reader() -> None:
        while not stop.is_set():
            for path in tmp_path.glob("ctx_*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    continue
                except ValueError as exc:
                    errors.append(f"{path.name}: {exc}")
                    return
                if data.get("messages_count") != 2:
                    errors.append(f"{path.name}: 内容不完整")
                    return

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    assert len(list(tmp_path.glob("ctx_*.json"))) == 20


def test_corrupt_file_does_not_break_init_or_read(tmp_path: Path) -> None:
    """损坏的历史文件不阻断启动，也读不崩。"""
    (tmp_path / "ctx_20260101_000000_000001_0001.json").write_text(
        "{ 不是合法 JSON", encoding="utf-8"
    )

    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())

    entries = recorder.list_entries()
    assert [item.seq for item in entries] == [1]
    assert entries[0].pipeline_key == ""
    assert entries[0].total_messages == 0
    assert entries[0].recorded_at == "2026-01-01T00:00:00.000001"
    assert recorder.read_entry(1) is None


# ── 清理 ────────────────────────────────────────────────────────


def test_clear_removes_files_and_index(tmp_path: Path) -> None:
    recorder = ContextRecorder(tmp_path, max_files=10, logger=NullLogger())
    for index in range(1, 4):
        recorder.record_context(_payload(index))

    assert recorder.clear() == 3
    assert list(tmp_path.glob("ctx_*.json")) == []
    assert recorder.list_entries() == []
    assert recorder.read_latest() is None
    assert recorder.latest_seq is None


# ── A15：bootstrap 配置接线 ─────────────────────────────────────


def _services():
    """延迟导入：bootstrap 包很重，且与本模块的其余用例无耦合。"""
    from neobot_app.bootstrap import _services as services

    return services


def _config(**chat_overrides) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(**chat_overrides),
        debug=SimpleNamespace(enabled=False),
    )


def test_build_context_recorder_uses_chat_config(
    tmp_path: Path, monkeypatch
) -> None:
    """由 [chat] 配置控制，与 debug.enabled 解耦，目录迁到 chat_flows/prompts。"""
    services = _services()
    monkeypatch.setattr(services, "DATA_DIR", tmp_path)
    config = _config(
        chat_flow_prompt_history_enabled=True,
        chat_flow_prompt_history_limit=7,
        chat_flow_latest_in_memory=True,
    )

    recorder = services.build_context_recorder(config=config, logger=NullLogger())

    assert recorder is not None
    assert recorder.log_dir == tmp_path / "chat_flows" / "prompts"
    assert recorder.log_dir.exists()
    assert recorder.max_files == 7
    assert recorder.latest_in_memory is True


def test_build_context_recorder_disabled_by_chat_config(
    tmp_path: Path, monkeypatch
) -> None:
    """关闭 chat_flow_prompt_history_enabled 后不再写盘（返回 None）。"""
    services = _services()
    monkeypatch.setattr(services, "DATA_DIR", tmp_path)
    config = SimpleNamespace(
        chat=SimpleNamespace(chat_flow_prompt_history_enabled=False),
        debug=SimpleNamespace(enabled=True),
    )

    assert services.build_context_recorder(config=config, logger=NullLogger()) is None
    assert not (tmp_path / "chat_flows").exists()


def test_build_context_recorder_defaults_tolerate_missing_values(
    tmp_path: Path, monkeypatch
) -> None:
    """字段缺失或为 None 时按默认值(True/100/False)工作。"""
    services = _services()
    monkeypatch.setattr(services, "DATA_DIR", tmp_path)
    recorder = services.build_context_recorder(
        config=_config(), logger=NullLogger()
    )
    assert recorder is not None
    assert recorder.max_files == 100
    assert recorder.latest_in_memory is False

    tolerant = services.build_context_recorder(
        config=_config(
            chat_flow_prompt_history_enabled=None,
            chat_flow_prompt_history_limit=None,
            chat_flow_latest_in_memory=None,
        ),
        logger=NullLogger(),
    )
    assert tolerant is not None
    assert tolerant.max_files == 100
    assert tolerant.latest_in_memory is False

    invalid = services.build_context_recorder(
        config=_config(chat_flow_prompt_history_limit=0), logger=NullLogger()
    )
    assert invalid is not None
    assert invalid.max_files == 100

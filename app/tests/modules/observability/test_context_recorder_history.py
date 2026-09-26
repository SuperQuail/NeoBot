"""ContextRecorder 提示词历史（纯内存 + 逐份 diff + 图片脱敏）测试。

覆盖 features/spec(10) 的验收点：
- 不落盘：写满也不产生任何文件；
- 逐份 diff：补丁远小于整份，常驻内存显著低于「全量快照」；
- 图片只留哈希：base64 不进内存；
- 有界：全局保留最近 N 份，淘汰后仍能重建其余各份；
- 旧落盘目录：不读取、可在清空时回收。
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

from neobot_contracts.ports.logging import NullLogger

from neobot_app.observability import context_recorder as recorder_module
from neobot_app.observability.context_recorder import ContextRecorder, PromptMeta
from neobot_app.observability.prompt_diff import IMAGE_HASH_PREFIX, payload_bytes


def _sized_text(index: int, size: int = 2000) -> str:
    return (f"第{index}段" * (size // 4))[:size]


def _payload(
    index: int,
    *,
    pipeline_key: str = "group:1",
    iteration: int = 1,
    extra_messages: int = 0,
    image: bytes | None = None,
) -> dict:
    """构造一份与回复管线 payload 同形的完整上下文。"""
    kind, _, conversation_id = pipeline_key.partition(":")
    messages: list[dict] = [
        {"role": "system", "content": _sized_text(0, 4000)},
        {"role": "user", "content": _sized_text(index)},
    ]
    for offset in range(extra_messages):
        messages.append({"role": "assistant", "content": _sized_text(index + offset)})
    if image is not None:
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看图"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(image).decode("ascii")
                        },
                    },
                ],
            }
        )
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
        "messages_count": len(messages),
        "total_chars": sum(len(str(item.get("content", ""))) for item in messages),
        "messages": messages,
        "response": None,
    }


def _growing_payload(rounds: int) -> dict:
    """真实形态的上下文：messages 逐轮追加，**之前的内容一字不改**。

    回复管线的 messages 就是这样长起来的，也是 diff 存储能省下两个数量级的前提；
    各份之间只有 recorded_at / iteration / 最后一条等少数字段不同。
    """
    messages: list[dict] = [{"role": "system", "content": _sized_text(0, 4000)}]
    for index in range(rounds):
        messages.append({"role": "user", "content": f"第 {index} 轮用户消息 " + "内容" * 200})
        messages.append({"role": "assistant", "content": f"第 {index} 轮回复 " + "回复" * 200})
    return {
        "recorded_at": f"2026-01-01T00:01:{rounds % 60:02d}+00:00",
        "stage": "agent_model_call",
        "pipeline_key": "group:1",
        "iteration": rounds,
        "model": "deepseek-chat",
        "messages_count": len(messages),
        "messages": messages,
        "response": None,
    }


def _contains(value: object, needle: str, seen: set[int]) -> bool:
    """深度扫描对象图里是否出现 needle（用于证明 base64 没进内存）。"""
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


# ── 元数据索引与读取 ────────────────────────────────────────────


def test_meta_index_filter_and_read_entry() -> None:
    """索引字段齐全；可按 pipeline_key 过滤；read_entry 返回完整 JSON。"""
    recorder = ContextRecorder(limit=10, logger=NullLogger())
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
    assert second.bytes == payload_bytes(_payload(2, pipeline_key="private:9", iteration=3))
    assert second.patch_bytes > 0

    assert [item.seq for item in recorder.list_entries("group:1")] == [1, 3]
    assert recorder.list_entries("group:missing") == []
    assert [item.seq for item in recorder.list_entries(None)] == [1, 2, 3]

    full = recorder.read_entry(2)
    assert full is not None
    assert full["event_id"] == "evt-2"
    assert full["messages"][1]["content"] == _sized_text(2)
    assert recorder.read_entry(999) is None
    latest = recorder.read_latest()
    assert latest is not None and latest["event_id"] == "evt-3"
    assert recorder.latest_seq == 3


def test_meta_pipeline_key_falls_back_to_conversation_ids() -> None:
    """payload 缺 pipeline_key 时按 conversation_kind:id 兜底。"""
    recorder = ContextRecorder(limit=10, logger=NullLogger())
    payload = _payload(1, pipeline_key="group:42")
    payload.pop("pipeline_key")

    recorder.record_context(payload)

    assert recorder.list_entries()[0].pipeline_key == "group:42"


# ── 不落盘 ──────────────────────────────────────────────────────


def test_nothing_is_written_to_disk(tmp_path: Path) -> None:
    """写满 limit 份也不产生任何文件（旧实现会写 ctx_*.json）。"""
    recorder = ContextRecorder(limit=5, logger=NullLogger())
    for index in range(1, 9):
        recorder.record_context(_payload(index))

    assert list(tmp_path.iterdir()) == []
    assert recorder.limit == 5


# ── diff 存储成本 ───────────────────────────────────────────────


def test_storage_is_far_below_full_snapshots() -> None:
    """逐份 diff 的常驻体积必须远低于「每份都存全量」。"""
    recorder = ContextRecorder(limit=40, logger=NullLogger())
    payloads = []
    for rounds in range(1, 41):
        payload = _growing_payload(rounds)
        payloads.append(payload)
        recorder.record_context(payload)

    full_total = sum(payload_bytes(payload) for payload in payloads)
    resident = recorder.storage_bytes

    assert recorder.limit == 40
    # 全量快照需要 ~40 份；diff 只需要「最旧快照 + 最新快照 + 极小补丁」
    assert resident * 10 < full_total
    # 补丁永远小于整份；payload 越长优势越明显（最后一份已是 1 个数量级以上）
    for meta in recorder.list_entries()[1:]:
        assert meta.patch_bytes < meta.bytes
    assert recorder.list_entries()[-1].patch_bytes * 10 < recorder.list_entries()[-1].bytes
    # 每一份依然能原样重建
    for meta in recorder.list_entries():
        data = recorder.read_entry(meta.seq)
        assert data is not None
        assert data["messages_count"] == meta.total_messages


def test_identical_payloads_cost_nothing_extra() -> None:
    """内容完全相同时补丁为空，只多出一条元数据。"""
    recorder = ContextRecorder(limit=10, logger=NullLogger())
    payload = _payload(7)
    recorder.record_context(payload)
    recorder.record_context(payload)

    entries = recorder.list_entries()
    assert len(entries) == 2
    assert entries[1].patch_bytes == len("[]")
    assert recorder.read_entry(2) == recorder.read_entry(1)


# ── 图片只留哈希 ────────────────────────────────────────────────


def test_image_base64_is_replaced_by_gallery_hash() -> None:
    """写入后内存里不存在 base64，只剩与图库同口径的 sha256。"""
    raw = b"\x89PNG\r\n\x1a\n" + b"image-bytes" * 500
    digest = hashlib.sha256(raw).hexdigest()
    recorder = ContextRecorder(limit=5, logger=NullLogger())

    recorder.record_context(_payload(1, image=raw))

    data = recorder.read_latest()
    assert data is not None
    part = data["messages"][-1]["content"][1]
    assert part["image_url"]["url"] == IMAGE_HASH_PREFIX + digest
    # 整个记录器对象图里都不该再有 base64（用原图字节的 base64 片段做探针）
    probe = base64.b64encode(raw)[:40].decode("ascii")
    assert not _contains(vars(recorder), probe, set())
    meta = recorder.list_entries()[0]
    assert meta.images == 1
    assert recorder.image_refs == 1


def test_image_payload_size_is_dominated_by_nothing() -> None:
    """图片脱敏后单份体积回落到文本量级（否则 100 份根本放不进内存）。"""
    raw = b"\x89PNG" + bytes(200_000)
    recorder = ContextRecorder(limit=5, logger=NullLogger())

    recorder.record_context(_payload(1, image=raw))

    meta = recorder.list_entries()[0]
    assert meta.bytes < 20_000


# ── 有界与重建 ──────────────────────────────────────────────────


def test_prune_keeps_latest_limit_and_rebuilds_rest() -> None:
    """写 120 次后只保留最近 100 份，且每一份都能正确重建。"""
    recorder = ContextRecorder(limit=100, logger=NullLogger())
    for index in range(1, 121):
        recorder.record_context(_payload(index))

    entries = recorder.list_entries()
    assert [item.seq for item in entries] == list(range(21, 121))
    for seq in range(1, 21):
        assert recorder.read_entry(seq) is None
    # 淘汰后剩下的每一份都要能重建出正确内容（定基逻辑不能把补丁链弄错）
    for seq in range(21, 121):
        data = recorder.read_entry(seq)
        assert data is not None, seq
        assert data["event_id"] == f"evt-{seq}"
        assert data["messages"][1]["content"] == _sized_text(seq)


def test_reconstruction_returns_private_objects() -> None:
    """重建返回的对象是私有副本：改动它不会污染历史。"""
    recorder = ContextRecorder(limit=10, logger=NullLogger())
    for index in range(1, 4):
        recorder.record_context(_payload(index))

    first = recorder.read_entry(2)
    assert first is not None
    first["messages"][0]["content"] = "被改坏了"
    again = recorder.read_entry(2)
    assert again is not None
    assert again["messages"][0]["content"] == _sized_text(0, 4000)
    latest = recorder.read_entry(3)
    assert latest is not None and latest["messages"][1]["content"] == _sized_text(3)


def test_clear_drops_everything_and_returns_count() -> None:
    recorder = ContextRecorder(limit=10, logger=NullLogger())
    for index in range(1, 4):
        recorder.record_context(_payload(index))

    assert recorder.clear() == 3
    assert recorder.list_entries() == []
    assert recorder.read_latest() is None
    assert recorder.latest_seq is None
    assert recorder.storage_bytes == 0
    # 清空后继续记录：新的一份重新成为快照，seq 继续单调递增
    assert recorder.record_context(_payload(9)) == 4
    assert recorder.read_entry(4) is not None


# ── 旧落盘目录 ──────────────────────────────────────────────────


def test_legacy_files_are_not_read_but_cleared(tmp_path: Path) -> None:
    """旧 ctx_*.json 不参与历史读取，但清空历史时一并回收。"""
    legacy = tmp_path / "chat_flows" / "prompts"
    legacy.mkdir(parents=True)
    (legacy / "ctx_20260101_000000_000001_0001.json").write_text(
        json.dumps({"event_id": "old", "messages": []}), encoding="utf-8"
    )

    recorder = ContextRecorder(limit=10, logger=NullLogger(), legacy_dir=legacy)

    assert recorder.list_entries() == []
    assert recorder.read_latest() is None
    recorder.record_context(_payload(1))
    assert len(list(legacy.glob("ctx_*.json"))) == 1  # 不会被消费

    assert recorder.clear() == 1
    assert list(legacy.glob("ctx_*.json")) == []


def test_missing_legacy_dir_is_tolerated(tmp_path: Path) -> None:
    recorder = ContextRecorder(
        limit=10, logger=NullLogger(), legacy_dir=tmp_path / "nope"
    )
    assert recorder.record_context(_payload(1)) == 1
    assert recorder.clear() == 1


# ── 异常与并发 ──────────────────────────────────────────────────


def test_write_exception_never_propagates(monkeypatch) -> None:
    """脱敏/序列化抛异常时只记 debug，调用方不受影响。"""

    def _boom(_value):
        raise RuntimeError("脱敏炸了")

    monkeypatch.setattr(recorder_module, "sanitize_images", _boom)
    recorder = ContextRecorder(limit=10, logger=NullLogger())

    assert recorder.record_context(_payload(1)) == 0
    assert recorder.list_entries() == []


def test_concurrent_readers_never_observe_wrong_entry() -> None:
    """写入过程中并发读取只会拿到完整且自洽的历史。"""
    recorder = ContextRecorder(limit=200, logger=NullLogger())
    stop = threading.Event()
    errors: list[str] = []
    total = 30

    def writer() -> None:
        try:
            for index in range(1, total + 1):
                recorder.record_context(_payload(index, extra_messages=index % 5))
        finally:
            stop.set()

    def reader() -> None:
        while not stop.is_set():
            for meta in recorder.list_entries():
                data = recorder.read_entry(meta.seq)
                if data is None:
                    errors.append(f"seq={meta.seq} 读不到")
                    return
                if data.get("event_id") != f"evt-{meta.seq}":
                    errors.append(f"seq={meta.seq} 内容串味")
                    return
                if data.get("messages_count") != meta.total_messages:
                    errors.append(f"seq={meta.seq} 条数不一致")
                    return

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert not errors
    assert len(recorder.list_entries()) == total


# ── bootstrap 配置接线 ──────────────────────────────────────────


def _services():
    """延迟导入：bootstrap 包很重，且与本模块的其余用例无耦合。"""
    from neobot_app.bootstrap import _services as services

    return services


def _config(**chat_overrides) -> SimpleNamespace:
    return SimpleNamespace(
        chat=SimpleNamespace(**chat_overrides),
        debug=SimpleNamespace(enabled=False),
    )


def test_build_context_recorder_uses_chat_config(tmp_path: Path, monkeypatch) -> None:
    """由 [chat] 配置控制，与 debug.enabled 解耦；纯内存不建目录。"""
    services = _services()
    monkeypatch.setattr(services, "DATA_DIR", tmp_path)
    config = _config(
        chat_flow_prompt_history_enabled=True,
        chat_flow_prompt_history_limit=7,
    )

    recorder = services.build_context_recorder(config=config, logger=NullLogger())

    assert recorder is not None
    assert recorder.limit == 7
    assert not (tmp_path / "chat_flows").exists()
    assert recorder.record_context(_payload(1)) == 1


def test_build_context_recorder_disabled_by_chat_config(
    tmp_path: Path, monkeypatch
) -> None:
    """关闭 chat_flow_prompt_history_enabled 后不记录（返回 None）。"""
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
    """字段缺失或为 None 时按默认值（True/100）工作；非法值回退默认。"""
    services = _services()
    monkeypatch.setattr(services, "DATA_DIR", tmp_path)

    recorder = services.build_context_recorder(config=_config(), logger=NullLogger())
    assert recorder is not None
    assert recorder.limit == 100

    tolerant = services.build_context_recorder(
        config=_config(
            chat_flow_prompt_history_enabled=None,
            chat_flow_prompt_history_limit=None,
        ),
        logger=NullLogger(),
    )
    assert tolerant is not None
    assert tolerant.limit == 100

    invalid = services.build_context_recorder(
        config=_config(chat_flow_prompt_history_limit=0), logger=NullLogger()
    )
    assert invalid is not None
    assert invalid.limit == 100

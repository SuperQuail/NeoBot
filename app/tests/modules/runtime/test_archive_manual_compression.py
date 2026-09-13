"""面板手动 / 批量 AI 档案压缩的服务层测试（spec(4) Part C）。

覆盖 A31/A32/A33/A34/A38/A39/A40/A41/A42/A43/A44/A45：
- 目标字符数参数化（自动仍是全局上限、手动是本次输入）+ 共用单飞键；
- 目标校验（下限 200 / 上限 max_total_chars，0 时兜底 100000）；
- no-op（目标 ≥ 当前字数 → 零 token）；
- 失败 / 未达标 → 回滚原文 + 删除快照 + 状态 failed；
- 压缩前快照（手动 reason=manual、自动 reason=auto）；
- 用量 conversation_kind=archive_manual / archive_overflow 单列；
- 批量：逐条串行 + 统一目标 + skipped/truncated；
- 全文约束：提示词注入被省略时必须用 read_archive 分页读全文。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import pytest_asyncio
from neobot_contracts.ports.logging import NullLogger
from neobot_memory import ArchiveMemoryService
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from neobot_app.runtime import archive_memory_summary as summary_module
from neobot_app.runtime.archive_memory_summary import (
    AUTO_COMPRESSION_USAGE_KIND,
    MANUAL_COMPRESSION_USAGE_KIND,
    MANUAL_TASK_TTL_SECONDS,
    MANUAL_TARGET_FALLBACK_MAX_CHARS,
    MAX_MANUAL_TASKS,
    MAX_OVERFLOW_PROMPT_CHARS,
    MIN_MANUAL_TARGET_CHARS,
    ArchiveMemoryAutoSummaryService,
    _ARCHIVE_PROMPT_OMITTED,
)
from neobot_app.skills.archive_crud import ArchiveCRUDSkill


def _engine():
    return create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _save_call(table: str, key: str, value: str, call_id: str = "call-save") -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "archive_crud__save_archive",
                    "arguments": json.dumps(
                        {"table_name": table, "key": key, "value": value}
                    ),
                },
            }
        ],
    }


def _read_calls(offsets: list[int], *, table: str, key: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call-read-{offset}",
                "type": "function",
                "function": {
                    "name": "archive_crud__read_archive",
                    "arguments": json.dumps(
                        {"table_name": table, "key": key, "offset": offset}
                    ),
                },
            }
            for offset in offsets
        ],
    }


class _ScriptedProvider:
    """按轮次返回预置响应，并把每轮请求留存下来（含 extensions.usage）。"""

    def __init__(self, rounds: list[dict[str, Any]], *, usage: dict[str, int] | None = None) -> None:
        self.rounds = list(rounds)
        self.usage = usage
        self.calls: list[list[dict]] = []
        self.active = 0
        self.max_active = 0

    async def chat(self, messages, tools=None):
        self.calls.append([dict(message) for message in messages])
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            response: dict[str, Any] = (
                dict(self.rounds[len(self.calls) - 1])
                if len(self.calls) <= len(self.rounds)
                else {"role": "assistant", "content": "done", "tool_calls": None}
            )
            if self.usage:
                response["extensions"] = {"usage": dict(self.usage)}
            return response
        finally:
            self.active -= 1

    async def close(self) -> None:
        pass


def _parse_table_key(prompt: str) -> tuple[str, str]:
    import re

    table = re.search(r"table_name: (\S+)", prompt)
    key = re.search(r"key: (\S+)", prompt)
    return (table.group(1) if table else "", key.group(1) if key else "")


class _KeyAwareProvider:
    """按提示词里的 (table, key) 写回压缩结果（批量场景每个条目各跑一轮）。"""

    def __init__(self, *, compressed_chars: int = 1000, suffix: str = "y") -> None:
        self.calls: list[list[dict]] = []
        self.saved: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.compressed_chars = compressed_chars
        self.suffix = suffix

    async def chat(self, messages, tools=None):
        self.calls.append([dict(message) for message in messages])
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0)
            seen_tool_result = any(
                message.get("role") == "tool" for message in messages
            )
            if seen_tool_result:
                return {"role": "assistant", "content": "done", "tool_calls": None}
            table, key = _parse_table_key(str(messages[-1].get("content") or ""))
            self.saved.append((table, key))
            return _save_call(
                table,
                key,
                self.suffix * self.compressed_chars,
                call_id=f"call-save-{table}-{key}",
            )
        finally:
            self.active -= 1

    async def close(self) -> None:
        pass


class _RecordingExecutor:
    """把工具调用路由到真实 ArchiveCRUDSkill（与生产工具面一致）。"""

    def __init__(self, service: ArchiveMemoryService) -> None:
        self.skill = ArchiveCRUDSkill(archive_service=service)
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, dict(args)))
        local = tool_name.split("__", 1)[-1]
        return await self.skill.execute(local, dict(args))


def _config(max_total_chars: int = 10000) -> Any:
    from types import SimpleNamespace

    return SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                archive=SimpleNamespace(
                    max_total_chars=max_total_chars,
                    overflow_action="summarize",
                    overflow_summary_cooldown_seconds=600.0,
                ),
                trigger=SimpleNamespace(group_interval=500, private_interval=500),
            )
        )
    )


class _Env:
    def __init__(self, engine, archive_service, summary, executor) -> None:
        self.engine = engine
        self.archive_service = archive_service
        self.summary = summary
        self.executor = executor


@pytest_asyncio.fixture
async def env():
    """真实 sqlite 存储 + 真实档案服务 + 真实总结服务（provider / 工具面可换）。"""
    created: list[_Env] = []

    async def _build(*, provider=None, max_total_chars: int = 10000) -> _Env:
        engine = _engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        archive_service = ArchiveMemoryService(
            uow_factory=make_uow_factory(engine), logger=NullLogger()
        )
        executor = _RecordingExecutor(archive_service)
        summary = ArchiveMemoryAutoSummaryService(
            archive_memory_service=archive_service,
            provider=provider,
            config=_config(max_total_chars),
            logger=NullLogger(),
            tool_definitions=[
                {"type": "function", "function": {"name": "archive_crud__save_archive"}},
                {"type": "function", "function": {"name": "archive_crud__read_archive"}},
            ],
            tool_executor=executor,
        )
        item = _Env(engine, archive_service, summary, executor)
        created.append(item)
        return item

    yield _build
    for item in created:
        await item.summary.wait_pending_overflow_tasks()
        await item.engine.dispose()


async def _seed(
    service: ArchiveMemoryService, table: str, key: str, value: str, tags=None
) -> None:
    """用面板路径（set_if_version）播种：绕过容量治理，避免顺手触发自动压缩。"""
    await service.set_if_version(table, key, value, list(tags or []), 0)


async def _run(summary, task_id: str) -> dict[str, Any]:
    await summary.wait_pending_overflow_tasks()
    payload = summary.get_manual_task(task_id)
    assert payload is not None
    return payload


# ── A31：目标字符数生效 + 快照留痕 ────────────────────────────────


async def test_manual_compression_hits_target_and_keeps_snapshot(env) -> None:
    original = "关键事实: 甲喜欢豆浆\n" + "x" * 12000
    compressed = "关键事实: 甲喜欢豆浆\n" + "y" * 2000
    provider = _ScriptedProvider([_save_call("user_profile", "1", compressed)])
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", original, ["重要"])

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000, operator_ip="127.0.0.1"
    )
    assert started["status"] == "running"
    assert started["task_id"]
    assert started["chars_before"] == len(original)

    task = await _run(built.summary, started["task_id"])
    assert task["status"] == "done"
    assert task["target_chars"] == 3000
    assert task["chars_before"] == len(original)
    assert task["chars_after"] == len(compressed)
    assert task["operator_ip"] == "127.0.0.1"
    assert task["snapshot_id"]
    assert task["message"] == f"{len(original)} → {len(compressed)} 字（目标 3000）"

    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and stored.value == compressed
    assert "甲喜欢豆浆" in stored.value

    snapshots = await built.archive_service.list_snapshots("user_profile", "1")
    assert len(snapshots) == 1
    assert snapshots[0]["reason"] == "manual"
    assert snapshots[0]["total_chars"] == len(original)
    assert snapshots[0]["operator_ip"] == "127.0.0.1"
    detail = await built.archive_service.get_snapshot(snapshots[0]["id"])
    assert detail is not None and detail["value"] == original

    # 提示词必须写明 trigger / target，并说明这是运维主动要求的目标
    prompt = provider.calls[0][-1]["content"]
    assert "trigger: manual" in prompt
    assert "target_chars: 3000" in prompt
    assert "hard_limit: 3000" in prompt
    assert "explicitly requested by the operator" in prompt


async def test_manual_compression_does_not_rewrite_global_config(env) -> None:
    """A34：触发前后全局上限不变（目标只对本次生效）。"""
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y" * 100)])
    built = await env(provider=provider, max_total_chars=10000)
    await _seed(built.archive_service, "user_profile", "1", "x" * 12000)

    await built.summary.start_manual_compression("user_profile", "1", target_chars=500)
    await built.summary.wait_pending_overflow_tasks()

    assert built.summary._overflow_max_total_chars == 10000
    assert built.archive_service.max_total_chars == 10000
    assert built.summary.manual_target_bounds() == (200, 10000)


# ── A32：no-op（零 token） ────────────────────────────────────────


async def test_manual_target_not_below_current_is_noop(env) -> None:
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y")])
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", "x" * 300)

    payload = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=300
    )

    assert payload["status"] == "noop"
    assert payload["task_id"] is None
    assert payload["noop"] is True
    assert provider.calls == []  # 零 token：一次模型调用都没有
    assert built.summary._manual_tasks == {}
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and len(stored.value) == 300


# ── A33 / A44：目标校验 ───────────────────────────────────────────


async def test_manual_target_validation(env) -> None:
    built = await env(max_total_chars=10000)
    with pytest.raises(ValueError, match="不能小于 200"):
        built.summary.normalize_manual_target(MIN_MANUAL_TARGET_CHARS - 1)
    with pytest.raises(ValueError, match="不能大于 10000"):
        built.summary.normalize_manual_target(10001)
    with pytest.raises(ValueError, match="必须是整数"):
        built.summary.normalize_manual_target("abc")
    assert built.summary.normalize_manual_target(200) == 200
    assert built.summary.normalize_manual_target("3000") == 3000


async def test_manual_target_falls_back_when_capacity_governance_disabled(env) -> None:
    """A44：max_total_chars=0（容量治理关闭）时手动压缩仍可用，取兜底上限。"""
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y" * 100)])
    built = await env(provider=provider, max_total_chars=0)
    assert built.summary.manual_target_bounds() == (200, MANUAL_TARGET_FALLBACK_MAX_CHARS)
    await _seed(built.archive_service, "user_profile", "1", "x" * 5000)

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=MANUAL_TARGET_FALLBACK_MAX_CHARS
    )
    # 目标 ≥ 当前字数 → no-op（不调用模型）；换一个真正需要压缩的目标
    assert started["status"] == "noop"
    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=2000
    )
    task = await _run(built.summary, started["task_id"])
    assert task["status"] == "done"
    assert task["chars_after"] == 100


# ── A39 / A43：失败与未达标 → 保留原文 + 删除快照 ────────────────


async def test_manual_compression_without_write_keeps_original(env) -> None:
    provider = _ScriptedProvider([])  # 不调用任何工具就收尾
    built = await env(provider=provider)
    original = "x" * 12000
    await _seed(built.archive_service, "user_profile", "1", original)

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    task = await _run(built.summary, started["task_id"])

    assert task["status"] == "failed"
    assert task["error"]
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and stored.value == original
    # 失败即删除本次快照（原文未变，留痕是冗余）
    assert await built.archive_service.list_snapshots("user_profile", "1") == []
    assert task["snapshot_id"] is None


async def test_manual_compression_over_target_restores_original(env) -> None:
    """A39/A43：模型没压到目标 → failed，且原文被回滚（不是静默留下半成品）。"""
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y" * 5000)])
    built = await env(provider=provider)
    original = "x" * 12000
    await _seed(built.archive_service, "user_profile", "1", original)

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    task = await _run(built.summary, started["task_id"])

    assert task["status"] == "failed"
    assert "3000" in task["error"]
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and stored.value == original
    assert await built.archive_service.list_snapshots("user_profile", "1") == []


async def test_manual_compression_provider_exception_restores_original(env) -> None:
    class _BoomProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None):
            self.calls += 1
            raise RuntimeError("provider boom")

        async def close(self) -> None:
            pass

    provider = _BoomProvider()
    built = await env(provider=provider)
    original = "x" * 12000
    await _seed(built.archive_service, "user_profile", "1", original)

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    task = await _run(built.summary, started["task_id"])

    assert task["status"] == "failed"
    assert "boom" in task["error"]
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and stored.value == original
    assert await built.archive_service.list_snapshots("user_profile", "1") == []
    # 失败进入退避：自动路径不会立刻重跑模型
    assert built.summary._overflow_retry_after


# ── A40：与自动压缩共用单飞键 ────────────────────────────────────


async def test_manual_is_rejected_while_auto_compression_runs(env) -> None:
    release = asyncio.Event()

    class _BlockingProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                await release.wait()
                return _save_call("user_profile", "1", "y" * 2000)
            return {"role": "assistant", "content": "done", "tool_calls": None}

        async def close(self) -> None:
            pass

    provider = _BlockingProvider()
    built = await env(provider=provider)
    await built.archive_service.set_with_outcome("user_profile", "1", "x" * 12000, [])
    await asyncio.sleep(0)  # 让自动压缩进入模型调用

    payload = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    assert payload["status"] == "running"
    assert payload["task_id"] is None
    assert "正在压缩中" in payload["message"]

    release.set()
    await built.summary.wait_pending_overflow_tasks()
    assert provider.calls <= 2  # 全程只有一个模型工具循环
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None and len(stored.value) == 2000


async def test_manual_skips_failure_cooldown(env) -> None:
    """手动触发跳过 _overflow_retry_ready 冷却（用户显式要求）。"""
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y" * 100)])
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", "x" * 12000)
    task_key = built.summary._overflow_task_key("user_profile", "1")
    built.summary._overflow_retry_after[task_key] = 10**12  # 冷却远未到期

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    task = await _run(built.summary, started["task_id"])
    assert task["status"] == "done"
    assert built.summary._overflow_retry_after.get(task_key) is None


# ── 用量统计：手动 / 自动单列（A42） ──────────────────────────────


async def test_usage_kind_separates_manual_from_auto(env, monkeypatch) -> None:
    from neobot_app.statistics import tracker as tracker_module

    recorded: list[dict[str, Any]] = []

    class _FakeTracker:
        async def record(self, **kwargs: Any) -> None:
            recorded.append(kwargs)

    monkeypatch.setattr(tracker_module, "_tracker", _FakeTracker())

    provider = _ScriptedProvider(
        [_save_call("user_profile", "1", "y" * 2000)],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", "x" * 12000)
    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=3000
    )
    await _run(built.summary, started["task_id"])

    manual_kinds = [row["conversation_kind"] for row in recorded]
    assert manual_kinds and set(manual_kinds) == {MANUAL_COMPRESSION_USAGE_KIND}

    # 自动路径（写超限）用另一个 kind
    provider2 = _ScriptedProvider(
        [_save_call("user_profile", "2", "y" * 2000)],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    built2 = await env(provider=provider2)
    monkeypatch.setattr(tracker_module, "_tracker", _FakeTracker())
    await built2.archive_service.set_with_outcome("user_profile", "2", "x" * 12000, [])
    await built2.summary.wait_pending_overflow_tasks()

    all_kinds = [row["conversation_kind"] for row in recorded]
    assert set(all_kinds) == {MANUAL_COMPRESSION_USAGE_KIND, AUTO_COMPRESSION_USAGE_KIND}


async def test_auto_compression_also_writes_snapshot(env) -> None:
    """Q14：自动压缩同样写快照（reason=auto、operator_ip 为空）。"""
    provider = _ScriptedProvider([_save_call("user_profile", "1", "y" * 2000)])
    built = await env(provider=provider)
    original = "x" * 12000
    outcome = await built.archive_service.set_with_outcome("user_profile", "1", original, [])
    assert outcome.scheduled is True
    await built.summary.wait_pending_overflow_tasks()

    snapshots = await built.archive_service.list_snapshots("user_profile", "1")
    assert len(snapshots) == 1
    assert snapshots[0]["reason"] == "auto"
    assert snapshots[0]["operator_ip"] is None
    assert snapshots[0]["total_chars"] == len(original)


# ── 状态表保留策略（FIFO 50 / 30 分钟清理 / 重启清空） ────────────


async def test_manual_task_table_keeps_last_fifty(env) -> None:
    built = await env()
    for index in range(MAX_MANUAL_TASKS + 15):
        task = built.summary._new_manual_task("user_profile", str(index), 500, "ip")
        task["status"] = "done"
        task["finished_at"] = summary_module.epoch_seconds()
    built.summary._prune_manual_tasks()
    assert len(built.summary._manual_tasks) == MAX_MANUAL_TASKS
    assert "0" not in {task["key"] for task in built.summary._manual_tasks.values()}


async def test_manual_task_ttl_cleanup(env) -> None:
    built = await env()
    stale = built.summary._new_manual_task("user_profile", "1", 500, "ip")
    stale["status"] = "done"
    stale["finished_at"] = summary_module.epoch_seconds() - MANUAL_TASK_TTL_SECONDS - 1
    fresh = built.summary._new_manual_task("user_profile", "2", 500, "ip")
    fresh["status"] = "done"
    fresh["finished_at"] = summary_module.epoch_seconds()
    assert built.summary.get_manual_task(stale["task_id"]) is None
    assert built.summary.get_manual_task(fresh["task_id"]) is not None


async def test_manual_task_unknown_id(env) -> None:
    built = await env()
    assert built.summary.get_manual_task("nope") is None


# ── A45：批量（逐条串行 + 统一目标 + skipped / truncated） ─────────


async def test_batch_compression_is_serial_and_reports_skipped(env) -> None:
    provider = _KeyAwareProvider(compressed_chars=1000)
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", "x" * 12000)
    await _seed(built.archive_service, "user_profile", "2", "x" * 13000)
    await _seed(built.archive_service, "user_profile", "3", "x" * 14000)
    built.archive_service.configure_overflow_policy(max_total_chars=100)
    await _seed(built.archive_service, "user_profile", "4", "x" * 900)

    started = await built.summary.start_batch_compression(
        target_chars=1500, operator_ip="10.0.0.1"
    )
    assert started["kind"] == "batch"
    assert started["status"] == "running"
    assert started["truncated"] == 0
    # 900 字的那条（key=4）不大于目标 1500 → 直接标 skipped
    assert [row["key"] for row in started["skipped"]] == ["4"]
    assert {item["key"]: item["status"] for item in started["items"]} == {
        "1": "pending",
        "2": "pending",
        "3": "pending",
        "4": "skipped",
    }

    await built.summary.wait_pending_overflow_tasks()
    task = built.summary.get_manual_task(started["task_id"])
    assert task is not None
    assert task["status"] == "done"
    assert task["succeeded"] == 3
    assert task["failed"] == 0
    by_key = {item["key"]: item for item in task["items"]}
    assert by_key["4"]["status"] == "skipped"
    assert by_key["4"]["chars_after"] is None
    for key in ("1", "2", "3"):
        assert by_key[key]["status"] == "done"
        assert by_key[key]["chars_after"] == 1000
        assert by_key[key]["snapshot_id"]
    assert task["chars_after"] == 3000
    # 任意时刻至多 1 条在跑（逐条串行）
    assert provider.max_active == 1
    assert task["operator_ip"] == "10.0.0.1"


async def test_batch_reports_truncated_beyond_limit(env, monkeypatch) -> None:
    monkeypatch.setattr(summary_module, "MAX_BATCH_COMPRESS_ITEMS", 2)
    provider = _ScriptedProvider([])
    built = await env(provider=provider)
    for index in range(3):
        await _seed(built.archive_service, "user_profile", str(index), "x" * 12000)
    built.archive_service.configure_overflow_policy(max_total_chars=100)

    started = await built.summary.start_batch_compression(target_chars=3000)
    assert started["truncated"] == 1
    assert len(started["items"]) == 2
    await built.summary.wait_pending_overflow_tasks()


async def test_batch_validation_and_provider_requirement(env) -> None:
    built = await env(provider=None)
    with pytest.raises(RuntimeError, match="模型不可用"):
        await built.summary.start_batch_compression(target_chars=3000)


# ── A37 / A38：压缩必须基于全文 ──────────────────────────────────


async def test_prompt_requires_pagination_when_text_is_omitted(env, monkeypatch) -> None:
    monkeypatch.setattr(summary_module, "MAX_OVERFLOW_PROMPT_CHARS", 400)
    built = await env(max_total_chars=10000)
    value = "头" * 300 + "中段唯一标记" + "尾" * 300
    prompt = built.summary._build_overflow_compression_prompt(
        table_name="user_profile",
        key="1",
        value=value,
        limit=200,
        trigger="manual",
        target_chars=200,
    )
    assert _ARCHIVE_PROMPT_OMITTED.strip() in prompt
    assert "read_archive(offset=...)" in prompt
    assert "中段唯一标记" not in prompt  # 中间段确实被省略了
    assert "Never claim the record" in prompt
    assert MAX_OVERFLOW_PROMPT_CHARS == 60_000


async def test_compression_reads_omitted_middle_page_by_page(env, monkeypatch) -> None:
    """A38：7 万字级档案的中间段必须能被分页读回并保留在压缩结果里。"""
    monkeypatch.setattr(summary_module, "MAX_OVERFLOW_PROMPT_CHARS", 400)
    marker = "中段唯一标记-必须保留"
    original = "头" * 300 + marker + "尾" * 600
    stored_compressed = "压缩后:" + marker + ":" + "y" * 200

    class _FullTextProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.pages: list[str] = []

        async def chat(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return _read_calls([0, 1, 2, -1], table="user_profile", key="1")
            if self.calls == 2:
                for message in messages:
                    if message.get("role") != "tool":
                        continue
                    try:
                        payload = json.loads(str(message.get("content") or ""))
                    except ValueError:
                        continue
                    item = payload.get("item") or {}
                    page = str(item.get("value") or "")
                    if page:
                        self.pages.append(page)
                assert any(marker in page for page in self.pages), "分页必须能读到被省略的中间段"
                return _save_call("user_profile", "1", stored_compressed)
            return {"role": "assistant", "content": "done", "tool_calls": None}

        async def close(self) -> None:
            pass

    provider = _FullTextProvider()
    built = await env(provider=provider)
    await _seed(built.archive_service, "user_profile", "1", original)

    started = await built.summary.start_manual_compression(
        "user_profile", "1", target_chars=500
    )
    assert started["task_id"], started
    task = await _run(built.summary, started["task_id"])

    assert task["status"] == "done"
    stored = await built.archive_service.get("user_profile", "1")
    assert stored is not None
    assert marker in stored.value  # A38：中间段没有被物理丢失
    assert len(stored.value) <= 500
    read_tools = [name for name, _args in built.executor.calls if name.endswith("read_archive")]
    assert read_tools
    offsets = [args.get("offset") for name, args in built.executor.calls if name.endswith("read_archive")]
    assert 0 in offsets and -1 in offsets

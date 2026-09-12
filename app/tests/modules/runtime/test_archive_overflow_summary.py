"""ArchiveMemoryAutoSummaryService 的「档案超限 → 后台压缩」测试（spec(1)）。

覆盖 A1/A2（12000 字符 append 后被压缩、关键时刻事实不丢）、A5（memory_counter
永不被压缩）、A6/D3（压缩失败时保留原内容并允许后续重试）以及配置接线。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.time_context import now_utc
from neobot_memory import ArchiveMemoryService

from neobot_app.runtime.archive_memory_summary import (
    COUNTER_TABLE,
    MAX_STORED_MESSAGE_CHARS,
    ArchiveMemoryAutoSummaryService,
)


class _MemoryArchiveAccess:
    """内存版档案访问（够 ArchiveMemoryService 与压缩路径使用）。"""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], ArchiveMemory] = {}
        self._next_id = 0

    async def get(self, table_name: str, key: str):
        return self.items.get((table_name, key))

    async def set(self, table_name: str, key: str, value: str, tags: list[str]):
        self._next_id += 1
        existing = self.items.get((table_name, key))
        entry = ArchiveMemory(
            id=existing.id if existing else self._next_id,
            table_name=table_name,
            key=key,
            value=value,
            tags=list(tags or []),
            created_at=existing.created_at if existing else now_utc(),
            updated_at=now_utc(),
            version=(existing.version + 1) if existing else 1,
        )
        self.items[(table_name, key)] = entry
        return entry

    async def delete(self, table_name: str, key: str) -> bool:
        return self.items.pop((table_name, key), None) is not None

    async def exists(self, table_name: str, key: str) -> bool:
        return (table_name, key) in self.items

    async def list(self, table_name: str, *, tags=None, key_query=None, value_query=None,
                   limit: int = 50, offset: int = 0):
        rows = [item for (name, _), item in self.items.items() if name == table_name]
        return rows[offset : offset + limit]


class _Uow:
    def __init__(self, access: _MemoryArchiveAccess) -> None:
        self.archive = access

    async def __aenter__(self) -> "_Uow":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _UowFactory:
    def __init__(self, access: _MemoryArchiveAccess) -> None:
        self.access = access

    def __call__(self) -> _Uow:
        return _Uow(self.access)


class _CompressingProvider:
    """第一轮返回 save_archive 工具调用（写入压缩后的内容），之后收尾。"""

    def __init__(
        self,
        compressed: str,
        *,
        table_name: str = "user_profile",
        key: str = "1",
        fail: bool = False,
    ) -> None:
        self.compressed = compressed
        self.table_name = table_name
        self.key = key
        self.fail = fail
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        # 复制一份快照：服务会继续往同一个列表里追加，否则留存的请求会被后续轮次改写。
        self.calls.append(list(messages))
        if self.fail:
            raise RuntimeError("provider boom")
        if len(self.calls) > 1:
            return {"role": "assistant", "content": "done", "tool_calls": None}
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "archive_crud__save_archive",
                        "arguments": json.dumps(
                            {
                                "table_name": self.table_name,
                                "key": self.key,
                                "value": self.compressed,
                            }
                        ),
                    },
                }
            ],
        }

    async def close(self) -> None:
        pass


class _NoopProvider:
    """不调用任何工具、直接收尾的 provider（用于计数器场景）。"""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(list(messages))
        return {"role": "assistant", "content": "ok", "tool_calls": None}

    async def close(self) -> None:
        pass


def _make_config(
    *,
    max_total_chars: int = 10000,
    action: str = "summarize",
    cooldown: float = 600.0,
    group_interval: int = 500,
) -> SimpleNamespace:
    return SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                archive=SimpleNamespace(
                    max_total_chars=max_total_chars,
                    overflow_action=action,
                    overflow_summary_cooldown_seconds=cooldown,
                ),
                trigger=SimpleNamespace(
                    group_interval=group_interval,
                    private_interval=group_interval,
                ),
            )
        )
    )


def _executor_for(archive_service: ArchiveMemoryService):
    async def executor(tool_name: str, args: dict) -> str:
        if tool_name == "archive_crud__save_archive":
            await archive_service.set(
                args["table_name"], args["key"], args["value"], list(args.get("tags") or [])
            )
            return '{"ok": true}'
        return f"未知工具: {tool_name}"

    return executor


def _build(
    *,
    provider: Any = None,
    max_total_chars: int = 10000,
    action: str = "summarize",
    cooldown: float = 600.0,
    group_interval: int = 500,
    logger: Any = None,
):
    access = _MemoryArchiveAccess()
    archive_service = ArchiveMemoryService(uow_factory=_UowFactory(access), logger=NullLogger())
    service = ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive_service,
        provider=provider,
        config=_make_config(
            max_total_chars=max_total_chars,
            action=action,
            cooldown=cooldown,
            group_interval=group_interval,
        ),
        logger=logger or NullLogger(),
        tool_definitions=[{"type": "function", "function": {"name": "archive_crud__save_archive"}}],
        tool_executor=_executor_for(archive_service),
    )
    return service, archive_service, access


# ── 配置接线 ──────────────────────────────────────────────────────


async def test_config_is_wired_into_archive_service() -> None:
    service, archive_service, _ = _build(max_total_chars=12345, action="reject", cooldown=42.0)

    assert archive_service.max_total_chars == 12345
    assert archive_service.overflow_action == "reject"
    assert archive_service.exempt_tables == frozenset({COUNTER_TABLE})
    assert archive_service._overflow_cooldown_seconds == 42.0


# ── A1/A2：超限写入触发后台压缩，且关键事实不丢 ────────────────────


async def test_overflow_write_is_compressed_in_background() -> None:
    original = "关键事实: 甲喜欢豆浆\n" + "x" * 12000
    compressed = "关键事实: 甲喜欢豆浆\n" + "y" * 2000
    provider = _CompressingProvider(compressed)
    service, archive_service, _ = _build(provider=provider)

    outcome = await archive_service.set_with_outcome("user_profile", "1", original, [])
    assert outcome.over_limit is True
    assert outcome.scheduled is True

    await service.wait_pending_overflow_tasks()

    stored = await archive_service.get("user_profile", "1")
    assert stored is not None
    assert len(stored.value) <= 10000
    assert stored.value == compressed
    assert "甲喜欢豆浆" in stored.value  # A2：压缩不丢关键事实
    assert len(provider.calls) >= 1
    prompt = provider.calls[0][-1]["content"]
    assert "user_profile" in prompt and "hard_limit: 10000" in prompt
    assert "甲喜欢豆浆" in prompt


async def test_unlimited_config_never_triggers_compression() -> None:
    """max_total_chars=0 时压缩入口完全不介入（A4 在运行时的体现）。"""
    provider = _CompressingProvider("compressed")
    service, archive_service, _ = _build(provider=provider, max_total_chars=0)

    outcome = await archive_service.set_with_outcome("user_profile", "1", "x" * 20000, [])
    await service.wait_pending_overflow_tasks()

    assert outcome.over_limit is False
    assert provider.calls == []
    assert len((await archive_service.get("user_profile", "1")).value) == 20000


# ── 失败兜底（A6 / D3 选项一） ────────────────────────────────────


async def test_compression_failure_keeps_content_and_enters_backoff() -> None:
    logger = Mock(spec=NullLogger)
    provider = _CompressingProvider("x", fail=True)
    service, archive_service, _ = _build(provider=provider, logger=logger)
    original = "x" * 12000

    outcome = await archive_service.set_with_outcome("user_profile", "1", original, [])
    assert outcome.scheduled is True
    await service.wait_pending_overflow_tasks()

    stored = await archive_service.get("user_profile", "1")
    assert stored is not None and stored.value == original  # 不截断、不丢数据
    warnings = [call.args[0] for call in logger.warning.call_args_list]
    assert "档案超限压缩失败，保留原内容等待下次写入重试" in warnings

    # 失败后退避：下一次写入不会立刻重跑模型
    blocked = await archive_service.set_with_outcome("user_profile", "1", original + "x", [])
    assert blocked.scheduled is False

    # 退避到期后（这里直接清空模拟到期）下一次写入重新触发
    service._overflow_retry_after.clear()
    retried = await archive_service.set_with_outcome("user_profile", "1", original + "xx", [])
    assert retried.scheduled is True
    await service.wait_pending_overflow_tasks()


async def test_missing_provider_keeps_content_without_scheduling() -> None:
    """总结模型不可用时：不报错、不截断，仅标记超标（下次写入再试）。"""
    service, archive_service, _ = _build(provider=None)

    outcome = await archive_service.set_with_outcome("user_profile", "1", "x" * 12000, [])

    assert outcome.over_limit is True
    assert outcome.scheduled is False
    stored = await archive_service.get("user_profile", "1")
    assert stored is not None and len(stored.value) == 12000


async def test_reject_action_is_not_configured_by_default() -> None:
    """默认 summarize：接线后普通表写入不被拒绝（行为由配置决定）。"""
    service, archive_service, _ = _build(provider=None, max_total_chars=100)

    outcome = await archive_service.set_with_outcome("user_profile", "1", "x" * 500, [])

    assert outcome.item is not None
    assert outcome.over_limit is True


# ── A5：计数器表永不被上限拦截 / 压缩 ─────────────────────────────


async def test_memory_counter_write_is_never_compressed() -> None:
    provider = _CompressingProvider("compressed")
    service, archive_service, _ = _build(provider=provider)

    payload = json.dumps(
        {"count": 500, "messages": [{"sender_id": "1", "text": "x" * 20000}]},
        ensure_ascii=False,
    )
    outcome = await archive_service.set_with_outcome(
        COUNTER_TABLE, "group:888", payload, ["auto_summary_counter"]
    )
    await service.wait_pending_overflow_tasks()

    assert outcome.over_limit is False
    assert outcome.scheduled is False
    assert provider.calls == []
    stored = await archive_service.get(COUNTER_TABLE, "group:888")
    assert stored is not None and stored.value == payload


async def test_auto_summary_counter_can_grow_past_limit() -> None:
    """真实计数器路径：待总结消息累到超过 10000 字符也不被拒绝、不触发压缩。"""
    provider = _NoopProvider()
    service, archive_service, _ = _build(provider=provider, group_interval=1000)

    for index in range(20):
        await service.record_message(
            conversation_kind="group",
            conversation_id="888",
            message_text="很长的消息" * 200,
        )

    stored = await archive_service.get(COUNTER_TABLE, "group:888")
    assert stored is not None
    assert len(stored.value) > 10000
    state = json.loads(stored.value)
    assert state["count"] == 20
    assert len(state["messages"]) == 20
    assert len(state["messages"][0]["text"]) == MAX_STORED_MESSAGE_CHARS
    assert provider.calls == []


async def test_patch_archive_append_over_limit_end_to_end() -> None:
    """A1/A2：12000 字符的 patch_archive(append) 走完「超限 → 压缩」全链路。"""
    from neobot_app.skills.archive_crud import ArchiveCRUDSkill

    original = "关键事实: 乙喜欢羽毛球\n" + "x" * 5000
    compressed = "关键事实: 乙喜欢羽毛球\n" + "y" * 2000
    provider = _CompressingProvider(compressed)
    service, archive_service, _ = _build(provider=provider)
    skill = ArchiveCRUDSkill(archive_service=archive_service)
    await archive_service.set("user_profile", "1", original, [])

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "append", "text": "z" * 7000}],
            },
        )
    )

    assert result["ok"] is True
    assert result["over_limit"] is True
    assert result["compressing"] is True
    assert result["total_chars"] > 10000

    await service.wait_pending_overflow_tasks()

    stored = await archive_service.get("user_profile", "1")
    assert stored is not None
    assert len(stored.value) <= 10000
    assert "乙喜欢羽毛球" in stored.value


# ── 总结提示词同步存储上限 ────────────────────────────────────────


async def test_summary_prompt_mentions_storage_cap_when_enabled() -> None:
    service, _, _ = _build(max_total_chars=10000)

    prompt = service._build_summary_prompt(
        conversation_kind="group", conversation_id="42", messages=[]
    )

    assert "storage cap of 10000 characters" in prompt
    assert "compressed automatically" in prompt


async def test_summary_prompt_has_no_cap_note_when_disabled() -> None:
    service, _, _ = _build(max_total_chars=0)

    prompt = service._build_summary_prompt(
        conversation_kind="group", conversation_id="42", messages=[]
    )

    assert "storage cap" not in prompt



"""面板档案管理与完整提示词历史接口（features/spec(2) / spec(3)）。

覆盖：表清单与统计、分页列表（不含全文）、单条详情、乐观锁编辑、内部表保护、
独立删除开关 + 审计日志、权限门禁、聊天流可读名称解析与回落、提示词历史读取与清空。
"""

from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore

PASSWORD = "NeoBot-Panel-2026"


class _RecordingLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def debug(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))

    def info(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))

    def warning(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))

    def error(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))

    def exception(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))


class _ArchiveItem:
    def __init__(self, table: str, key: str, value: str, *, version: int = 1, tags=None) -> None:
        self.table_name = table
        self.key = key
        self.value = value
        self.tags = list(tags or [])
        self.version = version
        self.created_at = None
        self.updated_at = None


class _FakeArchiveService:
    """内存档案服务替身：签名对齐 ArchiveMemoryService。"""

    def __init__(self, *, max_total_chars: int = 10000) -> None:
        self.max_total_chars = max_total_chars
        self.rows: dict[tuple[str, str], _ArchiveItem] = {}
        self.deleted: list[tuple[str, str]] = []
        self.conflict_next = False

    def seed(self, table: str, key: str, value: str, *, version: int = 1) -> _ArchiveItem:
        item = _ArchiveItem(table, key, value, version=version)
        self.rows[(table, key)] = item
        return item

    async def list_table_names(self) -> list[str]:
        return sorted({table for table, _ in self.rows})

    async def table_stats(self) -> list[dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        for (table, _key), item in self.rows.items():
            row = stats.setdefault(table, {"table_name": table, "count": 0, "max_value_chars": 0})
            row["count"] += 1
            row["max_value_chars"] = max(row["max_value_chars"], len(item.value))
        return list(stats.values())

    async def list_over_limit(self, *, table_name=None, limit=100, offset=0) -> list[dict[str, Any]]:
        rows = [
            {
                "table_name": item.table_name,
                "key": item.key,
                "chars": len(item.value),
                "version": item.version,
                "updated_at": "",
                "max_total_chars": self.max_total_chars,
                "preview": item.value[:200],
            }
            for item in self.rows.values()
            if self.max_total_chars > 0 and len(item.value) > self.max_total_chars
        ]
        return rows[:limit]

    async def list(self, table, *, tags=None, key_query=None, value_query=None, limit=50, offset=0):
        rows = [item for (name, _key), item in sorted(self.rows.items()) if name == table]
        if key_query:
            rows = [item for item in rows if str(key_query) in item.key]
        if value_query:
            rows = [item for item in rows if str(value_query) in item.value]
        return rows[offset : offset + limit]

    async def get(self, table: str, key: str):
        return self.rows.get((table, key))

    async def set_if_version(self, table, key, value, tags, expected_version):
        from neobot_memory.archive_service import ArchiveVersionConflictError

        if self.conflict_next:
            self.conflict_next = False
            raise ArchiveVersionConflictError(
                "档案已被其他写入修改",
                table_name=table,
                key=key,
                expected_version=expected_version,
                actual_version=expected_version + 5,
            )
        current = self.rows.get((table, key))
        actual = int(current.version) if current is not None else 0
        if actual != int(expected_version):
            raise ArchiveVersionConflictError(
                "档案已被其他写入修改",
                table_name=table,
                key=key,
                expected_version=expected_version,
                actual_version=actual,
            )
        item = _ArchiveItem(table, key, value, version=actual + 1, tags=tags)
        self.rows[(table, key)] = item
        return item

    async def delete(self, table: str, key: str) -> bool:
        removed = self.rows.pop((table, key), None)
        if removed is not None:
            self.deleted.append((table, key))
        return removed is not None


class _FakePromptMeta:
    def __init__(self, seq: int, pipeline_key: str) -> None:
        self.seq = seq
        self.path = f"ctx_{seq:04d}.json"
        self.pipeline_key = pipeline_key
        self.iteration = 1
        self.model = "test-model"
        self.total_messages = 3
        self.bytes = 1024
        self.recorded_at = "2026-09-12T00:00:00+00:00"

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "path": self.path,
            "pipeline_key": self.pipeline_key,
            "iteration": self.iteration,
            "model": self.model,
            "total_messages": self.total_messages,
            "bytes": self.bytes,
            "recorded_at": self.recorded_at,
        }


class _FakeContextRecorder:
    max_files = 100

    def __init__(self) -> None:
        self.entries = [
            _FakePromptMeta(1, "group:100"),
            _FakePromptMeta(2, "private:200"),
        ]
        self.cleared = 0
        self.fail = False

    def list_entries(self, pipeline_key: str | None = None):
        if self.fail:
            raise RuntimeError("磁盘不可用")
        if pipeline_key:
            return [entry for entry in self.entries if entry.pipeline_key == pipeline_key]
        return list(self.entries)

    def read_entry(self, seq: int):
        for entry in self.entries:
            if entry.seq == seq:
                return {"pipeline_key": entry.pipeline_key, "messages": [{"role": "system"}]}
        return None

    def clear(self) -> int:
        count = len(self.entries)
        self.entries = []
        self.cleared = count
        return count


class _FakeProfileService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def get_group_name(self, group_id: str | int) -> str:
        self.calls.append(("group", str(group_id)))
        if self.fail:
            raise RuntimeError("数据库不可用")
        return {100: "测试群聊"}.get(int(group_id), f"群聊{group_id}")

    async def get_user_name(self, user_id: str | int) -> str:
        self.calls.append(("user", str(user_id)))
        if self.fail:
            raise RuntimeError("数据库不可用")
        return {200: "小明"}.get(int(user_id), f"QQ:{user_id}")


class _FakeFlowRegistry:
    def __init__(self) -> None:
        self.flows = [
            {"pipeline_key": "group:100", "conversation_kind": "group", "conversation_id": "100"},
            {"pipeline_key": "private:200", "conversation_kind": "private", "conversation_id": "200"},
            {"pipeline_key": "group:999", "conversation_kind": "", "conversation_id": ""},
        ]

    def list_flows(self):
        return [dict(item) for item in self.flows]

    async def snapshot(self, key: str):
        for item in self.flows:
            if item["pipeline_key"] == key:
                return {**item, "messages": []}
        return None


class _FakeControl:
    def __init__(self, plugins_data: Path) -> None:
        self.plugins_data = plugins_data
        self.snapshots: list[Any] = []

    def plugin_config_path(self, name: str) -> Path:
        return self.plugins_data / name / "config.toml"

    def snapshot_plugins(self) -> list[Any]:
        return []

    def snapshot(self) -> list[Any]:
        return []


def _services(mapping: dict[str, Any]) -> Any:
    """把 dict 包成面板 _service() 期望的「有 get(name, default)」对象。"""
    return SimpleNamespace(
        get=lambda name, default=None: mapping.get(name, default)
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_panel(
    tmp_path: Path,
    *,
    services: dict[str, Any],
    manage_plugins: bool = True,
    allow_archive_delete: bool = False,
    logger: Any = None,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
    logger = logger or _RecordingLogger()
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(
            host="127.0.0.1",
            port=_free_port(),
            manage_plugins=manage_plugins,
            allow_archive_delete=allow_archive_delete,
        ),
        data_dir=data_dir,
        logger=logger,
        adapter=object(),
        plugin_control=_FakeControl(tmp_path / "plugins_data"),
        services=services,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, f"http://127.0.0.1:{server.bound_port}", logger, data_dir


async def _login(base: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["token"], payload["csrf_token"]


@pytest.fixture()
async def archive_panel(tmp_path: Path):
    archive = _FakeArchiveService()
    archive.seed("user_profile", "123", "小明的档案")
    archive.seed("user_profile", "456", "x" * 40, version=2)
    archive.seed("memory_counter", "group:100", "{}")
    services = {"archive_memory_service": archive}
    server, base, logger, _data = await _start_panel(tmp_path, services=services)
    try:
        yield server, base, logger, archive
    finally:
        await server.stop()


async def test_archives_lists_real_tables_with_stats(archive_panel) -> None:
    _server, base, _logger, _archive = archive_panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/archives", headers={"X-Token": token})

    assert response.status_code == 200, response.text
    payload = response.json()
    names = {item["table_name"] for item in payload["items"]}
    assert names == {"user_profile", "memory_counter"}
    counter = next(item for item in payload["items"] if item["table_name"] == "memory_counter")
    assert counter["internal"] is True
    assert counter["note"]
    assert payload["delete_enabled"] is False


async def test_archive_items_is_paginated_without_full_value(archive_panel) -> None:
    _server, base, _logger, _archive = archive_panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        page = await client.get(
            base + "/api/archives/items",
            params={"table": "user_profile", "limit": 1, "offset": 0},
            headers={"X-Token": token},
        )
        filtered = await client.get(
            base + "/api/archives/items",
            params={"table": "user_profile", "key_query": "456"},
            headers={"X-Token": token},
        )

    assert page.status_code == 200, page.text
    body = page.json()
    assert len(body["items"]) == 1
    assert "value" not in body["items"][0]
    assert body["items"][0]["total_chars"] > 0

    assert [row["key"] for row in filtered.json()["items"]] == ["456"]


async def test_archive_item_returns_full_text(archive_panel) -> None:
    _server, base, _logger, _archive = archive_panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            base + "/api/archives/item",
            params={"table": "user_profile", "key": "123"},
            headers={"X-Token": token},
        )
        missing = await client.get(
            base + "/api/archives/item",
            params={"table": "user_profile", "key": "nope"},
            headers={"X-Token": token},
        )

    assert response.status_code == 200, response.text
    assert response.json()["value"] == "小明的档案"
    assert response.json()["editable"] is True
    assert missing.status_code == 404


async def test_archive_update_uses_optimistic_lock(archive_panel) -> None:
    _server, base, _logger, archive = archive_panel
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        stale = await client.put(
            base + "/api/archives/item",
            headers=headers,
            json={"table": "user_profile", "key": "123", "value": "新内容", "version": 99},
        )
        ok = await client.put(
            base + "/api/archives/item",
            headers=headers,
            json={"table": "user_profile", "key": "123", "value": "新内容", "version": 1},
        )

    assert stale.status_code == 409, stale.text
    assert stale.json()["actual_version"] == 1
    assert ok.status_code == 200, ok.text
    assert ok.json()["version"] == 2
    assert archive.rows[("user_profile", "123")].value == "新内容"


async def test_archive_update_conflict_reports_latest_content(archive_panel) -> None:
    _server, base, _logger, archive = archive_panel
    archive.conflict_next = True
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.put(
            base + "/api/archives/item",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"table": "user_profile", "key": "123", "value": "x", "version": 1},
        )

    assert response.status_code == 409
    assert response.json()["current"]["key"] == "123"


async def test_archive_update_guards_internal_table_and_empty_value(archive_panel) -> None:
    _server, base, _logger, _archive = archive_panel
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        internal = await client.put(
            base + "/api/archives/item",
            headers=headers,
            json={"table": "memory_counter", "key": "group:100", "value": "{}", "version": 1},
        )
        empty = await client.put(
            base + "/api/archives/item",
            headers=headers,
            json={"table": "user_profile", "key": "123", "value": "   ", "version": 1},
        )

    assert internal.status_code == 400 and "内部表" in internal.json()["error"]
    assert empty.status_code == 400 and "不能为空" in empty.json()["error"]


async def test_archive_delete_requires_dedicated_switch(tmp_path: Path) -> None:
    archive = _FakeArchiveService()
    archive.seed("user_profile", "123", "档案")
    server, base, logger, _data = await _start_panel(
        tmp_path, services={"archive_memory_service": archive}, allow_archive_delete=False
    )
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            denied = await client.request(
                "DELETE",
                base + "/api/archives/item",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={"table": "user_profile", "key": "123", "version": 1},
            )
        assert denied.status_code == 403
        assert "allow_archive_delete" in denied.json()["error"]
        assert archive.deleted == []
        assert server.runtime_config.allow_archive_delete is False
        assert logger is not None
    finally:
        await server.stop()


async def test_archive_delete_writes_audit_log(tmp_path: Path) -> None:
    archive = _FakeArchiveService()
    archive.seed("user_profile", "123", "需要被记住的档案")
    logger = _RecordingLogger()
    server, base, _logger, _data = await _start_panel(
        tmp_path,
        services={"archive_memory_service": archive},
        allow_archive_delete=True,
        logger=logger,
    )
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            response = await client.request(
                "DELETE",
                base + "/api/archives/item",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={"table": "user_profile", "key": "123", "version": 1},
            )
        assert response.status_code == 200, response.text
        assert response.json()["deleted"] is True
        assert archive.deleted == [("user_profile", "123")]
        audit = [row for row in logger.records if "面板删除档案" in row]
        assert audit and "user_profile" in audit[0] and "需要被记住的档案" in audit[0]
    finally:
        await server.stop()


async def test_archive_writes_require_manage(tmp_path: Path) -> None:
    archive = _FakeArchiveService()
    archive.seed("user_profile", "123", "档案")
    server, base, _logger, _data = await _start_panel(
        tmp_path,
        services={"archive_memory_service": archive},
        manage_plugins=False,
        allow_archive_delete=True,
    )
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            updated = await client.put(
                base + "/api/archives/item",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
                json={"table": "user_profile", "key": "123", "value": "x", "version": 1},
            )
            listing = await client.get(base + "/api/archives", headers={"X-Token": token})
        assert updated.status_code == 403
        assert listing.status_code == 200  # 读操作不受 manage 限制
    finally:
        await server.stop()


async def test_chat_flow_display_names(archive_panel) -> None:
    server, base, _logger, _archive = archive_panel
    service = _FakeProfileService()
    server.services = _services(
        {"profile_service": service, "chat_flow_registry": _FakeFlowRegistry()}
    )
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/chat-flows", headers={"X-Token": token})
        detail = await client.get(
            base + "/api/chat-flows/detail",
            params={"key": "private:200"},
            headers={"X-Token": token},
        )

    names = {item["pipeline_key"]: item["display_name"] for item in listed.json()["items"]}
    assert names["group:100"] == "测试群聊"
    assert names["private:200"] == "小明"
    # 名称缺失时回落到可识别标识，不能是空白
    assert names["group:999"] == "群聊999"
    assert detail.json()["display_name"] == "小明"


async def test_chat_flow_display_name_falls_back_on_error(archive_panel) -> None:
    server, base, _logger, _archive = archive_panel
    service = _FakeProfileService(fail=True)
    server.services = _services(
        {"profile_service": service, "chat_flow_registry": _FakeFlowRegistry()}
    )
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/chat-flows", headers={"X-Token": token})

    assert listed.status_code == 200
    names = [item["display_name"] for item in listed.json()["items"]]
    assert names == ["group:100", "private:200", "group:999"]


async def test_chat_flow_display_name_is_cached(archive_panel) -> None:
    server, base, _logger, _archive = archive_panel
    service = _FakeProfileService()
    server.services = _services(
        {"profile_service": service, "chat_flow_registry": _FakeFlowRegistry()}
    )
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            await client.get(base + "/api/chat-flows", headers={"X-Token": token})

    # 3 次轮询 × 3 条流 = 9 次潜在查询；有 60s TTL 缓存时每个 pipeline_key 只查一次
    assert len(service.calls) == 3
    assert sorted(service.calls) == [("group", "100"), ("group", "999"), ("user", "200")]


async def test_prompt_history_endpoints(archive_panel) -> None:
    server, base, _logger, _archive = archive_panel
    recorder = _FakeContextRecorder()
    server.services = _services({"context_recorder": recorder})
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(
            base + "/api/chat-flows/prompts", headers={"X-Token": token}
        )
        filtered = await client.get(
            base + "/api/chat-flows/prompts",
            params={"key": "group:100"},
            headers={"X-Token": token},
        )
        entry = await client.get(
            base + "/api/chat-flows/prompt", params={"seq": 2}, headers={"X-Token": token}
        )
        missing = await client.get(
            base + "/api/chat-flows/prompt", params={"seq": 99}, headers={"X-Token": token}
        )
        no_seq = await client.get(
            base + "/api/chat-flows/prompt", headers={"X-Token": token}
        )
        cleared = await client.post(
            base + "/api/chat-flows/prompts/clear",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
        )

    assert listed.status_code == 200, listed.text
    assert [row["seq"] for row in listed.json()["items"]] == [1, 2]
    assert listed.json()["limit"] == 100
    assert [row["seq"] for row in filtered.json()["items"]] == [1]
    assert entry.status_code == 200 and entry.json()["entry"]["pipeline_key"] == "private:200"
    assert missing.status_code == 404
    assert no_seq.status_code == 400
    assert cleared.status_code == 200 and cleared.json()["removed"] == 2
    assert recorder.cleared == 2


async def test_prompt_history_clear_requires_manage(tmp_path: Path) -> None:
    recorder = _FakeContextRecorder()
    server, base, _logger, _data = await _start_panel(
        tmp_path, services={"context_recorder": recorder}, manage_plugins=False
    )
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                base + "/api/chat-flows/prompts/clear",
                headers={"X-Token": token, "X-CSRF-Token": csrf},
            )
        assert response.status_code == 403
        assert recorder.cleared == 0
    finally:
        await server.stop()

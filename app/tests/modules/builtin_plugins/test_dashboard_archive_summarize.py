"""面板 AI 档案压缩接口（spec(4) Part C）：触发 / 轮询 / 批量 / 压缩历史。

覆盖 A28–A34 / A41 / A44 / A47 的面板侧：
- 三个写接口都走 _require_manage；
- POST 返回 202 + task_id，GET 轮询到 done（含前后字数与快照 id）；
- 内部表禁止触发（明确文案，不产生模型调用）；
- 目标校验：下限 200 / 上限 max_total_chars（0 时兜底 100000）/ 目标 ≥ 当前字数 → no-op；
- 触发前后 config.toml 未被改写；
- 批量返回 truncated 与 skipped；
- 压缩历史只读（前后字数 / reason / 操作者 / 全文），restore_supported=false。
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest_asyncio
from neobot_contracts.ports.logging import NullLogger
from neobot_memory import ArchiveMemoryService
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore
from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService
from neobot_app.skills.archive_crud import ArchiveCRUDSkill

PASSWORD = "NeoBot-Panel-2026"


class _RecordingLogger:
    def __init__(self) -> None:
        self.records: list[str] = []

    def _record(self, message: str = "", *args: Any, **kwargs: Any) -> None:
        self.records.append(str(message))

    debug = _record
    info = _record
    warning = _record
    error = _record
    exception = _record


class _FakeControl:
    def __init__(self, plugins_data: Path) -> None:
        self.plugins_data = plugins_data

    def plugin_config_path(self, name: str) -> Path:
        return self.plugins_data / name / "config.toml"

    def snapshot(self) -> list[Any]:
        return []


def _services(mapping: dict[str, Any]) -> Any:
    return SimpleNamespace(get=lambda name, default=None: mapping.get(name, default))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _save_call(table: str, key: str, value: str) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"save-{table}-{key}",
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


class _KeyAwareProvider:
    """按提示词里的 (table, key) 写回固定长度的“压缩结果”。"""

    def __init__(self, *, chars: int = 2000, suffix: str = "y") -> None:
        self.chars = chars
        self.suffix = suffix
        self.calls: list[list[dict]] = []
        self.max_active = 0
        self._active = 0

    async def chat(self, messages, tools=None):
        self.calls.append([dict(message) for message in messages])
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        try:
            await asyncio.sleep(0)
            if any(message.get("role") == "tool" for message in messages):
                return {"role": "assistant", "content": "done", "tool_calls": None}
            prompt = str(messages[-1].get("content") or "")
            table = re.search(r"table_name: (\S+)", prompt)
            key = re.search(r"key: (\S+)", prompt)
            return _save_call(
                table.group(1) if table else "",
                key.group(1) if key else "",
                self.suffix * self.chars,
            )
        finally:
            self._active -= 1

    async def close(self) -> None:
        pass


class _Harness:
    def __init__(self, server, base, logger, archive, summary, provider, config_path) -> None:
        self.server = server
        self.base = base
        self.logger = logger
        self.archive = archive
        self.summary = summary
        self.provider = provider
        self.config_path = config_path


@pytest_asyncio.fixture
async def harness(tmp_path: Path):
    created: list[_Harness] = []

    async def _build(
        *,
        max_total_chars: int = 10000,
        manage_plugins: bool = True,
        provider: Any = None,
    ) -> _Harness:
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        archive = ArchiveMemoryService(
            uow_factory=make_uow_factory(engine), logger=NullLogger()
        )
        skill = ArchiveCRUDSkill(archive_service=archive)

        async def _executor(tool_name: str, args: dict) -> str:
            return await skill.execute(tool_name.split("__", 1)[-1], dict(args))

        config = SimpleNamespace(
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
        provider = provider if provider is not None else _KeyAwareProvider()
        summary = ArchiveMemoryAutoSummaryService(
            archive_memory_service=archive,
            provider=provider,
            config=config,
            logger=NullLogger(),
            tool_definitions=[
                {"type": "function", "function": {"name": "archive_crud__save_archive"}},
            ],
            tool_executor=_executor,
        )

        config_path = tmp_path / "config.toml"
        config_path.write_text(
            'version = "0.6.0"\n[agent.memory.archive]\nmax_total_chars = '
            + str(max_total_chars)
            + "\n",
            encoding="utf-8",
        )
        env_path = tmp_path / ".env"
        env_path.write_text("", encoding="utf-8")
        data_dir = tmp_path / "data"
        PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
        logger = _RecordingLogger()
        server = DashboardServer(
            plugin_name="dashboard",
            config=DashboardConfig(
                host="127.0.0.1",
                port=_free_port(),
                manage_plugins=manage_plugins,
                allow_archive_delete=False,
            ),
            data_dir=data_dir,
            logger=logger,
            adapter=object(),
            plugin_control=_FakeControl(tmp_path / "plugins_data"),
            services=_services(
                {
                    "archive_memory_service": archive,
                    "archive_summary_service": summary,
                }
            ),
            config_path=config_path,
            env_path=env_path,
            backup_dir=tmp_path / "backup",
        )
        await server.start()
        item = _Harness(
            server, f"http://127.0.0.1:{server.bound_port}", logger, archive, summary, provider, config_path
        )
        created.append(item)
        return item

    yield _build
    for item in created:
        await item.summary.wait_pending_overflow_tasks()
        await item.server.stop()


async def _login(base: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["token"], payload["csrf_token"]


async def _poll(client, base: str, token: str, task_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        response = await client.get(
            base + "/api/archives/summarize",
            params={"task_id": task_id},
            headers={"X-Token": token},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload.get("status") != "running":
            return payload
        await asyncio.sleep(0.02)
    return payload


# ── A29：权限门禁 ─────────────────────────────────────────────────


async def test_summarize_endpoints_require_manage(harness) -> None:
    built = await harness(manage_plugins=False)
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        started = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 3000},
        )
        status = await client.get(
            built.base + "/api/archives/summarize",
            params={"task_id": "x"},
            headers={"X-Token": token},
        )
        batch = await client.post(
            built.base + "/api/archives/summarize/over-limit",
            headers=headers,
            json={"target_chars": 3000},
        )
        history = await client.get(
            built.base + "/api/archives/snapshots",
            params={"table": "user_profile", "key": "1"},
            headers={"X-Token": token},
        )
    assert started.status_code == 403
    assert status.status_code == 403
    assert batch.status_code == 403
    assert history.status_code == 403
    assert built.provider.calls == []


# ── A28 / A31：触发 + 轮询到 done ─────────────────────────────────


async def test_manual_summarize_returns_202_and_finishes(harness) -> None:
    built = await harness(max_total_chars=10000)
    await built.archive.set_if_version("user_profile", "1", "x" * 12000, ["重要"], 0)
    before = built.config_path.read_text(encoding="utf-8")
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 3000},
        )
        assert response.status_code == 202, response.text
        payload = response.json()
        assert payload["status"] == "running"
        assert payload["task_id"]
        assert payload["chars_before"] == 12000
        task = await _poll(client, built.base, token, payload["task_id"])

    assert task["status"] == "done"
    assert task["target_chars"] == 3000
    assert task["chars_after"] is not None and task["chars_after"] <= 3000
    assert task["snapshot_id"]
    assert task["operator_ip"]  # R18：日志 / 状态里带操作者 IP
    assert any("面板触发 AI 档案压缩" in row for row in built.logger.records)
    assert any("ip=" in row for row in built.logger.records)

    stored = await built.archive.get("user_profile", "1")
    assert stored is not None and len(stored.value) <= 3000
    # A34：目标只对本次生效，配置文件没有被改写
    assert built.config_path.read_text(encoding="utf-8") == before
    assert built.summary._overflow_max_total_chars == 10000


async def test_summarize_status_unknown_task(harness) -> None:
    built = await harness()
    token, _ = await _login(built.base)
    async with httpx.AsyncClient() as client:
        missing = await client.get(
            built.base + "/api/archives/summarize", headers={"X-Token": token}
        )
        unknown = await client.get(
            built.base + "/api/archives/summarize",
            params={"task_id": "nope"},
            headers={"X-Token": token},
        )
    assert missing.status_code == 400
    assert unknown.status_code == 404
    assert "task_id" in missing.json()["error"]


# ── A30 / A32 / A33：拒绝路径 ─────────────────────────────────────


async def test_internal_table_cannot_be_summarized(harness) -> None:
    built = await harness()
    await built.archive.set_if_version("memory_counter", "group:1", "{" + "x" * 20000 + "}", [], 0)
    token, csrf = await _login(built.base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            built.base + "/api/archives/summarize",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"table": "memory_counter", "key": "group:1", "target_chars": 3000},
        )
    assert response.status_code == 400
    assert "内部表" in response.json()["error"]
    assert built.provider.calls == []  # 不产生任何模型调用


async def test_target_not_below_current_is_noop(harness) -> None:
    built = await harness()
    await built.archive.set_if_version("user_profile", "1", "x" * 300, [], 0)
    token, csrf = await _login(built.base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            built.base + "/api/archives/summarize",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"table": "user_profile", "key": "1", "target_chars": 300},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "noop"
    assert payload["task_id"] is None
    assert "无需压缩" in payload["message"]
    assert built.provider.calls == []


async def test_target_bounds_are_validated(harness) -> None:
    built = await harness(max_total_chars=10000)
    await built.archive.set_if_version("user_profile", "1", "x" * 12000, [], 0)
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        too_small = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 199},
        )
        too_big = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 10001},
        )
        missing = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1"},
        )
    assert too_small.status_code == 400
    assert "不能小于 200" in too_small.json()["error"]
    assert too_big.status_code == 400
    assert "不能大于 10000" in too_big.json()["error"]
    assert missing.status_code == 400
    assert built.provider.calls == []


async def test_target_falls_back_when_governance_disabled(harness) -> None:
    """A44：max_total_chars=0 时手动压缩仍可用（上限取兜底 100000）。"""
    built = await harness(max_total_chars=0)
    await built.archive.set_if_version("user_profile", "1", "x" * 5000, [], 0)
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        listed = await client.get(built.base + "/api/archives", headers={"X-Token": token})
        accepted = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 100000},
        )
    assert listed.status_code == 200
    assert listed.json()["summarize_available"] is True
    assert listed.json()["max_target_chars"] == 100000
    assert listed.json()["min_target_chars"] == 200
    # 5000 字 ≤ 100000 → no-op，但请求本身被接受（证明兜底上限生效）
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "noop"


# ── A41 / A47：快照与压缩历史 ────────────────────────────────────


async def test_compression_history_is_readonly(harness) -> None:
    built = await harness(max_total_chars=10000, provider=_KeyAwareProvider(chars=2500))
    await built.archive.set_if_version("user_profile", "1", "x" * 12000, [], 0)
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            built.base + "/api/archives/summarize",
            headers=headers,
            json={"table": "user_profile", "key": "1", "target_chars": 3000},
        )
        task = await _poll(client, built.base, token, response.json()["task_id"])
        assert task["status"] == "done"
        history = await client.get(
            built.base + "/api/archives/snapshots",
            params={"table": "user_profile", "key": "1"},
            headers={"X-Token": token},
        )
        detail = await client.get(
            built.base + "/api/archives/snapshot",
            params={"id": task["snapshot_id"]},
            headers={"X-Token": token},
        )
        missing = await client.get(
            built.base + "/api/archives/snapshot",
            params={"id": 999999},
            headers={"X-Token": token},
        )

    assert history.status_code == 200, history.text
    payload = history.json()
    assert payload["restore_supported"] is False  # 面板不提供一键恢复
    assert payload["keep_per_key"] == 10
    assert len(payload["items"]) == 1
    row = payload["items"][0]
    assert row["chars_before"] == 12000
    assert row["chars_after"] <= 3000
    assert row["reason"] == "manual"
    assert row["operator_ip"]
    assert row["created_at"]
    assert "value" not in row  # 列表不带全文

    assert detail.status_code == 200
    assert detail.json()["snapshot"]["value"] == "x" * 12000
    assert missing.status_code == 404


async def test_snapshot_history_requires_table_and_key(harness) -> None:
    built = await harness()
    token, _ = await _login(built.base)
    async with httpx.AsyncClient() as client:
        response = await client.get(
            built.base + "/api/archives/snapshots", headers={"X-Token": token}
        )
    assert response.status_code == 400


# ── A45：批量 ────────────────────────────────────────────────────


async def test_batch_over_limit_endpoint(harness) -> None:
    built = await harness(
        max_total_chars=10000, provider=_KeyAwareProvider(chars=1500)
    )
    for key in ("1", "2", "3"):
        await built.archive.set_if_version("user_profile", key, "x" * 12000, [], 0)
    # configure_overflow_policy 是同步方法（ArchiveMemoryService），不要 await
    built.archive.configure_overflow_policy(max_total_chars=10000)
    token, csrf = await _login(built.base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            built.base + "/api/archives/summarize/over-limit",
            headers=headers,
            json={"target_chars": 3000},
        )
        assert response.status_code == 202, response.text
        started = response.json()
        task = await _poll(client, built.base, token, started["task_id"])

    assert started["kind"] == "batch"
    assert started["truncated"] == 0
    assert started["skipped"] == []
    assert len(started["items"]) == 3
    assert task["status"] == "done"
    assert task["succeeded"] == 3
    assert {item["status"] for item in task["items"]} == {"done"}
    assert all(item["chars_after"] <= 3000 for item in task["items"])
    # 逐条串行：任意时刻至多 1 条在跑
    assert built.provider.max_active == 1
    assert any("面板触发批量档案压缩" in row for row in built.logger.records)

"""BUG-0038 guard tests: self-heal single-flight, daily budget, source glob confinement."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neobot_app.agents.self_heal import (
    SelfHealAgentConfig,
    SelfHealManager,
    SelfHealToolExecutor,
)


class _FakeHub:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.published = 0

    async def publish(self, **kwargs) -> None:
        self.published += 1
        if self.delay:
            await asyncio.sleep(self.delay)


class _FakeAgent:
    async def _invoke_direct(self, state) -> dict:
        return {"messages": []}


def _payload(time: str = "t0") -> dict:
    return {"time": time, "module": "test", "message": "boom", "traceback": "tb"}


def _make_manager(daily_limit: int = 5, hub_delay: float = 0.0) -> SelfHealManager:
    cfg = SelfHealAgentConfig(enabled=True, admin_account="10001", daily_limit=daily_limit)
    manager = SelfHealManager(config=cfg, notification_hub=_FakeHub(delay=hub_delay))
    manager.set_agent(_FakeAgent())
    return manager


async def test_concurrent_trigger_starts_single_heal() -> None:
    manager = _make_manager(hub_delay=0.05)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"
        await asyncio.sleep(0.05)

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]
    await manager.record(_payload("t1"))
    await manager.record(_payload("t2"))

    r1 = asyncio.create_task(manager.trigger_now(reason="r1"))
    r2 = asyncio.create_task(manager.trigger_now(reason="r2"))
    out = await asyncio.gather(r1, r2)

    assert len(heal_starts) == 1
    statuses = sorted(json.loads(o)["status"] for o in out)
    assert statuses == ["busy", "started"]


async def test_daily_limit_blocks_overflow() -> None:
    manager = _make_manager(daily_limit=2)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]

    async def trigger_once(tag: str) -> dict:
        await manager.record(_payload(tag))
        return json.loads(await manager.trigger_now(reason="manual"))

    r1 = await trigger_once("a")
    await manager._running_task
    r2 = await trigger_once("b")
    await manager._running_task
    r3 = await trigger_once("c")

    assert r1["ok"] is True
    assert r2["ok"] is True
    assert r3["ok"] is False
    assert "上限" in r3["error"]
    assert len(heal_starts) == 2


async def test_daily_budget_resets_on_new_day() -> None:
    manager = _make_manager(daily_limit=5)
    heal_starts = []

    async def _stub_run_heal(heal):
        heal_starts.append(heal.task_id)
        heal.status = "completed"

    manager._run_heal = _stub_run_heal  # type: ignore[method-assign]
    manager._trigger_date_today = "2000-01-01"
    manager._trigger_count_today = 100

    await manager.record(_payload())
    result = json.loads(await manager.trigger_now(reason="manual"))
    await manager._running_task

    assert result["ok"] is True
    assert len(heal_starts) == 1
    assert manager._trigger_count_today == 1


def _make_executor(tmp_path: Path) -> SelfHealToolExecutor:
    app_root = tmp_path / "app"
    pkg_root = tmp_path / "packages"
    (app_root / "src").mkdir(parents=True)
    (pkg_root / "src").mkdir(parents=True)
    (app_root / "src" / "manager.py").write_text(
        "def heal():\n    return 'fixed'\n", encoding="utf-8"
    )
    (pkg_root / "src" / "core.py").write_text(
        "VERSION = '1.0'\n", encoding="utf-8"
    )
    return SelfHealToolExecutor(source_roots=[app_root, pkg_root])


async def test_search_source_code_rejects_absolute_glob(tmp_path) -> None:
    outside = tmp_path / ".." / "secret.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("sk-lives-here\n", encoding="utf-8")
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({
        "pattern": "sk-",
        "path_glob": str(outside.resolve()),
    })
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_rejects_parent_traversal(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({
        "pattern": "heal",
        "path_glob": "../**/*.py",
    })
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_rejects_out_of_root_glob(tmp_path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "secret.env").write_text("KEY=123\n", encoding="utf-8")
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({
        "pattern": "KEY",
        "path_glob": "data/**/*.env",
    })
    data = json.loads(out)
    assert data["ok"] is False
    assert "越界" in data["error"]


async def test_search_source_code_accepts_in_root_glob(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({
        "pattern": "heal",
        "path_glob": "app/**/*.py",
    })
    data = json.loads(out)
    assert data["ok"] is True
    assert data["match_count"] == 1
    assert "manager.py" in data["matches"][0]["path"]


async def test_search_source_code_default_globs_scan_both_roots(tmp_path) -> None:
    executor = _make_executor(tmp_path)
    out = await executor._execute_search_source_code({"pattern": "VERSION"})
    data = json.loads(out)
    assert data["ok"] is True
    assert data["match_count"] == 1


class _FakeFailingAgent:
    """假自修复 Agent：_invoke_direct 直接抛错。"""

    async def _invoke_direct(self, state) -> dict:
        raise RuntimeError("heal exploded")


class _FakeBlockingAgent:
    """假自修复 Agent：_invoke_direct 阻塞等待 release 事件。"""

    def __init__(self) -> None:
        self.release = asyncio.Event()

    async def _invoke_direct(self, state) -> dict:
        await self.release.wait()
        return {"messages": []}


async def test_shutdown_is_idempotent_and_clears_state() -> None:
    """连续调用 shutdown() 不得抛错，且清空运行任务与错误缓冲。"""
    manager = _make_manager()
    await manager.record(_payload("t1"))
    assert len(manager._buffer) == 1

    await manager.shutdown()
    assert manager._running_task is None
    assert manager._current_heal is None
    assert len(manager._buffer) == 0

    await manager.shutdown()
    assert manager._running_task is None


async def test_shutdown_cancels_running_heal_task() -> None:
    """shutdown() 必须取消正在运行的自修复任务并复位全部状态。"""
    manager = _make_manager()
    manager._agent = _FakeBlockingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="manual"))
    assert result["ok"] is True
    running = manager._running_task
    assert running is not None and not running.done()

    await manager.shutdown()
    assert running.cancelled()
    assert manager._running_task is None
    assert manager._current_heal is None
    assert len(manager._buffer) == 0


async def test_run_heal_exception_marks_failed_and_recovers_state() -> None:
    """_run_heal 抛错后任务必须标记 failed、记录摘要并清空当前任务引用。"""
    manager = _make_manager()
    manager._agent = _FakeFailingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="boom"))
    assert result["ok"] is True
    heal = manager._current_heal
    assert heal is not None

    await manager._running_task
    assert heal.status == "failed"
    assert "RuntimeError" in heal.summary
    assert manager._current_heal is None


async def test_run_heal_completion_clears_running_task() -> None:
    """自修复任务结束后 manager._running_task 必须恢复为 None。"""
    manager = _make_manager()
    manager._agent = _FakeFailingAgent()  # type: ignore[assignment]
    await manager.record(_payload("t1"))

    result = json.loads(await manager.trigger_now(reason="boom"))
    assert result["ok"] is True
    assert manager._running_task is not None

    await manager._running_task
    assert manager._running_task is None

"""资源索引抽象(IndexRunner)单元测试。"""

from __future__ import annotations

import pytest

from neobot_app.indexer import IndexRunner, IndexTask, build_init_runner


def _sync_scan(force: bool) -> dict:
    return {"force": force, "scanned": 1}


async def _async_scan(force: bool) -> dict:
    return {"force": force, "async": True}


def test_register_and_run_sync() -> None:
    runner = IndexRunner()
    runner.register(IndexTask("t1", "任务1", _sync_scan))
    reports = runner.run_sync(force=True)
    assert len(reports) == 1
    assert reports[0]["task"] == "t1"
    assert reports[0]["report"] == {"force": True, "scanned": 1}


def test_duplicate_name_rejected() -> None:
    runner = IndexRunner()
    runner.register(IndexTask("t1", "任务1", _sync_scan))
    with pytest.raises(ValueError, match="已注册"):
        runner.register(IndexTask("t1", "任务1", _sync_scan))


async def test_run_async_tasks() -> None:
    runner = IndexRunner()
    runner.register(IndexTask("t1", "任务1", _sync_scan))
    runner.register(IndexTask("t2", "任务2", _async_scan))
    reports = await runner.run()
    assert len(reports) == 2
    by_name = {r["task"]: r["report"] for r in reports}
    assert by_name["t1"]["scanned"] == 1
    assert by_name["t2"]["async"] is True


def test_run_sync_skips_async_tasks() -> None:
    runner = IndexRunner()
    runner.register(IndexTask("t1", "任务1", _async_scan))
    reports = runner.run_sync()
    assert len(reports) == 1
    assert reports[0]["skipped"] is True


def test_describe() -> None:
    runner = IndexRunner()
    runner.register(IndexTask("t1", "任务1", _sync_scan))
    assert "t1: 任务1" in runner.describe()


def test_build_init_runner_with_service() -> None:
    class _Service:
        def refresh(self, force: bool = False) -> dict:
            return {"ok": True}

    runner = build_init_runner(vision_detect_service=_Service())
    assert "vision_detect" in runner.names()
    reports = runner.run_sync()
    assert reports[0]["report"] == {"ok": True}


def test_build_init_runner_empty() -> None:
    runner = build_init_runner(vision_detect_service=None)
    assert runner.names() == []
    assert "(没有已注册的索引任务)" in runner.describe()

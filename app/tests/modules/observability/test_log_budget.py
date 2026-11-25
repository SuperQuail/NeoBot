"""日志目录体积预算：超过上限时按最旧优先删除轮转文件。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import loguru
import pytest

from neobot_app.config.schemas.bot_parts.runtime import Debug
from neobot_app.observability import logging as logging_module
from neobot_app.observability.logging import (
    LOG_MAX_TOTAL_MB_DEFAULT,
    configure_loguru,
    enforce_log_size_budget,
    set_log_size_budget,
)


def _write(path: Path, size: int, *, age_seconds: float = 0.0) -> Path:
    path.write_bytes(b"x" * size)
    if age_seconds:
        stamp = time.time() - age_seconds
        os.utime(path, (stamp, stamp))
    return path


@pytest.fixture(autouse=True)
def _reset_budget_state() -> None:
    """预算状态是模块级的：每个用例前后都清回「未设置」，避免互相影响。"""
    logging_module.set_log_size_budget(0)
    yield
    logging_module.set_log_size_budget(0)
    configure_loguru()


def test_default_budget_is_500_mb_and_configured() -> None:
    assert LOG_MAX_TOTAL_MB_DEFAULT == 500
    assert Debug().log_max_total_mb == 500


def test_under_budget_keeps_everything(tmp_path: Path) -> None:
    current = _write(tmp_path / "neobot.log", 100)
    assert enforce_log_size_budget(tmp_path, 1000) == 0
    assert current.exists()


def test_deletes_oldest_until_under_budget(tmp_path: Path) -> None:
    oldest = _write(tmp_path / "neobot.1.log", 400, age_seconds=300)
    older = _write(tmp_path / "neobot.2.log", 400, age_seconds=200)
    newer = _write(tmp_path / "neobot.3.log", 400, age_seconds=100)
    current = _write(tmp_path / "neobot.log", 400)

    assert enforce_log_size_budget(tmp_path, 900) == 2
    assert not oldest.exists() and not older.exists()
    assert newer.exists() and current.exists()


def test_never_deletes_current_file_even_when_over_budget(tmp_path: Path) -> None:
    current = _write(tmp_path / "neobot.log", 2000)
    assert enforce_log_size_budget(tmp_path, 100) == 0
    assert current.exists()


def test_ignores_unrelated_files_and_disabled_budget(tmp_path: Path) -> None:
    other = _write(tmp_path / "notes.txt", 5000)
    _write(tmp_path / "neobot.log", 100)
    assert enforce_log_size_budget(tmp_path, 0) == 0
    assert other.exists()


def test_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    assert enforce_log_size_budget(tmp_path / "nope", 1) == 0


def test_set_budget_prunes_immediately(tmp_path: Path) -> None:
    configure_loguru(tmp_path)
    stale = _write(tmp_path / "neobot.old.log", 2 * 1024 * 1024, age_seconds=3600)

    set_log_size_budget(1)

    assert not stale.exists()
    assert (tmp_path / "neobot.log").exists()


def test_file_sink_write_enforces_budget(tmp_path: Path) -> None:
    configure_loguru(tmp_path)
    set_log_size_budget(1)
    stale = _write(tmp_path / "neobot.older.log", 2 * 1024 * 1024, age_seconds=7200)
    # 跳过小时节流，模拟「一小时后又开始写日志」
    logging_module._log_budget_checked_at = 0.0

    loguru.logger.info("触发一次文件写入")

    assert not stale.exists()
    assert "触发一次文件写入" in (tmp_path / "neobot.log").read_text(encoding="utf-8")
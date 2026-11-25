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


def test_default_budget_is_500_mb_and_configured() -> None:
    assert LOG_MAX_TOTAL_MB_DEFAULT == 500
    assert Debug().log_max_total_mb == 500


def test_under_budget_keeps_everything(tmp_path: Path) -> None:
    current = _write(tmp_path / "neobot.log", 100)
    assert enforce_log_size_budget(tmp_path, 1000) == 0
    assert current.exists()


def test_budget_boundary_is_inclusive(tmp_path: Path) -> None:
    rotated = _write(tmp_path / "neobot.1.log", 400, age_seconds=100)
    current = _write(tmp_path / "neobot.log", 600)

    # 恰好等于预算不删（`<=` 改成 `<` 会让这里先删一个）
    assert enforce_log_size_budget(tmp_path, 1000) == 0
    assert rotated.exists() and current.exists()

    assert enforce_log_size_budget(tmp_path, 999) == 1
    assert not rotated.exists()


def test_deletes_oldest_by_mtime_not_name_or_size(tmp_path: Path) -> None:
    # 文件名与体积顺序故意和 mtime 相反：只有「按 mtime 最旧优先」才删 z
    oldest = _write(tmp_path / "neobot.z.log", 600, age_seconds=300)
    newest = _write(tmp_path / "neobot.a.log", 200, age_seconds=10)
    current = _write(tmp_path / "neobot.log", 300)

    assert enforce_log_size_budget(tmp_path, 700) == 1
    assert not oldest.exists()
    assert newest.exists() and current.exists()


def test_never_deletes_current_file_even_when_over_budget(tmp_path: Path) -> None:
    current = _write(tmp_path / "neobot.log", 2000)
    assert enforce_log_size_budget(tmp_path, 100) == 0
    assert current.exists()


def test_only_neobot_files_count_and_are_deleted(tmp_path: Path) -> None:
    # 无关文件比日志更旧更大：如果实现没做名称过滤，会先删它
    other = _write(tmp_path / "notes.txt", 5000, age_seconds=400)
    stale = _write(tmp_path / "neobot.old.log", 5000, age_seconds=300)
    _write(tmp_path / "neobot.log", 100)

    assert enforce_log_size_budget(tmp_path, 4000) == 1
    assert not stale.exists()
    assert other.exists()


def test_zero_budget_never_deletes(tmp_path: Path) -> None:
    stale = _write(tmp_path / "neobot.old.log", 5000, age_seconds=300)
    _write(tmp_path / "neobot.log", 100)

    assert enforce_log_size_budget(tmp_path, 0) == 0
    assert stale.exists()


def test_missing_directory_is_not_an_error(tmp_path: Path) -> None:
    assert enforce_log_size_budget(tmp_path / "nope", 1) == 0


def test_set_budget_prunes_immediately(tmp_path: Path) -> None:
    configure_loguru(tmp_path)
    stale = _write(tmp_path / "neobot.old.log", 2 * 1024 * 1024, age_seconds=3600)

    set_log_size_budget(1)

    assert not stale.exists()
    assert (tmp_path / "neobot.log").exists()


def test_budget_check_is_throttled_to_hourly(tmp_path: Path) -> None:
    configure_loguru(tmp_path)
    set_log_size_budget(1)
    late = _write(tmp_path / "neobot.late.log", 2 * 1024 * 1024, age_seconds=60)

    loguru.logger.info("第一次写入：还在小时节流窗口内")

    # 刚检查过就不再扫目录（去掉节流会让这里立刻删掉）
    assert late.exists()

    logging_module._log_budget_checked_at = 0.0
    loguru.logger.info("第二次写入：节流窗口已过")

    assert not late.exists()
    assert "第二次写入：节流窗口已过" in (tmp_path / "neobot.log").read_text(encoding="utf-8")
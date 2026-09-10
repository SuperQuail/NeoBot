"""原子写入：写一半被杀不能污染原文件。

面板的 stats.json、文件服务器元数据这类小文件以前是直接 ``open(..., "w")``，
进程在写一半时被结束（崩溃 / 断电 / 任务管理器）就留下被截断的 JSON，下次启动
解析失败、统计清零。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import neobot_app.utils.atomic as atomic
from neobot_app.builtin_plugins.dashboard.metrics import Metrics
from neobot_app.utils.atomic import atomic_write_text


def test_atomic_write_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "stats.json"

    atomic_write_text(target, '{"total": 1}')
    atomic_write_text(target, '{"total": 2}')

    assert target.read_text(encoding="utf-8") == '{"total": 2}'
    assert [item.name for item in tmp_path.iterdir()] == ["stats.json"]


def test_atomic_write_retries_transient_windows_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """目标被短时占用（WinError 5）时应重试成功，而不是把保存直接判失败。"""
    target = tmp_path / "config.toml"
    target.write_text("old", encoding="utf-8")
    calls = {"count": 0}
    real_replace = atomic.os.replace

    def flaky(src: object, dst: object) -> None:
        calls["count"] += 1
        if calls["count"] < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(atomic.os, "replace", flaky)
    monkeypatch.setattr(atomic.time, "sleep", lambda _seconds: None)

    atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "new"
    assert calls["count"] == 3


def test_atomic_write_keeps_original_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "stats.json"
    target.write_text('{"total": 1}', encoding="utf-8")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(atomic.os, "replace", boom)
    monkeypatch.setattr(atomic.time, "sleep", lambda _seconds: None)

    with pytest.raises(OSError):
        atomic_write_text(target, '{"total": 2}')

    assert target.read_text(encoding="utf-8") == '{"total": 1}'
    # 临时文件不能留在数据目录里
    assert [item.name for item in tmp_path.iterdir()] == ["stats.json"]


def test_metrics_save_does_not_raise_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metrics = Metrics(data_dir=tmp_path)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "neobot_app.builtin_plugins.dashboard.metrics.atomic_write_text", boom
    )

    metrics.flush()

    assert not (tmp_path / "stats.json").exists()

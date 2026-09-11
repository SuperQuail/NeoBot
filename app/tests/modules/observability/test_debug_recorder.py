"""DebugRecorder 测试:数据包记录过滤(元事件)、按天分片与保留期清理。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from neobot_app.observability.debug import (
    DEFAULT_RETENTION_DAYS,
    DebugRecorder,
)
from neobot_app.time_context import now_utc


def _packets_file(log_dir: Path) -> Path:
    """当天分片文件 packets-YYYYMMDD.jsonl。"""
    files = sorted(log_dir.glob("packets-*.jsonl"))
    assert files, "未生成当天的 packets 分片"
    return files[-1]


def _age(path: Path, days: float) -> None:
    """把文件修改时间改成 days 天前（保留期按修改时间判定）。"""
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))


def test_record_packet_skips_meta_events(tmp_path) -> None:
    """周期性元事件(心跳/生命周期)不写日志也不写调试包文件，避免刷屏。"""
    logger = Mock()
    recorder = DebugRecorder(tmp_path, logger=logger)

    recorder.record_packet({"post_type": "meta_event", "meta_event_type": "heartbeat"})
    recorder.record_packet({"post_type": "meta_event", "meta_event_type": "lifecycle"})

    # 初始化日志之外的 debug 调用中不得出现"记录数据包"
    assert all(
        call.args[:1] != ("记录数据包",) for call in logger.debug.call_args_list
    )
    assert not list(tmp_path.glob("packets-*.jsonl"))


def test_record_packet_writes_non_meta_events(tmp_path) -> None:
    """普通事件照常记录日志与调试包。"""
    logger = Mock()
    recorder = DebugRecorder(tmp_path, logger=logger)

    recorder.record_packet({"post_type": "message", "message_type": "group"})

    logger.debug.assert_any_call("记录数据包", post_type="message")
    lines = _packets_file(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["packet"]["post_type"] == "message"


def test_packets_are_split_by_day(tmp_path) -> None:
    """调试数据按天分片，旧分片可以整文件清理，不再写单个无限增长的 jsonl。"""
    recorder = DebugRecorder(tmp_path, logger=Mock())

    recorder.record_packet({"post_type": "message"})

    # 分片名用的是 UTC 日期（DebugRecorder._jsonl_path），本机时区为 UTC+8 时
    # 本地时间 00:00-08:00 之间两者不是同一天，必须按同一个时钟取期望值。
    expected = f"packets-{now_utc().strftime('%Y%m%d')}.jsonl"
    assert _packets_file(tmp_path).name == expected
    assert not (tmp_path / "packets.jsonl").exists()


def test_init_prunes_files_older_than_retention(tmp_path) -> None:
    """初始化时清理超过保留期的数据包分片与回复事件明细。"""
    log_dir = tmp_path / "log"
    reply_dir = log_dir / "reply_events"
    reply_dir.mkdir(parents=True)
    old_packet = log_dir / "packets-20200101.jsonl"
    old_packet.write_text("{}\n", encoding="utf-8")
    _age(old_packet, DEFAULT_RETENTION_DAYS + 1)
    fresh_packet = log_dir / "packets-20990101.jsonl"
    fresh_packet.write_text("{}\n", encoding="utf-8")
    old_event = reply_dir / "2020-1-1-0-0-abcdef.md"
    old_event.write_text("# old\n", encoding="utf-8")
    _age(old_event, DEFAULT_RETENTION_DAYS + 1)
    fresh_event = reply_dir / "2099-1-1-0-0-abcdef.md"
    fresh_event.write_text("# fresh\n", encoding="utf-8")

    logger = Mock()
    DebugRecorder(log_dir, logger=logger, retention_days=DEFAULT_RETENTION_DAYS)

    assert not old_packet.exists()
    assert not old_event.exists()
    assert fresh_packet.exists()
    assert fresh_event.exists()
    prune_logs = [
        call
        for call in logger.info.call_args_list
        if call.args[:1] == ("DebugRecorder 已清理过期调试数据",)
    ]
    assert prune_logs and prune_logs[0].kwargs == {
        "removed": 2,
        "retention_days": DEFAULT_RETENTION_DAYS,
    }


def test_retention_window_keeps_recent_data(tmp_path) -> None:
    """保留期内（10 天以内）的数据必须保留。"""
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    inside = log_dir / "packets-20200101.jsonl"
    inside.write_text("{}\n", encoding="utf-8")
    _age(inside, DEFAULT_RETENTION_DAYS - 0.5)

    DebugRecorder(log_dir, logger=Mock(), retention_days=DEFAULT_RETENTION_DAYS)

    assert inside.exists()


def test_prune_runs_at_most_hourly_but_can_be_forced(tmp_path) -> None:
    """写入路径最多每小时清理一次，force=True 立即清理。"""
    recorder = DebugRecorder(tmp_path, logger=Mock())
    expired = tmp_path / "packets-20200101.jsonl"
    expired.write_text("{}\n", encoding="utf-8")
    _age(expired, DEFAULT_RETENTION_DAYS + 1)

    recorder.record_packet({"post_type": "message"})
    assert expired.exists(), "刚初始化过就不该再扫目录"

    assert recorder.prune_expired(force=True) == 1
    assert not expired.exists()


def test_retention_days_must_be_positive(tmp_path) -> None:
    """保留天数必须为正，避免配置成 0 后重新变成无限增长。"""
    with pytest.raises(ValueError):
        DebugRecorder(tmp_path, logger=Mock(), retention_days=0)

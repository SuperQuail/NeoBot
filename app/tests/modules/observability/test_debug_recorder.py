"""DebugRecorder 测试:数据包记录过滤(元事件)与调试包写入。"""

from __future__ import annotations

import json
from unittest.mock import Mock

from neobot_app.observability.debug import DebugRecorder


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
    assert not (tmp_path / "packets.jsonl").exists()


def test_record_packet_writes_non_meta_events(tmp_path) -> None:
    """普通事件照常记录日志与调试包。"""
    logger = Mock()
    recorder = DebugRecorder(tmp_path, logger=logger)

    recorder.record_packet({"post_type": "message", "message_type": "group"})

    logger.debug.assert_any_call("记录数据包", post_type="message")
    lines = (tmp_path / "packets.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["packet"]["post_type"] == "message"

"""FreezeService 状态机测试:冻结、解冻、自动到期与状态快照。"""

from __future__ import annotations

import pytest

from neobot_app.runtime.freeze_service import FreezeService


def test_initially_not_frozen():
    service = FreezeService()
    assert service.is_frozen() is False
    assert service.remaining_seconds() is None
    assert service.status() == {
        "frozen": False,
        "reason": "",
        "operator": "",
        "frozen_at": None,
        "frozen_at_text": "",
        "frozen_for_seconds": 0,
        "remaining_seconds": None,
    }


def test_freeze_and_unfreeze_round_trip():
    service = FreezeService()
    ok, message = service.freeze(reason="token 风暴", operator="panel")
    assert ok is True
    assert "已冻结" in message
    assert service.is_frozen() is True

    ok, message = service.unfreeze(reason="manual")
    assert ok is True
    assert "已解冻" in message
    assert service.is_frozen() is False


def test_unfreeze_without_freeze_reports_noop():
    service = FreezeService()
    ok, message = service.unfreeze()
    assert ok is False
    assert "没有处于冻结状态" in message


def test_repeated_freeze_keeps_original_start_time():
    """事故中反复确认状态不能重置已冻结时长(否则状态会一直显示刚开始)。"""
    service = FreezeService()
    service.freeze(reason="first")
    first_at = service.status()["frozen_at"]
    ok, message = service.freeze(reason="second")
    assert ok is True
    assert "已再次确认" in message
    assert service.status()["frozen_at"] == first_at
    assert service.status()["reason"] == "second"


def test_freeze_with_duration_expires_automatically(monkeypatch):
    """带时长冻结到期后必须自动解冻,避免把 Bot 永久停住。"""
    import neobot_app.runtime.freeze_service as module

    clock = {"now": 1000.0}
    monkeypatch.setattr(module, "monotonic_seconds", lambda: clock["now"])

    service = FreezeService()
    service.freeze(reason="auto", seconds=60)
    assert service.is_frozen() is True
    assert service.remaining_seconds() == 60

    clock["now"] += 61
    assert service.is_frozen() is False
    assert service.remaining_seconds() is None


def test_freeze_rejects_non_positive_duration():
    service = FreezeService()
    ok, message = service.freeze(seconds=0)
    assert ok is False
    assert "必须大于 0" in message
    assert service.is_frozen() is False


def test_freeze_respects_max_seconds():
    service = FreezeService(max_seconds=3600)
    ok, message = service.freeze(seconds=7200)
    assert ok is False
    assert "最多 1 小时" in message


@pytest.mark.parametrize("seconds", [30.0, 1800.0])
def test_freeze_duration_message_mentions_auto_unfreeze(seconds: float):
    service = FreezeService()
    ok, message = service.freeze(seconds=seconds)
    assert ok is True
    assert "自动解冻" in message

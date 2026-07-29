from __future__ import annotations

import time

from neobot_adapter.onebot.adapter import OneBotAdapter
from neobot_adapter.onebot.receiver.core import AdapterCore


def test_onebot_connected_reflects_active_websocket() -> None:
    adapter = OneBotAdapter()
    assert adapter.connected is False
    marker = object()
    adapter.core.active_connections.add(marker)
    assert adapter.connected is True
    adapter.core.active_connections.remove(marker)
    assert adapter.connected is False


def test_onebot_receiver_stop_wakes_thread_and_clears_reference(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NEO_BOT_ADAPTER_HOST", "127.0.0.1")
    monkeypatch.setenv("NEO_BOT_ADAPTER_PORT", "0")
    core = AdapterCore()
    core.start()

    deadline = time.monotonic() + 3
    while core._async_stop_event is None and time.monotonic() < deadline:
        time.sleep(0.01)

    started = time.monotonic()
    assert core.stop(timeout=3.0) is True
    assert time.monotonic() - started < 3.0
    assert core.thread is None

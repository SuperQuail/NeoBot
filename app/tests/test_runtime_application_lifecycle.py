from __future__ import annotations

import asyncio

import pytest

from neobot_app.runtime.application import NeoBotApplication
from neobot_contracts.ports.logging import NullLogger


def test_restart_request_is_distinct_from_normal_stop() -> None:
    application = object.__new__(NeoBotApplication)
    application._shutdown_event = asyncio.Event()
    application._restart_requested = False

    application.request_restart()
    assert application.restart_requested is True
    assert application._shutdown_event.is_set()

    application.request_stop()
    assert application.restart_requested is False


@pytest.mark.asyncio
async def test_adapter_shutdown_has_timeout_fallback() -> None:
    class HangingAdapter:
        def __init__(self) -> None:
            self.cancelled = False

        async def stop(self) -> None:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    application = object.__new__(NeoBotApplication)
    application.adapter = HangingAdapter()
    application._logger = NullLogger()
    application._ADAPTER_STOP_TIMEOUT_SECONDS = 0.01

    await application._stop_adapter_with_timeout()

    assert application.adapter.cancelled is True

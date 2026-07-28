from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.onebot.receiver.core import AdapterCore
from neobot_adapter.request.websocket import WebSocketAPI


@pytest.mark.asyncio
async def test_adapter_core_sends_raw_payload_to_explicit_websocket():
    core = AdapterCore()
    websocket = AsyncMock()

    sent = await core.send_message({"action": "ping", "params": {}}, websocket)

    assert sent is True
    websocket.send.assert_awaited_once()
    assert json.loads(websocket.send.await_args.args[0]) == {
        "action": "ping",
        "params": {},
    }


@pytest.mark.asyncio
async def test_adapter_core_reports_missing_connection():
    core = AdapterCore()

    sent = await core.send_message({"action": "ping"})

    assert sent is False


@pytest.mark.asyncio
async def test_websocket_api_propagates_send_failure():
    core = AsyncMock()
    core.send_message.return_value = False
    api = WebSocketAPI(core)

    sent = await api.send_message({"action": "ping"})

    assert sent is False

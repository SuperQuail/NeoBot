"""网关 HTTP 端点：认证、错误码与长轮询（真实 aiohttp TestServer）。"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from neobot_contracts.ports.logging import NullLogger

from neobot_app.config.schemas.bot_parts.dsh import DshGatewayConfig
from neobot_app.dsh_gateway.models import DaemonCommand, SyncReport
from neobot_app.dsh_gateway.server import HEALTH_PATH, SYNC_PATH, DshGatewayServer
from neobot_app.dsh_gateway.service import DshGatewayService

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class _RecordingHandler:
    def __init__(self) -> None:
        self.received: list[tuple[str, list[SyncReport]]] = []
        self.outbox: list[DaemonCommand] = []

    async def on_reports(self, daemon_id: str, reports: list[SyncReport]) -> None:
        self.received.append((daemon_id, list(reports)))

    async def drain_commands(self, daemon_id: str) -> list[DaemonCommand]:
        commands, self.outbox = self.outbox, []
        return commands


def _config(**overrides) -> DshGatewayConfig:
    values = {
        "enabled": True,
        "host": "127.0.0.1",
        "port": 0,
        "token": TOKEN,
        "allow_ips": [],
        "max_body_bytes": 1024 * 1024,
        "poll_wait_seconds": 0,
    }
    values.update(overrides)
    return DshGatewayConfig(**values)


def _payload(**overrides):
    payload = {
        "v": 1,
        "daemon_id": "devbox-1",
        "seq": 1,
        "cursor": 0,
        "reports": [
            {
                "id": "r-1",
                "kind": "task.event",
                "task_id": "t-1",
                "payload": {"status": "running"},
            }
        ],
        "health": {"sessions": 1},
    }
    payload.update(overrides)
    return payload


@pytest.fixture
async def make_gateway():
    clients: list[TestClient] = []

    async def create(**overrides) -> SimpleNamespace:
        service = DshGatewayService(logger=NullLogger())
        handler = _RecordingHandler()
        service.register_handler("dsh_router", handler)
        server = DshGatewayServer(config=_config(**overrides), service=service, logger=NullLogger())
        client = TestClient(TestServer(server.make_app()))
        await client.start_server()
        clients.append(client)
        return SimpleNamespace(service=service, handler=handler, server=server, client=client)

    yield create

    for client in clients:
        await client.close()


async def _wait_connected(service: DshGatewayService, daemon_id: str, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for item in service.health_snapshot():
            if item["daemon_id"] == daemon_id and item["connected"]:
                return
        await asyncio.sleep(0.005)
    raise AssertionError(f"daemon {daemon_id} 未进入长轮询挂起状态")


async def test_sync_accepts_valid_request_and_delivers_reports(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.post(SYNC_PATH, json=_payload(seq=4), headers=AUTH)

    assert response.status == 200
    body = await response.json()
    assert body["v"] == 1
    assert body["daemon_id"] == "devbox-1"
    assert body["cursor"] == 4
    assert body["commands"] == []
    assert [(daemon, [report.id for report in reports]) for daemon, reports in gateway.handler.received] == [
        ("devbox-1", ["r-1"])
    ]


async def test_sync_returns_drained_commands(make_gateway):
    gateway = await make_gateway()
    gateway.handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch", task_id="t-1")]

    response = await gateway.client.post(SYNC_PATH, json=_payload(), headers=AUTH)

    assert response.status == 200
    body = await response.json()
    assert body["commands"] == [{"id": "c-1", "kind": "task.dispatch", "task_id": "t-1", "payload": {}}]


async def test_sync_resends_unacked_command_until_ack(make_gateway):
    gateway = await make_gateway()
    gateway.handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    first = await gateway.client.post(SYNC_PATH, json=_payload(seq=1), headers=AUTH)
    second = await gateway.client.post(SYNC_PATH, json=_payload(seq=2), headers=AUTH)
    acked = await gateway.client.post(SYNC_PATH, json=_payload(seq=3, acks=["c-1"]), headers=AUTH)
    after = await gateway.client.post(SYNC_PATH, json=_payload(seq=4), headers=AUTH)

    assert [item["id"] for item in (await first.json())["commands"]] == ["c-1"]
    assert [item["id"] for item in (await second.json())["commands"]] == ["c-1"]
    assert (await acked.json())["commands"] == []
    assert (await after.json())["commands"] == []


async def test_sync_rejects_invalid_acks(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.post(SYNC_PATH, json=_payload(acks=[""]), headers=AUTH)

    assert response.status == 400
    assert (await response.json())["error"]["code"] == "invalid_acks"


async def test_sync_rejects_missing_or_wrong_token(make_gateway):
    gateway = await make_gateway()

    missing = await gateway.client.post(SYNC_PATH, json=_payload())
    assert missing.status == 401
    assert "Bearer" in missing.headers["WWW-Authenticate"]
    assert (await missing.json())["error"]["code"] == "unauthorized"

    wrong = await gateway.client.post(
        SYNC_PATH,
        json=_payload(),
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert wrong.status == 401

    basic = await gateway.client.post(
        SYNC_PATH,
        json=_payload(),
        headers={"Authorization": "Basic dGVzdC10b2tlbg=="},
    )
    assert basic.status == 401
    assert gateway.handler.received == []


async def test_sync_rejects_ip_outside_allow_list(make_gateway):
    denied = await make_gateway(allow_ips=["10.0.0.0/8"])

    response = await denied.client.post(SYNC_PATH, json=_payload(), headers=AUTH)

    assert response.status == 403
    assert (await response.json())["error"]["code"] == "ip_not_allowed"

    allowed = await make_gateway(allow_ips=["127.0.0.1/32"])
    ok = await allowed.client.post(SYNC_PATH, json=_payload(), headers=AUTH)
    assert ok.status == 200


async def test_sync_rejects_malformed_json(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.post(
        SYNC_PATH,
        data="{not-json",
        headers={**AUTH, "Content-Type": "application/json"},
    )

    assert response.status == 400
    assert (await response.json())["error"]["code"] == "invalid_json"


async def test_sync_rejects_invalid_payload(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.post(SYNC_PATH, json={"daemon_id": "   ", "seq": 1}, headers=AUTH)

    assert response.status == 400
    assert (await response.json())["error"]["code"] == "invalid_daemon_id"


async def test_sync_rejects_unsupported_protocol_version(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.post(SYNC_PATH, json=_payload(v=2), headers=AUTH)

    assert response.status == 400
    assert (await response.json())["error"]["code"] == "unsupported_version"


async def test_sync_rejects_oversized_body(make_gateway):
    gateway = await make_gateway(max_body_bytes=64)

    response = await gateway.client.post(SYNC_PATH, json=_payload(daemon_id="d" * 200), headers=AUTH)

    assert response.status == 413
    assert (await response.json())["error"]["code"] == "payload_too_large"


async def test_long_poll_returns_command_after_notify(make_gateway):
    gateway = await make_gateway(poll_wait_seconds=5)
    started = time.monotonic()

    request = asyncio.create_task(gateway.client.post(SYNC_PATH, json=_payload(), headers=AUTH))
    await _wait_connected(gateway.service, "devbox-1")

    gateway.handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]
    gateway.service.notify("devbox-1")
    response = await asyncio.wait_for(request, timeout=2)

    assert response.status == 200
    body = await response.json()
    assert [command["id"] for command in body["commands"]] == ["c-1"]
    assert time.monotonic() - started < 2


async def test_long_poll_timeout_returns_empty_commands(make_gateway):
    gateway = await make_gateway(poll_wait_seconds=1)
    started = time.monotonic()

    response = await gateway.client.post(SYNC_PATH, json=_payload(), headers=AUTH)
    elapsed = time.monotonic() - started

    assert response.status == 200
    assert (await response.json())["commands"] == []
    assert elapsed >= 0.8


async def test_health_endpoint_returns_daemon_snapshot(make_gateway):
    gateway = await make_gateway()

    await gateway.client.post(SYNC_PATH, json=_payload(seq=3), headers=AUTH)
    response = await gateway.client.get(HEALTH_PATH, headers=AUTH)

    assert response.status == 200
    body = await response.json()
    assert body["v"] == 1
    assert body["connected"] == 0
    assert body["daemons"] == [
        {
            "daemon_id": "devbox-1",
            "last_seq": 3,
            "last_seen": body["daemons"][0]["last_seen"],
            "connected": False,
        }
    ]
    assert isinstance(body["daemons"][0]["last_seen"], float)


async def test_health_endpoint_requires_token(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.get(HEALTH_PATH)

    assert response.status == 401


async def test_unknown_path_is_404_with_valid_token(make_gateway):
    gateway = await make_gateway()

    response = await gateway.client.get("/dsh/daemon/unknown", headers=AUTH)

    assert response.status == 404


async def test_client_cancel_during_long_poll_keeps_gateway_serving(make_gateway):
    gateway = await make_gateway(poll_wait_seconds=1)

    request = asyncio.create_task(gateway.client.post(SYNC_PATH, json=_payload(), headers=AUTH))
    await _wait_connected(gateway.service, "devbox-1")

    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request

    health = await gateway.client.get(HEALTH_PATH, headers=AUTH)
    assert health.status == 200

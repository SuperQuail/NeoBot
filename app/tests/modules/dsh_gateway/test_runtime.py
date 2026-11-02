"""网关装配：开关语义、端口解析、真实启停与端口占用降级。"""

from __future__ import annotations

import socket

import aiohttp
from neobot_contracts.ports.logging import NullLogger

from neobot_app.config.schemas.bot_parts.dsh import DshGatewayConfig
from neobot_app.dsh_gateway.runtime import DshGatewayRuntime, build_gateway_runtime
from neobot_app.dsh_gateway.server import HEALTH_PATH

TOKEN = "test-token"


class _RecordingLogger(NullLogger):
    def __init__(self) -> None:
        self.records: list[tuple[str, str, dict]] = []

    def info(self, msg: str, **kw) -> None:
        self.records.append(("info", msg, kw))

    def warning(self, msg: str, **kw) -> None:
        self.records.append(("warning", msg, kw))

    def error(self, msg: str, **kw) -> None:
        self.records.append(("error", msg, kw))


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


def test_disabled_config_creates_nothing():
    assert build_gateway_runtime(config=_config(enabled=False)) is None
    assert build_gateway_runtime(config=None) is None


def test_enabled_without_token_is_refused():
    logger = _RecordingLogger()

    runtime = build_gateway_runtime(config=_config(token="   "), logger=logger)

    assert runtime is None
    assert any(level == "error" and kw.get("event") == "dsh_gateway.no_token" for level, _msg, kw in logger.records)


def test_invalid_allow_ips_is_refused():
    logger = _RecordingLogger()

    runtime = build_gateway_runtime(config=_config(allow_ips=["not-a-network"]), logger=logger)

    assert runtime is None
    assert any(
        level == "error" and kw.get("event") == "dsh_gateway.bad_allow_ips" for level, _msg, kw in logger.records
    )


def test_build_gateway_runtime_does_not_listen_before_start():
    runtime = build_gateway_runtime(config=_config(port=18791))

    assert isinstance(runtime, DshGatewayRuntime)
    assert runtime.running is False
    assert runtime.port == 18791
    assert runtime.service.handler_plugins == ()


async def test_runtime_starts_on_ephemeral_port_and_serves_health():
    runtime = build_gateway_runtime(config=_config(port=0))
    assert runtime is not None
    await runtime.start()
    try:
        assert runtime.running is True
        assert runtime.started is True
        assert runtime.port > 0

        async with aiohttp.ClientSession() as session:
            unauthorized = await session.get(f"http://127.0.0.1:{runtime.port}{HEALTH_PATH}")
            assert unauthorized.status == 401
            authorized = await session.get(
                f"http://127.0.0.1:{runtime.port}{HEALTH_PATH}",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
            assert authorized.status == 200
            body = await authorized.json()
            assert body["daemons"] == []
    finally:
        await runtime.close()

    assert runtime.running is False
    assert runtime.started is False


async def test_runtime_start_and_close_are_idempotent():
    runtime = build_gateway_runtime(config=_config(port=0))
    assert runtime is not None
    await runtime.start()
    port = runtime.port
    await runtime.start()
    assert runtime.port == port

    await runtime.close()
    await runtime.close()
    assert runtime.running is False


async def test_port_bind_failure_is_logged_and_not_raised():
    occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    occupied.bind(("127.0.0.1", 0))
    occupied.listen(1)
    port = occupied.getsockname()[1]
    logger = _RecordingLogger()
    try:
        runtime = build_gateway_runtime(config=_config(port=port), logger=logger)
        assert runtime is not None

        await runtime.start()

        assert runtime.running is False
        assert runtime.started is False
        assert any(
            level == "error" and kw.get("event") == "dsh_gateway.start_failed" for level, _msg, kw in logger.records
        )
    finally:
        occupied.close()


async def test_non_loopback_host_only_warns():
    logger = _RecordingLogger()
    runtime = build_gateway_runtime(config=_config(host="0.0.0.0", port=0), logger=logger)
    assert runtime is not None
    try:
        await runtime.start()
        assert runtime.running is True
        assert any(
            level == "warning" and kw.get("event") == "dsh_gateway.non_loopback" for level, _msg, kw in logger.records
        )
    finally:
        await runtime.close()

"""网关服务：报告去重、seq 游标、handler、命令出队、多 daemon 隔离与健康快照。"""

from __future__ import annotations

import asyncio
import time

import pytest

from neobot_app.dsh_gateway.models import DaemonCommand, SyncReport, SyncRequest
from neobot_app.dsh_gateway.service import DshGatewayService


class _RecordingHandler:
    def __init__(self) -> None:
        self.received: list[tuple[str, list[SyncReport]]] = []
        self.outbox: list[DaemonCommand] = []
        self.fail_next = False
        self.concurrent = 0
        self.max_concurrent = 0
        self.drain_calls = 0
        self.gate: asyncio.Event | None = None

    async def on_reports(self, daemon_id: str, reports: list[SyncReport]) -> None:
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            self.received.append((daemon_id, list(reports)))
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("handler boom")
            if self.gate is not None:
                await self.gate.wait()
        finally:
            self.concurrent -= 1

    async def drain_commands(self, daemon_id: str) -> list[DaemonCommand]:
        self.drain_calls += 1
        commands, self.outbox = self.outbox, []
        return commands


def _report(report_id: str = "r-1", kind: str = "task.event") -> SyncReport:
    return SyncReport(id=report_id, kind=kind, task_id="t-1", payload={"status": "running"})


def _request(daemon_id: str = "devbox-1", seq: int = 1, reports: list[SyncReport] | None = None) -> SyncRequest:
    return SyncRequest(daemon_id=daemon_id, seq=seq, reports=list(reports or []))


def _is_connected(service: DshGatewayService, daemon_id: str) -> bool:
    return any(item["daemon_id"] == daemon_id and item["connected"] for item in service.health_snapshot())


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("等待条件超时")


async def test_sync_delivers_new_reports_and_advances_cursor():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    response = await service.sync(_request(seq=3, reports=[_report()]))

    assert response.daemon_id == "devbox-1"
    assert response.cursor == 3
    assert [(daemon, [item.id for item in reports]) for daemon, reports in handler.received] == [("devbox-1", ["r-1"])]
    snapshot = service.health_snapshot()
    assert len(snapshot) == 1
    assert snapshot[0]["daemon_id"] == "devbox-1"
    assert snapshot[0]["last_seq"] == 3
    assert snapshot[0]["connected"] is False
    assert isinstance(snapshot[0]["last_seen"], float)


async def test_duplicate_seq_is_not_delivered_twice():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    await service.sync(_request(seq=5, reports=[_report("r-1")]))
    duplicate = await service.sync(_request(seq=5, reports=[_report("r-1")]))
    stale = await service.sync(_request(seq=4, reports=[_report("r-0")]))

    assert len(handler.received) == 1
    assert duplicate.cursor == 5
    assert stale.cursor == 5


async def test_first_sync_with_zero_seq_delivers_reports():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    first = await service.sync(_request(seq=0, reports=[_report()]))
    duplicate = await service.sync(_request(seq=0, reports=[_report()]))

    assert first.cursor == 0
    assert duplicate.cursor == 0
    assert len(handler.received) == 1


async def test_commands_are_drained_on_every_sync():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch"), DaemonCommand(id="c-2", kind="task.cancel")]

    first = await service.sync(_request(seq=1))
    second = await service.sync(_request(seq=2))

    assert [command.id for command in first.commands] == ["c-1", "c-2"]
    # 未 ack 的命令下一轮重发（顺序保持首次下发顺序）。
    assert [command.id for command in second.commands] == ["c-1", "c-2"]

    acked = await service.sync(SyncRequest(daemon_id="devbox-1", seq=3, acks=["c-1", "c-2"]))
    assert acked.commands == []

    handler.outbox = [DaemonCommand(id="c-3", kind="task.dispatch")]
    third = await service.sync(_request(seq=4))
    assert [command.id for command in third.commands] == ["c-3"]


async def test_unacked_command_is_resent_next_sync():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    first = await service.sync(_request(seq=1))
    second = await service.sync(_request(seq=2))
    third = await service.sync(_request(seq=3, reports=[_report()]))

    assert [command.id for command in first.commands] == ["c-1"]
    assert [command.id for command in second.commands] == ["c-1"]
    assert [command.id for command in third.commands] == ["c-1"]
    # 只 drain 一次：重发来自 pending，而不是重复入队。
    assert handler.drain_calls == 3


async def test_ack_stops_resending():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    await service.sync(_request(seq=1))
    acked = await service.sync(SyncRequest(daemon_id="devbox-1", seq=2, acks=["c-1"]))
    after = await service.sync(_request(seq=3))

    assert acked.commands == []
    assert after.commands == []


async def test_duplicate_and_unknown_acks_are_harmless():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    await service.sync(_request(seq=1))
    response = await service.sync(SyncRequest(daemon_id="devbox-1", seq=2, acks=["c-1", "c-1", "never-issued"]))
    response_again = await service.sync(SyncRequest(daemon_id="devbox-1", seq=3, acks=["c-1", "never-issued"]))

    assert response.commands == []
    assert response_again.commands == []
    assert service.health_snapshot()[0]["last_seq"] == 3


async def test_long_poll_returns_pending_command_immediately():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    first = await service.sync(_request(seq=1))
    assert [command.id for command in first.commands] == ["c-1"]

    started = time.monotonic()
    pending = await service.wait_for_commands("devbox-1", 5)

    assert [command.id for command in pending] == ["c-1"]
    assert time.monotonic() - started < 1


async def test_pending_overflow_drops_oldest(monkeypatch):
    from neobot_app.dsh_gateway import service as service_module

    monkeypatch.setattr(service_module, "MAX_PENDING_COMMANDS", 2)
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [
        DaemonCommand(id="c-1", kind="task.dispatch"),
        DaemonCommand(id="c-2", kind="task.dispatch"),
        DaemonCommand(id="c-3", kind="task.dispatch"),
    ]

    response = await service.sync(_request(seq=1))

    assert [command.id for command in response.commands] == ["c-2", "c-3"]


async def test_command_without_id_is_delivered_once_but_not_tracked():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="", kind="task.dispatch")]

    first = await service.sync(_request(seq=1))
    second = await service.sync(_request(seq=2))

    assert [command.kind for command in first.commands] == ["task.dispatch"]
    assert second.commands == []


async def test_sync_without_handler_still_advances_cursor():
    service = DshGatewayService()

    response = await service.sync(_request(seq=2, reports=[_report()]))

    assert response.cursor == 2
    assert response.commands == []


async def test_duplicate_reports_still_drain_commands():
    """daemon 因响应丢失重发 seq 时，未取走的命令要照常下发。"""
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    await service.sync(_request(seq=1))
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]
    duplicate = await service.sync(_request(seq=1, reports=[_report()]))

    assert duplicate.cursor == 1
    assert [command.id for command in duplicate.commands] == ["c-1"]
    assert handler.received == []


async def test_daemons_are_isolated():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    await service.sync(_request(daemon_id="devbox-a", seq=7, reports=[_report("a-1")]))
    await service.sync(_request(daemon_id="devbox-b", seq=1, reports=[_report("b-1")]))

    snapshot = {item["daemon_id"]: item for item in service.health_snapshot()}
    assert snapshot["devbox-a"]["last_seq"] == 7
    assert snapshot["devbox-b"]["last_seq"] == 1
    assert [daemon for daemon, _reports in handler.received] == ["devbox-a", "devbox-b"]


async def test_register_and_unregister_handler():
    handler = _RecordingHandler()
    service = DshGatewayService()

    service.register_handler("dsh_router", handler)
    assert service.handler_plugins == ("dsh_router",)
    assert service.unregister_handler("dsh_router") is True
    assert service.unregister_handler("dsh_router") is False

    await service.sync(_request(seq=1, reports=[_report()]))
    assert handler.received == []


def test_register_handler_validates_arguments():
    service = DshGatewayService()

    with pytest.raises(ValueError, match="plugin_name"):
        service.register_handler("  ", _RecordingHandler())
    with pytest.raises(TypeError, match="on_reports"):
        service.register_handler("broken", object())


async def test_handler_failure_does_not_advance_cursor():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.fail_next = True

    with pytest.raises(RuntimeError, match="handler boom"):
        await service.sync(_request(seq=3, reports=[_report()]))
    assert service.health_snapshot()[0]["last_seq"] == 0

    retry = await service.sync(_request(seq=3, reports=[_report()]))
    assert retry.cursor == 3
    assert len(handler.received) == 2


async def test_same_daemon_sync_is_serialized():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.gate = asyncio.Event()

    first = asyncio.create_task(service.sync(_request(seq=1, reports=[_report()])))
    await _wait_until(lambda: handler.concurrent == 1)
    second = asyncio.create_task(service.sync(_request(seq=2, reports=[_report("r-2")])))
    await asyncio.sleep(0.05)

    assert handler.max_concurrent == 1
    assert not second.done()

    handler.gate.set()
    await asyncio.gather(first, second)

    assert handler.max_concurrent == 1
    assert [item["last_seq"] for item in service.health_snapshot()] == [2]


async def test_notify_wakes_long_poll_with_command():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)

    started = time.monotonic()
    waiter = asyncio.create_task(service.wait_for_commands("devbox-1", 5))
    await _wait_until(lambda: _is_connected(service, "devbox-1"))

    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]
    service.notify("devbox-1")
    commands = await asyncio.wait_for(waiter, timeout=2)

    assert [command.id for command in commands] == ["c-1"]
    assert time.monotonic() - started < 2


async def test_wait_for_commands_times_out_empty():
    service = DshGatewayService()

    started = time.monotonic()
    commands = await service.wait_for_commands("devbox-1", 0.05)
    elapsed = time.monotonic() - started

    assert commands == []
    assert elapsed >= 0.04


async def test_wait_for_commands_returns_pending_command_immediately():
    handler = _RecordingHandler()
    service = DshGatewayService()
    service.register_handler("dsh_router", handler)
    handler.outbox = [DaemonCommand(id="c-1", kind="task.dispatch")]

    started = time.monotonic()
    commands = await service.wait_for_commands("devbox-1", 5)

    assert [command.id for command in commands] == ["c-1"]
    assert time.monotonic() - started < 1


async def test_health_snapshot_marks_connected_during_long_poll():
    service = DshGatewayService()

    waiter = asyncio.create_task(service.wait_for_commands("devbox-1", 5))
    await _wait_until(lambda: _is_connected(service, "devbox-1"))

    snapshot = service.health_snapshot()[0]
    assert snapshot["daemon_id"] == "devbox-1"
    assert snapshot["connected"] is True
    assert snapshot["last_seen"] is not None

    service.notify("devbox-1")
    await asyncio.wait_for(waiter, timeout=2)
    assert service.health_snapshot()[0]["connected"] is False


async def test_wait_for_commands_cancellation_releases_state():
    service = DshGatewayService()

    waiter = asyncio.create_task(service.wait_for_commands("devbox-1", 5))
    await _wait_until(lambda: _is_connected(service, "devbox-1"))

    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert service.health_snapshot()[0]["connected"] is False
    assert await service.wait_for_commands("devbox-1", 0) == []


async def test_notify_unknown_daemon_is_noop():
    service = DshGatewayService()

    service.notify("never-seen")

    assert service.health_snapshot() == []


async def test_last_health_reports_daemon_payload():
    service = DshGatewayService()
    request = SyncRequest(daemon_id="devbox-1", seq=1, health={"sessions": 3, "version": "0.3.0"})

    await service.sync(request)

    assert service.last_health("devbox-1") == {"sessions": 3, "version": "0.3.0"}
    assert service.last_health("devbox-2") == {}

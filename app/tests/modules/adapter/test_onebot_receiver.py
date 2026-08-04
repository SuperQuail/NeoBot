"""OneBot 反向 WebSocket 接收器 (AdapterCore) 与 OneBotAdapter 的单元测试。

不真实连网：通过假 WebSocket / 假核心在 handler 层验证 JSON 解析容错、心跳、
队列满策略、echo 幂等与消息路由等行为。合并自 packages/adapter/tests/ 下
test_onebot_lifecycle.py 与 test_websocket_api.py 的有效用例。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from unittest.mock import AsyncMock

import pytest
from loguru import logger as loguru_logger

from neobot_contracts.models import ConversationRef

from neobot_adapter.onebot.adapter import OneBotAdapter
from neobot_adapter.onebot.receiver.core import AdapterCore
from neobot_adapter.request.websocket import WebSocketAPI

import websockets.exceptions


@contextlib.contextmanager
def _pristine_websockets_package():
    """临时移除 websockets 包上的 exceptions 属性，模拟生产环境未显式导入该子模块。

    websockets 16 的懒加载 __getattr__ 无法解析 exceptions，属性只在实际执行
    `import websockets.exceptions` 后才会存在；移除属性即可复现 src 中
    `except websockets.exceptions.*` 子句在运行时抛 AttributeError 的真实场景。
    """
    package = sys.modules["websockets"]
    removed = package.__dict__.pop("exceptions", None)
    try:
        yield
    finally:
        if removed is not None:
            package.__dict__["exceptions"] = removed


class _FakeWebSocket:
    """按预定帧序列迭代的假 WebSocket，支持在迭代中抛异常模拟断连。"""

    def __init__(self, frames: list | None = None, exc: Exception | None = None) -> None:
        self._frames = list(frames or [])
        self._exc = exc

    def __aiter__(self) -> "_FakeWebSocket":
        return self

    async def __anext__(self):
        if self._exc is not None:
            raise self._exc
        if not self._frames:
            raise StopAsyncIteration
        return self._frames.pop(0)


class _NeverRespondWebSocket:
    """send 永不回应的假 WebSocket，用于验证 API 调用超时路径。"""

    async def send(self, data: str) -> None:
        return None


class _RecordingCore:
    """记录 call_api 参数的假核心，返回固定成功响应。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, float]] = []

    async def call_api(self, action: str, params: dict, timeout: float = 5.0, websocket=None):
        self.calls.append((action, params, timeout))
        return {"status": "ok", "retcode": 0, "message": "", "wording": "", "data": {"message_id": 7}}

    def call_api_sync(self, action: str, params: dict, timeout: float = 5.0, websocket=None):
        return None


# ─────────────────────────────── 事件入队与路由 ───────────────────────────────


@pytest.mark.asyncio
async def test_adapter_core_routes_event_into_queue() -> None:
    """_handle_event 必须把原始事件放入消息队列，get_message 按 FIFO 取出。"""
    core = AdapterCore()
    event = {
        "post_type": "message",
        "message_type": "private",
        "user_id": 10001,
        "message": [{"type": "text", "data": {"text": "hi"}}],
    }

    await core._handle_event(None, event)

    assert core.get_message() == event
    assert core.get_message(block=False) is None


@pytest.mark.asyncio
async def test_adapter_core_drops_event_when_queue_full() -> None:
    """队列满时新事件必须被丢弃且不抛异常，队列中先到的事件保持不变。"""
    core = AdapterCore(max_queue_size=1)

    await core._handle_event(None, {"post_type": "message", "message_type": "private", "user_id": 1, "message": "a"})
    await core._handle_event(None, {"post_type": "message", "message_type": "private", "user_id": 1, "message": "b"})

    assert core.message_queue.qsize() == 1
    assert core.get_message()["message"] == "a"


# ─────────────────────────── JSON 解析容错 / 断连 ───────────────────────────


@pytest.mark.asyncio
async def test_adapter_core_tolerates_malformed_json_frame() -> None:
    """畸形 JSON 帧必须被吞掉并记录日志，连接清理后该连接上的后续帧仍应被处理。"""
    core = AdapterCore()
    ws = _FakeWebSocket(frames=["not-a-json", '{"post_type":"message","message_type":"private","user_id":1,"message":"ok"}'])

    with _pristine_websockets_package():
        await core._handle_client(ws)

    assert not core.active_connections
    assert core.get_message(block=False)["message"] == "ok"


@pytest.mark.asyncio
async def test_adapter_core_logs_graceful_disconnect() -> None:
    """正常连接断开必须走 ConnectionClosed 分支优雅退出，而不是泄漏 AttributeError。"""
    core = AdapterCore()
    ws = _FakeWebSocket(exc=websockets.exceptions.ConnectionClosed(None, None))

    with _pristine_websockets_package():
        await core._handle_client(ws)

    assert not core.active_connections


@pytest.mark.asyncio
async def test_adapter_core_remove_connection_fails_pending_echo() -> None:
    """连接断开时等待中的 echo future 必须收到 ConnectionClosed 异常。"""
    core = AdapterCore()
    ws = object()
    fut = asyncio.get_running_loop().create_future()
    core._pending["echo-1"] = fut
    core._echo_to_conn["echo-1"] = ws
    core._conn_to_echo[ws] = {"echo-1"}

    with _pristine_websockets_package():
        await core._remove_connection(ws)

    assert fut.done()
    assert isinstance(fut.exception(), websockets.exceptions.ConnectionClosed)


# ─────────────────────────────── 心跳处理 ───────────────────────────────


@pytest.mark.asyncio
async def test_adapter_core_heartbeat_meta_starts_checker() -> None:
    """收到 heartbeat 元事件后必须记录心跳时间、推导间隔并启动心跳检测任务。"""
    core = AdapterCore()
    try:
        await core._handle_meta_event(
            {"post_type": "meta_event", "meta_event_type": "heartbeat", "interval": 1000}
        )

        assert core._last_heartbeat_time > 0
        assert core._heartbeat_interval == 1.0
        assert core._heartbeat_checker_task is not None
    finally:
        core._stop_event.set()
        task = core._heartbeat_checker_task
        core._heartbeat_checker_task = None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_adapter_core_heartbeat_timeout_logs_warning() -> None:
    """心跳超时（间隔 * 倍数未收到心跳）必须输出警告日志而非静默。"""
    core = AdapterCore()
    core._last_heartbeat_time = time.monotonic() - 100
    core._heartbeat_interval = 0.01
    records: list[str] = []
    sink_id = loguru_logger.add(lambda message: records.append(message), format="{message}")
    task = asyncio.create_task(core._check_heartbeat())
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not any("心跳超时" in text for text in records):
            await asyncio.sleep(0.01)

        assert any("心跳超时" in text for text in records)
    finally:
        core._stop_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        loguru_logger.remove(sink_id)


# ─────────────────────────────── echo 幂等 / 超时 ───────────────────────────────


@pytest.mark.asyncio
async def test_adapter_core_fulfill_echo_is_idempotent() -> None:
    """已取消或未匹配的 echo 响应必须被安全丢弃，绝不能抛异常或回填非法状态。"""
    core = AdapterCore()
    fut = asyncio.get_running_loop().create_future()
    core._pending["echo-1"] = fut
    fut.cancel()

    await core._fulfill_echo(None, "echo-1", {"echo": "echo-1"})
    await core._fulfill_echo(None, "echo-unknown", {"echo": "x"})

    assert fut.cancelled() is True


@pytest.mark.asyncio
async def test_adapter_core_call_action_timeout_returns_none_and_cleans_pending() -> None:
    """API 调用超时后必须返回 None，并把 echo 相关注册表清理干净。"""
    core = AdapterCore()

    result = await core._call_action(_NeverRespondWebSocket(), "ping", {}, timeout=0.05)

    assert result is None
    assert core._pending == {}
    assert core._echo_to_conn == {}


# ─────────────────────────────── 原始发送 / API 路由 ───────────────────────────────


@pytest.mark.asyncio
async def test_adapter_core_sends_raw_payload_to_explicit_websocket() -> None:
    """向显式传入的 websocket 发送原始 OneBot 载荷，且 JSON 内容保持原样。"""
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
async def test_adapter_core_reports_missing_connection() -> None:
    """没有活跃连接时 send_message 必须返回 False 而不是抛异常。"""
    core = AdapterCore()

    sent = await core.send_message({"action": "ping"})

    assert sent is False


@pytest.mark.asyncio
async def test_websocket_api_propagates_send_failure() -> None:
    """WebSocketAPI 必须把底层 send 失败原样向上传播为 False。"""
    core = AsyncMock()
    core.send_message.return_value = False
    api = WebSocketAPI(core)

    sent = await api.send_message({"action": "ping"})

    assert sent is False


# ─────────────────────────────── OneBotAdapter 生命周期 ───────────────────────────────


def test_onebot_connected_reflects_active_websocket() -> None:
    """connected 属性必须反映 AdapterCore 中活跃连接集合的状态。"""
    adapter = OneBotAdapter()
    assert adapter.connected is False

    marker = object()
    adapter.core.active_connections.add(marker)
    assert adapter.connected is True

    adapter.core.active_connections.remove(marker)
    assert adapter.connected is False


@pytest.mark.asyncio
async def test_onebot_adapter_send_routes_by_conversation_kind() -> None:
    """send 必须按会话类型路由到 send_private_msg / send_group_msg，并携带 timeout。"""
    fake = _RecordingCore()
    adapter = OneBotAdapter()
    adapter._core = fake

    private = await adapter.send(ConversationRef(kind="private", id="123"), "hi", timeout=2.0)
    await adapter.send(ConversationRef(kind="group", id="456"), "yo")

    assert private.data.message_id == 7
    assert fake.calls[0][0] == "send_private_msg"
    assert fake.calls[0][1] == {"user_id": 123, "message": {"type": "text", "data": {"text": "hi"}}}
    assert fake.calls[0][2] == 2.0
    assert fake.calls[1][0] == "send_group_msg"
    assert fake.calls[1][1] == {"group_id": 456, "message": {"type": "text", "data": {"text": "yo"}}}


@pytest.mark.asyncio
async def test_onebot_adapter_stop_works_without_start() -> None:
    """未 start 的 OneBotAdapter 调用 stop 必须快速返回且解绑全局 core 代理。"""
    adapter = OneBotAdapter()

    await adapter.stop()

    assert adapter._dispatch_task is None


def test_onebot_receiver_stop_wakes_thread_and_clears_reference(monkeypatch) -> None:
    """stop 必须唤醒接收线程，线程退出后 thread 引用被清空。"""
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

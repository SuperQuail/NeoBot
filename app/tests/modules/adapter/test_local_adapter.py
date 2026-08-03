"""Tests for the local sandbox adapter (LocalAdapter / LocalCore / LocalMessageStore).

文件同时保留原 EventGateway 的用例，并合并自 packages/adapter/tests/test_local_adapter.py
（LocalAdapter 本地沙箱适配器），新增 await_dispatch 语义 / FIFO / stop 取消等用例。
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from neobot_contracts.models import ConversationRef

from neobot_adapter import LocalAdapter
from neobot_adapter.local.core import LocalCore
from neobot_adapter.local.store import LocalMessageStore
from neobot_adapter.request.message import get_msg

from neobot_app.runtime.gateway import EventGateway
from neobot_app.runtime.event_context import EventContext


class _HookBus:
    def __init__(self) -> None:
        self.ctx = None

    async def dispatch(self, ctx: EventContext) -> None:
        self.ctx = ctx
        # Simulate plugin consumption test
        if ctx.raw_event.get("_test_mark_consumed"):
            ctx.consumed = True


class _LegacyPipeline:
    def __init__(self) -> None:
        self.received_private: list = []
        self.received_group: list = []

    async def handle_private_message_event(self, raw_event: dict, *, skip_ai_reply: bool = False) -> None:
        self.received_private.append({"raw_event": raw_event, "skip_ai_reply": skip_ai_reply})

    async def handle_group_message_event(self, raw_event: dict, *, skip_ai_reply: bool = False) -> None:
        self.received_group.append({"raw_event": raw_event, "skip_ai_reply": skip_ai_reply})

    async def flush_pending_summaries(self) -> None:
        pass


class _NoticeHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _RequestHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _LifecycleHandler:
    def __init__(self) -> None:
        self.ctx = None

    async def handle(self, ctx: EventContext) -> None:
        self.ctx = ctx


class _Source:
    def subscribe(self, *args, **kwargs):
        raise AssertionError("not used in unit tests")


class _RecordingDispatcher:
    """记录 publish 事件的假 dispatcher。"""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, event: dict) -> None:
        self.published.append(event)


class _BlockedDispatcher:
    """publish 被阻塞直到显式 release() 才完成的假 dispatcher，用于控制分发时序。"""

    def __init__(self) -> None:
        self.published: list[dict] = []
        self.started = asyncio.Event()
        self._release = asyncio.Event()

    async def publish(self, event: dict) -> None:
        self.started.set()
        await self._release.wait()
        self.published.append(event)

    def release(self) -> None:
        self._release.set()


def _message_payload(
    text: str,
    *,
    user_id: str = "10001",
    conversation_id: str = "10001",
    conversation_name: str = "Alice",
) -> dict:
    """构造 LocalCore.create_message 的最小入参。"""
    return {
        "conversation": {"kind": "private", "id": conversation_id, "name": conversation_name},
        "sender": {"user_id": user_id, "nickname": conversation_name},
        "message": text,
    }


# ───────────────────────── EventGateway（保留原有用例） ─────────────────────────


@pytest.mark.asyncio
async def test_event_gateway_honors_local_skip_ai_reply_marker() -> None:
    """Verify that _neobot_skip_ai_reply is stripped and passed as skip_ai_reply."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "_neobot_skip_ai_reply": True,
        "_local_conversation_name": "Alice",
    }
    await gateway.handle(raw_event)

    assert len(legacy.received_private) == 1
    handled = legacy.received_private[0]
    assert handled["skip_ai_reply"] is True
    assert "_neobot_skip_ai_reply" not in handled["raw_event"]
    assert "_local_conversation_name" not in handled["raw_event"]


@pytest.mark.asyncio
async def test_event_gateway_local_conversation_name_stripped() -> None:
    """Verify _local_conversation_name is stripped from the event and stored in metadata."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "group",
        "_local_conversation_name": "Bob",
    }
    await gateway.handle(raw_event)

    assert hooks.ctx is not None
    assert hooks.ctx.metadata.get("local_conversation_name") == "Bob"
    assert "_local_conversation_name" not in hooks.ctx.raw_event


@pytest.mark.asyncio
async def test_event_gateway_routes_notice_events() -> None:
    """Verify notice events are routed to the notice handler."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "notice",
        "notice_type": "group_poke",
    }
    await gateway.handle(raw_event)

    assert notice.ctx is not None
    assert notice.ctx.raw_event["post_type"] == "notice"
    assert len(legacy.received_private) == 0
    assert len(legacy.received_group) == 0


@pytest.mark.asyncio
async def test_event_gateway_respects_consumed_flag() -> None:
    """Verify consumed events are not routed to handlers."""
    hooks = _HookBus()
    legacy = _LegacyPipeline()
    notice = _NoticeHandler()
    request = _RequestHandler()
    lifecycle = _LifecycleHandler()

    gateway = EventGateway(
        event_source=_Source(),
        hook_bus=hooks,
        legacy_pipeline=legacy,
        notice_handler=notice,
        request_handler=request,
        lifecycle_handler=lifecycle,
    )

    raw_event = {
        "post_type": "message",
        "message_type": "private",
        "_test_mark_consumed": True,
    }
    await gateway.handle(raw_event)

    # The event should have been consumed by the plugin hook bus
    # and not forwarded to the legacy pipeline
    assert len(legacy.received_private) == 0
    assert len(legacy.received_group) == 0


# ─────────────────────── LocalAdapter / LocalCore / Store ───────────────────────


def test_local_message_store_records_conversations() -> None:
    """消息入库后必须能按 message_id 取回，且会话/好友列表记录被更新。"""
    store = LocalMessageStore(bot_user_id=42, bot_name="Neo")

    stored = store.add_event(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "raw_message": "hello",
            "sender": {"user_id": 10001, "nickname": "Alice"},
        },
        direction="incoming",
    )

    assert stored is not None
    assert stored.message_id >= 1_000_000
    assert store.get_msg(stored.message_id) is stored
    assert store.list_conversations()[0].id == "10001"
    assert store.friend_list()[0]["nickname"] == "Alice"


@pytest.mark.asyncio
async def test_local_adapter_subscribe_and_call_api() -> None:
    """启动本地适配器后订阅 message 事件，create_message 必须触发订阅且 call_api/get_msg 可回读消息。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    seen: list[dict] = []
    adapter.subscribe("message", seen.append, message_type="private")

    await adapter.start()
    try:
        created = await adapter.core.create_message(
            {
                "conversation": {"kind": "private", "id": "10001", "name": "Alice"},
                "sender": {"user_id": "10001", "nickname": "Alice"},
                "message": "hello",
            }
        )
        assert seen
        assert seen[0]["raw_message"] == "hello"

        result = await adapter.call_api("get_msg", {"message_id": created["message_id"]})
        assert result is not None
        assert result["status"] == "ok"
        assert result["data"]["raw_message"] == "hello"

        response = await get_msg(created["message_id"])
        assert response.data is not None
        assert response.data.raw_message == "hello"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_adapter_send_and_unsupported_action() -> None:
    """send 必须返回 message_id，未支持的 action 必须返回 failed 状态而非抛异常。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        response = await adapter.send(ConversationRef(kind="private", id="10001"), "hi")
        assert response.status == "ok"
        assert response.data is not None
        assert response.data.message_id is not None

        result = await adapter.call_api("set_group_ban", {"group_id": 1, "user_id": 2})
        assert result is not None
        assert result["status"] == "failed"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_http_health_and_auth() -> None:
    """配置 auth_token 后 HTTP 端点必须拒绝无凭证请求，正确凭证可访问 health 与 action 端点。"""
    adapter = LocalAdapter(port=0, auth_token="secret", bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{adapter.http_url}/health") as response:
                assert response.status == 401

            async with session.get(
                f"{adapter.http_url}/health",
                headers={"Authorization": "Bearer secret"},
            ) as response:
                assert response.status == 200
                payload = await response.json()
                assert payload["ok"] is True
                assert payload["data"]["mode"] == "local"

            async with session.post(
                f"{adapter.http_url}/v1/actions/get_login_info",
                json={"params": {}},
                headers={"Authorization": "Bearer secret"},
            ) as response:
                assert response.status == 200
                payload = await response.json()
                assert payload["ok"] is True
                assert payload["data"]["status"] == "ok"
                assert payload["data"]["data"]["user_id"] == 42
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_websocket_ping() -> None:
    """WebSocket 握手后必须先收 hello 帧，ping 必须回 pong 且带相同 id。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(adapter.ws_url) as ws:
                hello = await ws.receive_json()
                assert hello["type"] == "hello"
                await ws.send_json({"type": "ping", "id": "p1"})
                pong = await ws.receive_json()
                assert pong["type"] == "pong"
                assert pong["id"] == "p1"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_websocket_query_token() -> None:
    """配置 auth_token 后 WebSocket 可通过 ?token= 查询参数完成鉴权并收到 hello 帧。"""
    adapter = LocalAdapter(port=0, auth_token="secret", bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{adapter.ws_url}?token=secret") as ws:
                hello = await ws.receive_json()
                assert hello["type"] == "hello"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_history_uses_message_seq() -> None:
    """get_friend_msg_history 必须按 message_seq 分页且支持 reverse_order 倒序。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        ids: list[int] = []
        for index in range(5):
            created = await adapter.core.create_message(
                {
                    "conversation": {"kind": "private", "id": "10001", "name": "Alice"},
                    "sender": {"user_id": "10001", "nickname": "Alice"},
                    "message": f"m{index}",
                }
            )
            ids.append(created["message_id"])

        latest = await adapter.get_friend_msg_history(10001, count=2)
        assert [item.message_id for item in latest.data.messages] == ids[-2:]

        earlier = await adapter.get_friend_msg_history(10001, message_seq=ids[-1], count=2)
        assert [item.message_id for item in earlier.data.messages] == ids[-3:-1]

        reversed_page = await adapter.get_friend_msg_history(
            10001,
            message_seq=ids[-1],
            count=2,
            reverse_order=True,
        )
        assert [item.message_id for item in reversed_page.data.messages] == list(reversed(ids[-3:-1]))
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_delete_msg_marks_deleted_and_publishes_notice() -> None:
    """delete_msg 后 get_msg 必须返回 deleted=True，并向订阅者发布 group_recall 通知。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    seen: list[dict] = []
    adapter.subscribe("notice", seen.append)
    await adapter.start()
    try:
        created = await adapter.core.create_message(
            {
                "conversation": {"kind": "group", "id": "20001", "name": "Test Group"},
                "sender": {"user_id": "10001", "nickname": "Alice"},
                "message": "hello",
            }
        )
        result = await adapter.call_api("delete_msg", {"message_id": created["message_id"]})
        assert result["status"] == "ok"

        message = await adapter.call_api("get_msg", {"message_id": created["message_id"]})
        assert message["data"]["deleted"] is True
        assert any(event.get("notice_type") == "group_recall" for event in seen)
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_media_forward_and_reaction_actions() -> None:
    """媒体注册、表情回应 set/unset、合并转发 send/get 在本地适配器上必须闭环工作。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        await adapter.core.register_media(
            {
                "file": "img-1",
                "url": "https://example.test/image.png",
                "file_size": 12,
                "file_name": "image.png",
            }
        )
        image = await adapter.call_api("get_image", {"file": "img-1"})
        assert image["status"] == "ok"
        assert image["data"]["url"] == "https://example.test/image.png"

        created = await adapter.core.create_message(
            {
                "conversation": {"kind": "group", "id": "20001", "name": "Test Group"},
                "sender": {"user_id": "10001", "nickname": "Alice"},
                "message": "hello",
            }
        )
        like = await adapter.call_api(
            "set_msg_emoji_like",
            {"message_id": created["message_id"], "emoji_id": 128077},
        )
        assert like["status"] == "ok"
        fetched = await adapter.call_api(
            "fetch_emoji_like",
            {"message_id": created["message_id"], "emoji_id": 128077},
        )
        assert fetched["data"]["count"] == 1

        unlike = await adapter.call_api(
            "set_msg_emoji_like",
            {"message_id": created["message_id"], "emoji_id": 128077, "set": False},
        )
        assert unlike["status"] == "ok"
        fetched = await adapter.call_api(
            "fetch_emoji_like",
            {"message_id": created["message_id"], "emoji_id": 128077},
        )
        assert fetched["data"]["count"] == 0

        sent = await adapter.call_api(
            "send_group_forward_msg",
            {
                "group_id": 20001,
                "messages": [{"type": "node", "data": {"name": "Alice", "uin": 10001, "content": "hi"}}],
            },
        )
        assert sent["status"] == "ok"
        forward = await adapter.call_api("get_forward_msg", {"message_id": sent["data"]["message_id"]})
        assert forward["status"] == "ok"
        assert forward["data"]["messages"][0]["type"] == "node"
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_friend_and_group_requests_publish_onebot_events() -> None:
    """好友/加群请求创建与审批必须发布 request 事件并产生对应 notice。"""
    adapter = LocalAdapter(port=0, bot_user_id=42, bot_name="Neo")
    requests: list[dict] = []
    notices: list[dict] = []
    adapter.subscribe("request", requests.append)
    adapter.subscribe("notice", notices.append)
    await adapter.start()
    try:
        friend_request = await adapter.core.create_friend_request(
            {"user_id": 10001, "nickname": "Alice", "comment": "add me"}
        )
        assert requests[-1]["request_type"] == "friend"

        approved = await adapter.call_api(
            "set_friend_add_request",
            {"flag": friend_request["flag"], "approve": True, "remark": "A"},
        )
        assert approved["status"] == "ok"
        friends = await adapter.get_friend_list()
        assert friends.data[0].remark == "A"
        assert any(event.get("notice_type") == "friend_add" for event in notices)

        group_request = await adapter.core.create_group_request(
            {
                "group_id": 20001,
                "group_name": "Test Group",
                "user_id": 10002,
                "nickname": "Bob",
                "comment": "join",
            }
        )
        assert requests[-1]["request_type"] == "group"
        approved = await adapter.call_api(
            "set_group_add_request",
            {"flag": group_request["flag"], "approve": True},
        )
        assert approved["status"] == "ok"
        member = await adapter.get_group_member_info(20001, 10002)
        assert member.data.nickname == "Bob"
        assert any(event.get("notice_type") == "group_increase" for event in notices)
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_test_http_endpoints_update_sandbox_state() -> None:
    """v1/test 端点必须能写入好友并通过 export/reset 反映与清空沙箱状态。"""
    adapter = LocalAdapter(port=0, auth_token="secret", bot_user_id=42, bot_name="Neo")
    await adapter.start()
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": "Bearer secret"}
            async with session.post(
                f"{adapter.http_url}/v1/test/friends",
                json={"user_id": 10001, "nickname": "Alice"},
                headers=headers,
            ) as response:
                assert response.status == 200
                payload = await response.json()
                assert payload["data"]["nickname"] == "Alice"

            async with session.get(f"{adapter.http_url}/v1/test/export", headers=headers) as response:
                payload = await response.json()
                assert payload["ok"] is True
                assert payload["data"]["friends"][0]["user_id"] == 10001

            async with session.post(f"{adapter.http_url}/v1/test/reset", json={}, headers=headers) as response:
                payload = await response.json()
                assert payload["data"]["reset"] is True
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_local_core_await_dispatch_false_returns_before_dispatch() -> None:
    """await_dispatch=False 时 create_message 必须立即返回，事件交由后台 worker 异步分发。"""
    dispatcher = _BlockedDispatcher()
    core = LocalCore(dispatcher=dispatcher, port=0, bot_user_id=42)
    try:
        result = await core.create_message(_message_payload("hello"), await_dispatch=False)

        assert result["message_id"] is not None
        assert dispatcher.published == []

        dispatcher.release()
        await asyncio.wait_for(core._dispatch_queue.join(), timeout=3)
        assert len(dispatcher.published) == 1
        assert dispatcher.published[0]["raw_message"] == "hello"
    finally:
        await core.stop()


@pytest.mark.asyncio
async def test_local_core_dispatch_worker_preserves_fifo_order() -> None:
    """后台分发 worker 是单消费者，多个事件必须按入队顺序依次分发（FIFO）。"""
    dispatcher = _RecordingDispatcher()
    core = LocalCore(dispatcher=dispatcher, port=0, bot_user_id=42)
    try:
        expected = [f"m{index}" for index in range(5)]
        for text in expected:
            await core.create_message(_message_payload(text), await_dispatch=False)

        await asyncio.wait_for(core._dispatch_queue.join(), timeout=3)
        assert [event["raw_message"] for event in dispatcher.published] == expected
    finally:
        await core.stop()


@pytest.mark.asyncio
async def test_local_core_await_dispatch_true_publishes_before_return() -> None:
    """await_dispatch=True（默认）时 create_message 返回前事件必须已经同步分发完成。"""
    dispatcher = _RecordingDispatcher()
    core = LocalCore(dispatcher=dispatcher, port=0, bot_user_id=42)
    try:
        await core.create_message(_message_payload("sync"), await_dispatch=True)

        assert len(dispatcher.published) == 1
        assert dispatcher.published[0]["raw_message"] == "sync"
    finally:
        await core.stop()


@pytest.mark.asyncio
async def test_local_core_stop_cancels_pending_dispatch() -> None:
    """stop() 必须取消仍在执行的分发任务，且取消后分发队列不再被消费。"""
    dispatcher = _BlockedDispatcher()
    core = LocalCore(dispatcher=dispatcher, port=0, bot_user_id=42)
    try:
        await core.create_message(_message_payload("stuck"), await_dispatch=False)
        await dispatcher.started.wait()
        task = core._dispatch_task
        assert task is not None

        await core.stop()

        assert task.cancelled() is True
        assert core._dispatch_task is None
        assert dispatcher.published == []
    finally:
        if core._dispatch_task is not None:
            core._dispatch_task.cancel()
            await asyncio.gather(core._dispatch_task, return_exceptions=True)

from __future__ import annotations

import aiohttp
import pytest

from neobot_contracts.models import ConversationRef

from neobot_adapter import LocalAdapter
from neobot_adapter.local.store import LocalMessageStore
from neobot_adapter.request.message import get_msg


def test_local_message_store_records_conversations() -> None:
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

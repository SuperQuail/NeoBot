"""request 模块消息段构造、auto_escape 与 timeout 参数透传的单元测试。

通过 request/_proxy.py 的 bind_core 绑定假核心，验证 request 各函数构造的
OneBot 载荷与超时参数；不发起任何真实网络请求。
"""

from __future__ import annotations

import pytest

from neobot_adapter.request import message as message_api
from neobot_adapter.request._proxy import bind_core, unbind_core
from neobot_adapter.request.websocket import WebSocketAPI


class _FakeCore:
    """记录 call_api 调用并返回固定成功响应的假核心。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, float]] = []

    async def call_api(self, action: str, params: dict, timeout: float = 5.0, websocket=None):
        self.calls.append((action, params, timeout))
        return {
            "status": "ok",
            "retcode": 0,
            "message": "",
            "wording": "",
            "data": {
                "message_id": 12345,
                "raw_message": "hi",
                "message": [{"type": "text", "data": {"text": "hi"}}],
            },
        }

    def call_api_sync(self, action: str, params: dict, timeout: float = 5.0, websocket=None):
        return None


@pytest.fixture(autouse=True)
def bound_fake_core():
    """每个用例前绑定假核心到全局 core_proxy，用例结束后解绑。"""
    fake = _FakeCore()
    bind_core(fake)
    yield fake
    unbind_core()


@pytest.mark.asyncio
async def test_send_private_msg_builds_text_segment_and_forwards_timeout(bound_fake_core: _FakeCore) -> None:
    """send_private_msg 必须构造 text 消息段，并把 timeout 参数透传给核心。"""
    fake = bound_fake_core

    response = await message_api.send_private_msg(10001, "hi", timeout=3)

    assert fake.calls == [
        ("send_private_msg", {"user_id": 10001, "message": {"type": "text", "data": {"text": "hi"}}}, 3)
    ]
    assert response.data is not None
    assert response.data.message_id == 12345


@pytest.mark.asyncio
async def test_send_private_replay_msg_builds_reply_then_text_segments(bound_fake_core: _FakeCore) -> None:
    """send_private_replay_msg 必须构造 reply 段在前、text 段在后的消息段数组。"""
    fake = bound_fake_core

    await message_api.send_private_replay_msg(10001, "thanks", replay_id=999)

    action, params, _ = fake.calls[0]
    assert action == "send_private_msg"
    assert params["user_id"] == 10001
    assert params["message"] == [
        {"type": "reply", "data": {"id": "999"}},
        {"type": "text", "data": {"text": "thanks"}},
    ]


@pytest.mark.asyncio
async def test_send_group_forward_msg_passes_nodes_unchanged(bound_fake_core: _FakeCore) -> None:
    """send_group_forward_msg 必须把节点数组原样放入 messages 参数。"""
    fake = bound_fake_core
    nodes = [{"type": "node", "data": {"name": "Alice", "uin": 10001, "content": "hi"}}]

    await message_api.send_group_forward_msg(20001, nodes, timeout=6)

    assert fake.calls[0] == ("send_group_forward_msg", {"group_id": 20001, "messages": nodes}, 6)


@pytest.mark.asyncio
async def test_get_msg_forwards_timeout_parameter(bound_fake_core: _FakeCore) -> None:
    """get_msg 必须携带 message_id 与 timeout 参数调用核心。"""
    fake = bound_fake_core

    response = await message_api.get_msg(42, timeout=7)

    assert fake.calls[0] == ("get_msg", {"message_id": 42}, 7)
    assert response.data is not None
    assert response.data.message_id == 12345


@pytest.mark.asyncio
async def test_websocket_api_send_private_msg_includes_auto_escape_flag(bound_fake_core: _FakeCore) -> None:
    """WebSocketAPI.send_private_msg 必须把 auto_escape 标志加入参数字典。"""
    fake = bound_fake_core
    api = WebSocketAPI(fake)

    await api.send_private_msg(10001, "[CQ:at,qq=1]", auto_escape=True, timeout=9)

    assert fake.calls[0][0] == "send_private_msg"
    assert fake.calls[0][1] == {
        "user_id": 10001,
        "message": "[CQ:at,qq=1]",
        "auto_escape": True,
    }
    assert fake.calls[0][2] == 9


@pytest.mark.asyncio
async def test_websocket_api_send_group_msg_includes_auto_escape_flag(bound_fake_core: _FakeCore) -> None:
    """WebSocketAPI.send_group_msg 默认必须携带 auto_escape=False。"""
    fake = bound_fake_core
    api = WebSocketAPI(fake)

    await api.send_group_msg(20001, "hello")

    assert fake.calls[0][0] == "send_group_msg"
    assert fake.calls[0][1] == {
        "group_id": 20001,
        "message": "hello",
        "auto_escape": False,
    }


@pytest.mark.asyncio
async def test_request_proxy_raises_when_core_unbound() -> None:
    """core 未绑定时调用 request API 必须抛出 RuntimeError 而非静默失败。"""
    unbind_core()
    try:
        with pytest.raises(RuntimeError):
            await message_api.get_msg(1)
    finally:
        bind_core(_FakeCore())

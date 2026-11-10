"""OfficialAdapter 生命周期：启动/停止/rebind、事件投递与 action 分发。

全部使用假凭据库/假网关/假 HTTP，不联网。
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from neobot_contracts.models import ConversationRef


from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME
from neobot_contracts.ports.logging import NullLogger

from neobot_adapter.official import adapter as adapter_module
from neobot_adapter.official.auth import BindState, Credentials
from neobot_adapter.official.settings import OfficialSettings


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _FakeCredentialStore:
    """类级凭据值，方便假扫码流程与适配器共享。"""

    value: Credentials | None = None
    instances: list["_FakeCredentialStore"] = []

    def __init__(self, data_dir) -> None:
        self.data_dir = data_dir
        type(self).instances.append(self)

    def load(self) -> Credentials | None:
        return type(self).value

    def save(self, app_id: str, secret: str) -> None:
        type(self).value = Credentials(app_id=app_id, client_secret=secret)

    def delete(self) -> None:
        type(self).value = None


class _FakeTokenProvider:
    def __init__(self, settings, http=None) -> None:
        self.settings = settings

    async def get_token(self, *, force: bool = False) -> str:
        return "fake-token"

    def invalidate(self) -> None:
        return None


class _FakeApi:
    instances: list["_FakeApi"] = []

    def __init__(self, settings, token_provider, logger=None, *, http=None) -> None:
        self.settings = settings
        self.requests: list[tuple[str, str, dict]] = []
        self.closed = False
        type(self).instances.append(self)

    async def request(self, method: str, path: str, *, body=None, timeout: float = 10.0) -> dict:
        self.requests.append((method, path, dict(body or {})))
        if path == "/users/@me":
            return {
                "code": 0,
                "data": {
                    "username": "BotNick",
                    "share_url": "https://q.qq.com/qqbot/connect?robot_uin=1020304",
                },
            }
        return {"code": 0, "data": {"id": "ROBOT1.0_out"}}

    async def close(self) -> None:
        self.closed = True


class _FakeGateway:
    instances: list["_FakeGateway"] = []

    def __init__(self, settings, token_provider, on_event, logger=None, **kwargs) -> None:
        self.settings = settings
        self.on_event = on_event
        self.connected = False
        self.started = 0
        self.stopped = 0
        type(self).instances.append(self)

    async def start(self) -> None:
        self.started += 1
        self.connected = True
        await self.on_event(
            {
                "op": 0,
                "t": "READY",
                "id": "evt-ready",
                "s": 1,
                "d": {"session_id": "session-1", "user": {"id": "bot-openid"}},
            }
        )

    async def stop(self) -> None:
        self.stopped += 1
        self.connected = False

    async def wait_connected(self, timeout: float | None = None) -> bool:
        return self.connected


def _install_fakes(monkeypatch, *, credentials: Credentials | None) -> None:
    _FakeCredentialStore.value = credentials
    _FakeCredentialStore.instances = []
    _FakeApi.instances = []
    _FakeGateway.instances = []
    monkeypatch.setattr(adapter_module, "CredentialStore", _FakeCredentialStore)
    monkeypatch.setattr(adapter_module, "TokenProvider", _FakeTokenProvider)
    monkeypatch.setattr(adapter_module, "OfficialApi", _FakeApi)
    monkeypatch.setattr(adapter_module, "OfficialGateway", _FakeGateway)


def _make_adapter(workdir, events: list[dict]) -> adapter_module.OfficialAdapter:
    settings = OfficialSettings(app_id="", client_secret="", data_dir=workdir)
    return adapter_module.OfficialAdapter(
        settings,
        logger=NullLogger(),
        event_sink=events.append,
        data_dir=workdir,
    )


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


class _BlockingBindFlow:
    """先报 pending，等测试 release 后成功并写入新凭据。"""

    release: asyncio.Event
    completed = 0

    def __init__(self, settings, logger=None, http=None) -> None:
        self.settings = settings

    async def start(self, on_update=None) -> BindState:
        state = BindState(
            phase="pending",
            url="https://q.qq.com/qqbot/openclaw/connect.html?task_id=t1&_wv=2&source=neobot",
            svg="<svg/>",
            expires_at=time.time() + 600,
        )
        if on_update is not None:
            on_update(state)
        await type(self).release.wait()
        _FakeCredentialStore.value = Credentials(app_id="app-new", client_secret="new-secret")
        final = BindState(phase="success")
        if on_update is not None:
            on_update(final)
        type(self).completed += 1
        return final


class _ErrorBindFlow:
    def __init__(self, settings, logger=None, http=None) -> None:
        self.settings = settings

    async def start(self, on_update=None) -> BindState:
        state = BindState(phase="error", error="扫码失败")
        if on_update is not None:
            on_update(state)
        return state


async def test_start_with_stored_credentials_connects(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    events: list[dict] = []
    adapter = _make_adapter(workdir, events)

    assert adapter.bound is True
    assert adapter.requires_connection_wait is True
    assert adapter.connected is False

    await adapter.start()

    assert adapter.connected is True
    assert adapter.wait_for_connection(0.1) is True
    assert adapter.robot_uin == 1020304
    assert adapter.robot_nickname == "BotNick"
    assert adapter.settings.app_id == "app-1"
    meta_events = [e for e in events if e.get("meta_event_type") == "lifecycle"]
    assert meta_events and meta_events[0]["sub_type"] == "connect"
    assert meta_events[0]["self_id"] == 1020304

    version = await adapter.call_api("get_version_info", {})
    assert version["status"] == "ok"
    assert version["data"]["app_name"] == OFFICIAL_ADAPTER_APP_NAME

    login = await adapter.call_api("get_login_info", {})
    assert login["data"] == {"user_id": 1020304, "nickname": "BotNick"}

    await adapter.stop()
    assert adapter.connected is False
    assert _FakeGateway.instances[0].stopped == 1
    assert _FakeApi.instances[0].closed is True


async def test_start_without_credentials_runs_bind_flow(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=None)
    _BlockingBindFlow.release = asyncio.Event()
    _BlockingBindFlow.completed = 0
    monkeypatch.setattr(adapter_module, "QrBindFlow", _BlockingBindFlow)
    events: list[dict] = []
    adapter = _make_adapter(workdir, events)

    assert adapter.bound is False
    assert adapter.requires_connection_wait is False
    assert adapter.bind_state.phase == "idle"

    await adapter.start()

    assert adapter.connected is False
    await _wait_until(lambda: adapter.bind_state.phase == "pending")
    bind_task = adapter._bind_task
    assert bind_task is not None

    _BlockingBindFlow.release.set()
    await asyncio.wait_for(bind_task, timeout=2)

    assert _BlockingBindFlow.completed == 1
    assert adapter.bound is True
    assert adapter.settings.app_id == "app-new"
    assert adapter.bind_state.phase == "success"
    assert adapter.connected is True
    await adapter.stop()


async def test_stop_is_idempotent(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    adapter = _make_adapter(workdir, [])

    await adapter.start()
    gateway = _FakeGateway.instances[0]
    api = _FakeApi.instances[0]

    await adapter.stop()
    await adapter.stop()

    assert gateway.stopped == 1
    assert api.closed is True
    assert adapter.connected is False


async def test_rebind_switches_connection_after_bind_success(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    _BlockingBindFlow.release = asyncio.Event()
    _BlockingBindFlow.completed = 0
    monkeypatch.setattr(adapter_module, "QrBindFlow", _BlockingBindFlow)
    adapter = _make_adapter(workdir, [])
    await adapter.start()
    first_gateway = _FakeGateway.instances[0]

    await adapter.rebind()
    await _wait_until(lambda: adapter.bind_state.phase == "pending")
    bind_task = adapter._bind_task
    assert bind_task is not None
    _BlockingBindFlow.release.set()
    await asyncio.wait_for(bind_task, timeout=2)

    assert adapter.settings.app_id == "app-new"
    assert first_gateway.stopped == 1
    assert len(_FakeGateway.instances) == 2
    assert adapter.connected is True
    await adapter.stop()


async def test_rebind_failure_keeps_existing_connection(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    monkeypatch.setattr(adapter_module, "QrBindFlow", _ErrorBindFlow)
    adapter = _make_adapter(workdir, [])
    await adapter.start()
    gateway = _FakeGateway.instances[0]

    await adapter.rebind()
    bind_task = adapter._bind_task
    assert bind_task is not None
    await asyncio.wait_for(bind_task, timeout=2)

    assert adapter.bind_state.phase == "error"
    assert adapter.connected is True
    assert gateway.stopped == 0
    assert adapter.settings.app_id == "app-1"
    await adapter.stop()


async def test_unsupported_actions_return_chinese_failure(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    adapter = _make_adapter(workdir, [])
    await adapter.start()

    response = await adapter.call_api("set_group_ban", {"group_id": 1, "user_id": 2})

    assert response["status"] == "failed"
    assert "不支持" in response["message"]

    recall = await adapter.call_api("delete_msg", {"message_id": 1})
    assert recall["status"] == "failed"
    assert "撤回" in recall["message"]

    ranges = await adapter.call_api("get_robot_uin_range", {})
    assert ranges["data"] == []
    groups = await adapter.call_api("get_group_list", {})
    assert groups["data"] == []
    await adapter.stop()


async def test_inbound_event_is_published_and_serves_get_msg(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    events: list[dict] = []
    adapter = _make_adapter(workdir, events)
    await adapter.start()

    await adapter._on_event(
        {
            "op": 0,
            "t": "C2C_MESSAGE_CREATE",
            "id": "evt-message-1",
            "s": 2,
            "d": {
                "id": "ROBOT1.0_in",
                "content": "你好",
                "timestamp": "2026-01-02T03:04:05+08:00",
                "author": {"user_openid": "user-openid-1", "username": "Alice"},
            },
        }
    )

    messages = [e for e in events if e.get("post_type") == "message"]
    assert len(messages) == 1
    synthetic_id = messages[0]["message_id"]
    got = await adapter.call_api("get_msg", {"message_id": synthetic_id})
    assert got["status"] == "ok"
    assert got["data"]["message_id"] == synthetic_id

    # 被动回复：用刚收到消息的官方 msg_id 发一条私聊。
    conversation = ConversationRef(kind="private", id=str(messages[0]["user_id"]))
    result = await adapter.send(conversation, "回复")
    assert result.status == "ok"
    sent = _FakeApi.instances[0].requests[-1]
    assert sent[1] == "/v2/users/user-openid-1/messages"
    assert sent[2]["msg_id"] == "ROBOT1.0_in"
    await adapter.stop()


async def test_onebot_shaped_methods_and_core_proxy(workdir, monkeypatch) -> None:
    from neobot_adapter.request._proxy import core_proxy

    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    adapter = _make_adapter(workdir, [])
    await adapter.start()

    # core 代理指向当前官方核心，request 子模块因此可用。
    assert core_proxy.is_bound is True

    groups = await adapter.get_group_list()
    assert groups.status == "ok"
    assert groups.data == []

    stranger = await adapter.get_stranger_info(123)
    assert stranger.status == "ok"
    assert stranger.data.user_id == 123

    # 未在官方事件中出现过的会话反查不到 openid，发送应明确失败。
    failed = await adapter.send_group_msg(9_000_000_000_001, "你好")
    assert failed.status == "failed"

    await adapter.stop()
    assert core_proxy.is_bound is False


async def test_send_before_start_returns_failed(workdir, monkeypatch) -> None:
    _install_fakes(monkeypatch, credentials=Credentials("app-1", "secret-1"))
    adapter = _make_adapter(workdir, [])

    result = await adapter.send(ConversationRef(kind="private", id="1"), "你好")

    assert result.status == "failed"
    assert "尚未连接" in (result.message or "")

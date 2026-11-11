"""双通道适配器门面测试。

覆盖契约：dual 双后端同时启动、事件通道标记、双会话选路（两会话→onebot、
单会话→该通道、未知→onebot、显式 official、显式不可用 failed）、
ensure_accounts、apply_channel_config 增删/重启、stop 全停。
全部使用假后端，不依赖真实网络与官方协议模块。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from neobot_adapter import AdapterSettings, SwitchableAdapter, create_adapter
from neobot_adapter.switchable import channel_context, current_channel
from neobot_contracts.models import ConversationRef

from .test_switchable_adapter import _FakeBackend, _config, _install_fake_backends


def _dual(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SwitchableAdapter, list[_FakeBackend], set[str]]:
    created, failures = _install_fake_backends(monkeypatch)
    return SwitchableAdapter(AdapterSettings(mode="dual")), created, failures


def _message(kind: str, target: int) -> dict[str, Any]:
    if kind == "group":
        return {"post_type": "message", "message_type": "group", "group_id": target}
    return {"post_type": "message", "message_type": "private", "user_id": target}


# ── 生命周期：双后端同时启动 / 停止 ────────────────────────────────


async def test_dual_builds_and_starts_both_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, created, _ = _dual(monkeypatch)

    assert adapter.active_mode == "dual"
    assert adapter.active_channels == ("onebot", "official")
    assert adapter.connected_channels == ()
    assert [backend.mode for backend in created] == ["onebot", "official"]

    await adapter.start()

    assert [backend.start_calls for backend in created] == [1, 1]
    assert adapter.connected is True
    assert adapter.connected_channels == ("onebot", "official")


async def test_dual_start_keeps_running_when_one_backend_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    created, failures = _install_fake_backends(monkeypatch)
    failures.add("official")
    adapter = SwitchableAdapter(AdapterSettings(mode="dual"))

    await adapter.start()  # 单条通道失败只记 error，不抛

    assert created[0].started is True
    assert created[1].started is False
    assert adapter.connected_channels == ("onebot",)


async def test_dual_start_raises_when_all_backends_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    _created, failures = _install_fake_backends(monkeypatch)
    failures.update({"onebot", "official"})
    adapter = SwitchableAdapter(AdapterSettings(mode="dual"))

    with pytest.raises(OSError, match="后端启动失败"):
        await adapter.start()


async def test_dual_stop_stops_all_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()

    await adapter.stop()

    assert [backend.stop_calls for backend in created] == [1, 1]
    assert adapter.connected is False
    assert adapter.connected_channels == ()


async def test_dual_wait_for_connection_returns_when_any_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    assert adapter.wait_for_connection(0.05) is False

    await adapter.start()
    created[0].connected = False  # 只剩官方在线也算连上

    assert adapter.wait_for_connection(0.05) is True


# ── 事件合流：通道标记与会话记录 ────────────────────────────────────


async def test_dual_events_tag_channel_and_record_conversations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    seen: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        seen.append(event)

    adapter.subscribe("message", handler)
    group = _message("group", 42)
    private = _message("private", 7)
    await created[0].event_sink(group)
    await created[1].event_sink(private)

    assert [event["neobot_channel"] for event in seen] == ["onebot", "official"]
    assert "neobot_channel" not in group  # 不改后端手里的原事件
    assert adapter.channels_for_conversation(ConversationRef("group", "42")) == ("onebot",)
    assert adapter.channels_for_conversation(ConversationRef("private", "7")) == ("official",)


# ── 发送 / call_api 选路 ───────────────────────────────────────────


async def test_dual_routes_each_conversation_to_expected_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    onebot, official = created
    both = ConversationRef("group", "1")
    only_official = ConversationRef("private", "2")
    unknown = ConversationRef("group", "3")
    await onebot.event_sink(_message("group", 1))
    await official.event_sink(_message("group", 1))
    await official.event_sink(_message("private", 2))

    assert (await adapter.send(both, "hi")).status == "ok"  # 两会话→onebot
    assert (await adapter.send(only_official, "hi")).status == "ok"  # 单会话→该通道
    assert (await adapter.send(unknown, "hi")).status == "ok"  # 未知→onebot
    assert (await adapter.send(both, "hi", channel="official")).status == "ok"  # 显式

    assert onebot.send_calls == 2
    assert official.send_calls == 2


async def test_dual_auto_falls_back_when_preferred_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    onebot, official = created

    onebot.connected = False  # 未知会话默认 onebot，不可用则改投 official
    assert (await adapter.send(ConversationRef("group", "9"), "hi")).status == "ok"
    assert official.send_calls == 1

    onebot.connected = True
    await official.event_sink(_message("private", 5))
    official.connected = False  # 只出现在官方、官方不可用则改投 onebot
    assert (await adapter.send(ConversationRef("private", "5"), "hi")).status == "ok"
    assert onebot.send_calls == 1


async def test_dual_explicit_unavailable_channel_returns_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    created[1].connected = False

    sent = await adapter.send(ConversationRef("group", "1"), "hi", channel="official")
    result = await adapter.call_api("get_group_list", {}, channel="official")

    assert sent.status == "failed" and "official" in (sent.message or "")
    assert result["status"] == "failed" and result["retcode"] == -1
    assert created[1].send_calls == 0 and created[1].api_calls == []


async def test_single_mode_explicit_not_enabled_channel_returns_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    await adapter.start()

    sent = await adapter.send(ConversationRef("group", "1"), "hi", channel="official")
    unknown = await adapter.call_api("get_group_list", {}, channel="local")

    assert sent.status == "failed" and "未启用" in (sent.message or "")
    assert unknown["status"] == "failed" and unknown["retcode"] == -1
    assert created[0].send_calls == 0 and created[0].api_calls == []


async def test_dual_call_api_routes_explicit_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()

    explicit = await adapter.call_api("get_group_list", {}, channel="official")
    auto = await adapter.call_api("get_group_list", {})

    assert explicit["data"]["mode"] == "official"
    assert auto["data"]["mode"] == "onebot"
    assert created[0].api_calls == ["get_group_list"]
    assert created[1].api_calls == ["get_group_list"]


# ── 事件来源通道路由：处理中的查询不能落到默认 OneBot ──────────────


async def test_call_api_follows_event_source_channel_inside_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    results: list[dict[str, Any]] = []
    ambient: list[str | None] = []

    async def handler(event: dict[str, Any]) -> None:
        ambient.append(current_channel())
        results.append(await adapter.call_api("get_group_list", {}))

    adapter.subscribe("message", handler)
    await created[1].event_sink(_message("group", 5))

    assert ambient == ["official"]
    assert results[0]["data"]["mode"] == "official"
    assert created[1].api_calls == ["get_group_list"]
    assert created[0].api_calls == []
    # 分发结束后恢复默认选路
    assert current_channel() is None
    assert (await adapter.call_api("get_group_list", {}))["data"]["mode"] == "onebot"


async def test_event_channel_context_is_inherited_by_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """回复管线是事件处理里 create_task 出来的：它的查询必须仍查来源通道。"""
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    tasks: list[asyncio.Task[Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        tasks.append(asyncio.create_task(adapter.call_api("get_msg", {"message_id": 1})))

    adapter.subscribe("message", handler)
    await created[1].event_sink(_message("group", 6))
    results = await asyncio.gather(*tasks)

    assert results[0]["status"] == "ok"
    assert created[1].api_calls == ["get_msg"]
    assert created[0].api_calls == []


async def test_explicit_channel_overrides_event_source_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    results: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        results.append(await adapter.call_api("get_group_list", {}, channel="onebot"))

    adapter.subscribe("message", handler)
    await created[1].event_sink(_message("group", 7))

    assert results[0]["data"]["mode"] == "onebot"
    assert created[0].api_calls == ["get_group_list"]
    assert created[1].api_calls == []


async def test_event_channel_disconnected_returns_failed_without_onebot_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    created[1].connected = False
    results: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        results.append(await adapter.call_api("get_group_list", {}))

    adapter.subscribe("message", handler)
    await created[1].event_sink(_message("group", 8))

    assert results[0]["status"] == "failed" and "official" in results[0]["message"]
    assert created[0].api_calls == []
    assert created[1].api_calls == []


async def test_query_convenience_methods_follow_event_source_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    got: dict[str, Any] = {}

    async def handler(event: dict[str, Any]) -> None:
        got["msg"] = await adapter.get_msg(11)
        got["members"] = await adapter.get_group_member_list(22)

    adapter.subscribe("message", handler)
    await created[1].event_sink(_message("group", 9))

    assert got["msg"]["data"]["mode"] == "official"
    assert got["members"]["data"][0]["mode"] == "official"
    assert created[1].method_calls == ["get_msg", "get_group_member_list"]
    assert created[0].method_calls == []
    # 事件上下文之外仍是默认 OneBot；显式 channel 仍可指定。
    assert (await adapter.get_msg(11))["data"]["mode"] == "onebot"
    assert (await adapter.get_msg(12, channel="official"))["data"]["mode"] == "official"


async def test_query_convenience_method_returns_failed_for_unavailable_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()
    created[1].connected = False

    result = await adapter.get_msg(1, channel="official")

    assert result.status == "failed" and "official" in (result.message or "")
    assert created[1].method_calls == []


async def test_channel_context_pins_queries_outside_event_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后台/定时/跨聊天的合成事件用同一入口把通道钉进上下文。"""
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()

    with channel_context("official"):
        assert current_channel() == "official"
        result = await adapter.call_api("get_msg", {"message_id": 1})

    assert result["data"]["mode"] == "official"
    assert created[1].api_calls == ["get_msg"]
    assert current_channel() is None


# ── 账号 ────────────────────────────────────────────────────────────


async def test_dual_ensure_accounts_queries_once_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    assert await adapter.ensure_accounts() == {}  # 未连接不查询

    await adapter.start()
    accounts = await adapter.ensure_accounts()

    assert accounts == {"onebot": 10001, "official": 20002}
    assert adapter.accounts == accounts
    assert adapter.account_for("onebot") == 10001
    assert adapter.account_for("official") == 20002
    assert adapter.account_for("local") == 0

    await adapter.ensure_accounts()  # 已解析：不再发请求
    assert created[0].api_calls == ["get_login_info"]
    assert created[1].api_calls == ["get_login_info"]


# ── 热重载：apply_channel_config 增删 / 重启 ───────────────────────


async def test_apply_channel_config_adds_official_and_keeps_onebot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    await adapter.start()

    ok, message = await adapter.apply_channel_config(_config(mode="dual"))

    assert ok is True and "dual" in message
    assert adapter.active_mode == "dual"
    assert adapter.active_channels == ("onebot", "official")
    assert len(created) == 2
    assert created[0].stop_calls == 0 and created[0].start_calls == 1  # 未变化的后端不动
    assert created[1].start_calls == 1


async def test_apply_channel_config_removes_onebot_and_keeps_official(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()

    ok, _ = await adapter.apply_channel_config(_config(mode="official"))

    assert ok is True
    assert adapter.active_mode == "official"
    assert adapter.active_channels == ("official",)
    assert created[0].stop_calls == 1  # 移除的停掉
    assert created[1].stop_calls == 0 and created[1].start_calls == 1  # 保留的不重启
    assert len(created) == 2


async def test_dual_apply_channel_config_restarts_only_changed_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    await adapter.start()

    ok, _ = await adapter.apply_channel_config(_config(mode="dual", reverse_ws_host="127.0.0.1", reverse_ws_port=9999))

    assert ok is True
    assert adapter.active_channels == ("onebot", "official")
    assert len(created) == 3
    assert created[0].stop_calls == 1  # onebot 配置变化 → 重启
    assert created[1].stop_calls == 0  # official 未变化 → 保留
    assert created[2].mode == "onebot" and created[2].settings.port == 9999


async def test_apply_channel_config_round_trips_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    await adapter.start()

    await adapter.apply_channel_config(_config(mode="dual"))
    await adapter.apply_channel_config(_config(mode="official"))
    await adapter.apply_channel_config(_config(mode="dual"))

    assert adapter.active_mode == "dual"
    assert adapter.active_channels == ("onebot", "official")
    # onebot 停过一次、重建过一次；official 全程保留只启动一次。
    assert created[0].stop_calls == 1
    assert len(created) == 3 and created[2].mode == "onebot"
    official = created[1]
    assert official.stop_calls == 0 and official.start_calls == 1


async def test_switch_accepts_dual_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    await adapter.start()

    ok, message = await adapter.switch("dual")
    assert ok is True and "dual" in message
    assert adapter.active_channels == ("onebot", "official")
    assert created[0].stop_calls == 0 and created[1].start_calls == 1

    ok, message = await adapter.switch("onebot")
    assert ok is True
    assert adapter.active_channels == ("onebot",)
    assert created[1].stop_calls == 1


# ── core 委托 ───────────────────────────────────────────────────────


async def test_dual_speaking_policy_applies_to_all_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    policy = object()

    adapter.core.speaking_policy = policy

    assert created[0].core.speaking_policy is policy
    assert created[1].core.speaking_policy is policy
    assert adapter.core.speaking_policy is policy


def test_factory_dual_returns_switchable_facade(tmp_path: Any) -> None:
    adapter = create_adapter(AdapterSettings(mode="dual", data_dir=str(tmp_path)))

    assert isinstance(adapter, SwitchableAdapter)
    assert adapter.active_mode == "dual"
    assert adapter.active_channels == ("onebot", "official")
    assert adapter.connected_channels == ()


async def test_dual_getattr_prefers_onebot_but_falls_back_to_official(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter, created, _ = _dual(monkeypatch)
    created[0].shared_marker = "onebot"
    created[1].shared_marker = "official"
    created[1].official_marker = "official-only"

    assert adapter.shared_marker == "onebot"
    assert adapter.official_marker == "official-only"

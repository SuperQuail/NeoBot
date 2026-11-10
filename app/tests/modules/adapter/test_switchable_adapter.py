"""可切换适配器门面（SwitchableAdapter）测试。

覆盖契约：订阅跨通道切换存活、后端事件统一汇入门面 sink、切换失败回滚旧
后端、发言策略随切换传播、OneBot 反向 WS 设置委托、热重载分支与 factory
装配。全部使用假后端，不依赖真实网络与官方协议模块。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from neobot_adapter import (
    AdapterSettings,
    LocalAdapter,
    OneBotAdapter,
    SwitchableAdapter,
    create_adapter,
)
from neobot_adapter.model import response
from neobot_adapter.onebot.receiver.settings import ReverseWsSettings
from neobot_contracts.models import ConversationRef


class _FakeBackend:
    """按 OneBotAdapter 能力面实现的最小后端替身。"""

    def __init__(self, mode: str, *, fail_start: bool = False) -> None:
        self.mode = mode
        self.fail_start = fail_start
        self.start_calls = 0
        self.stop_calls = 0
        self.started = False
        self.connected = False
        self.requires_connection_wait = True
        self.http_url = ""
        self.ws_url = ""
        self.bind_state = None
        self.event_sink: Any = None
        self.reconfigured: list[ReverseWsSettings] = []
        self.api_calls: list[str] = []
        self.send_calls = 0
        self.core = SimpleNamespace(speaking_policy=None)

    async def start(self) -> None:
        self.start_calls += 1
        if self.fail_start:
            raise OSError(f"{self.mode} 后端启动失败")
        self.started = True
        self.connected = True

    async def stop(self) -> None:
        self.stop_calls += 1
        self.started = False
        self.connected = False

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        return self.connected

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> dict[str, Any]:
        self.api_calls.append(action)
        return {"status": "ok", "retcode": 0, "data": {"mode": self.mode}}

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = 5.0,
        wait_response: bool = True,
    ) -> response.SendMsgResponse:
        self.send_calls += 1
        return response.SendMsgResponse(status="ok", data={"message_id": self.send_calls})

    async def get_group_list(self, no_cache: bool = False, timeout: float = 5.0) -> Any:
        return response.GetGroupListResponse(status="ok", data=[])


def _install_fake_backends(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[_FakeBackend], set[str]]:
    """把 _build_backend 换成假后端工厂，并记录构造顺序与失败开关。"""
    created: list[_FakeBackend] = []
    failures: set[str] = set()

    def _build(self: SwitchableAdapter, mode: str, settings: AdapterSettings) -> Any:
        backend = _FakeBackend(mode, fail_start=mode in failures)
        backend.event_sink = self.publish
        if mode == "onebot":
            backend.settings = ReverseWsSettings(
                host=settings.reverse_ws_host or "0.0.0.0",
                port=settings.reverse_ws_port or 8080,
                access_token=settings.reverse_ws_access_token,
            )

            def _reconfigure(settings: ReverseWsSettings) -> None:
                backend.reconfigured.append(settings)
                backend.settings = settings

            backend.reconfigure = _reconfigure
        self._apply_policy(backend)
        created.append(backend)
        return backend

    monkeypatch.setattr(SwitchableAdapter, "_build_backend", _build)
    return created, failures


def _config(**overrides: Any) -> Any:
    values: dict[str, Any] = {
        "mode": "onebot",
        "reverse_ws_host": "",
        "reverse_ws_port": 0,
        "reverse_ws_access_token": "",
        "qq_appid": "",
        "qq_client_secret": "",
        "qq_markdown": True,
        "qq_base_url": "https://api.bot.qq.com",
        "qq_token_url": "https://api.bot.qq.com/app/getAppAccessToken",
        "qq_portal_host": "q.qq.com",
    }
    values.update(overrides)
    return SimpleNamespace(adapter=SimpleNamespace(**values))


def _feed_messages(adapter: OneBotAdapter, messages: list[dict[str, Any]]) -> None:
    """让 _dispatch_loop 依次取到给定事件，随后自行退出。"""
    pending = list(messages)

    def get_message(block: bool = True, timeout: float | None = None) -> Any:
        if pending:
            return pending.pop(0)
        adapter._stopping.set()
        return None

    adapter._core.get_message = get_message


# ── 事件订阅与 sink ─────────────────────────────────────────────────


async def test_subscription_survives_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    seen: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        seen.append(event)

    adapter.subscribe("message", handler)
    event = {"post_type": "message", "message_type": "private", "user_id": 7}

    assert (await adapter.switch("official"))[0] is True
    assert adapter.active_mode == "official"
    # 切换后的事件来自新后端的 sink，仍然命中切换前注册的处理器。
    await created[1].event_sink(event)
    assert seen == [event]


async def test_event_namespace_decorator_hooked_on_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    seen: list[dict[str, Any]] = []

    @adapter.on.message.group
    async def handler(event: dict[str, Any]) -> None:
        seen.append(event)

    await adapter.publish({"post_type": "message", "message_type": "group"})
    await adapter.publish({"post_type": "message", "message_type": "private"})
    assert len(seen) == 1
    assert created[0].event_sink is not None

    # 退订后跨切换也不再生效。
    subscription = adapter.subscribe("notice", handler)
    subscription.unsubscribe()
    await created[0].event_sink({"post_type": "notice"})


async def test_backend_event_sink_is_facade_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    seen: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        seen.append(event)

    adapter.subscribe("message", handler)
    assert created[0].event_sink == adapter.publish
    await created[0].event_sink({"post_type": "message"})
    assert seen == [{"post_type": "message"}]


async def test_onebot_adapter_uses_event_sink_when_provided() -> None:
    received: list[dict[str, Any]] = []

    async def sink(event: dict[str, Any]) -> None:
        received.append(event)

    adapter = OneBotAdapter(event_sink=sink)
    try:
        _feed_messages(adapter, [{"post_type": "message", "message_type": "private"}])
        await adapter._dispatch_loop()
    finally:
        adapter._stopping.set()
    assert received == [{"post_type": "message", "message_type": "private"}]


async def test_onebot_adapter_without_sink_keeps_own_dispatcher() -> None:
    adapter = OneBotAdapter()
    seen: list[dict[str, Any]] = []

    async def handler(event: dict[str, Any]) -> None:
        seen.append(event)

    adapter.subscribe("message", handler)
    try:
        _feed_messages(adapter, [{"post_type": "message", "message_type": "group"}])
        await adapter._dispatch_loop()
    finally:
        adapter._stopping.set()
    assert seen == [{"post_type": "message", "message_type": "group"}]


# ── 切换事务 ────────────────────────────────────────────────────────


async def test_switch_replaces_backend_and_keeps_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, message = await adapter.switch("official")

    assert ok is True and "official" in message
    assert adapter.active_mode == "official"
    assert created[0].stop_calls == 1
    assert created[1].mode == "official" and created[1].start_calls == 1
    result = await adapter.call_api("get_group_list", {})
    assert result["data"]["mode"] == "official"


async def test_switch_failure_rolls_back_old_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, failures = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    failures.add("official")

    ok, message = await adapter.switch("official")

    assert ok is False
    assert "official" in message and "启动失败" in message
    assert "已回滚到旧适配器" in message
    assert adapter.active_mode == "onebot"
    assert created[0].stop_calls == 1
    assert created[0].start_calls == 1  # 回滚时重新启动旧后端
    assert (await adapter.call_api("get_group_list", {}))["data"]["mode"] == "onebot"


async def test_switch_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, message = await adapter.switch("qq")

    assert ok is False and "未知适配器模式" in message
    assert adapter.active_mode == "onebot"
    assert len(created) == 1


async def test_send_and_call_api_fail_fast_while_switching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    adapter._switching = True

    api_result = await adapter.call_api("get_group_list", {})
    sent = await adapter.send(ConversationRef("group", "1"), "hi")

    assert api_result["status"] == "failed"
    assert "切换" in api_result["message"]
    assert sent.status == "failed"
    assert created[0].api_calls == [] and created[0].send_calls == 0

    adapter._switching = False
    assert (await adapter.call_api("get_group_list", {}))["status"] == "ok"


async def test_speaking_policy_propagates_across_switches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    policy = object()
    adapter.core.speaking_policy = policy

    await adapter.switch("official")
    assert created[1].core.speaking_policy is policy

    await adapter.switch("onebot")
    assert created[2].core.speaking_policy is policy
    assert adapter.core.speaking_policy is policy


# ── OneBot 监听设置委托 ─────────────────────────────────────────────


def test_settings_delegate_to_active_onebot_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot", reverse_ws_host="127.0.0.1", reverse_ws_port=8091))
    assert adapter.settings.port == 8091
    assert adapter.settings.host == "127.0.0.1"

    new_settings = ReverseWsSettings(host="0.0.0.0", port=8092, access_token="t")
    adapter.reconfigure(new_settings)

    assert adapter.settings == new_settings
    assert adapter._settings.reverse_ws_port == 8092
    assert adapter._settings.reverse_ws_access_token == "t"


async def test_settings_fall_back_to_stored_when_official_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot", reverse_ws_port=8091))
    adapter.reconfigure(ReverseWsSettings(host="0.0.0.0", port=8092, access_token=""))

    await adapter.switch("official")

    assert adapter.settings.port == 8092
    assert adapter.bind_state is None  # 假后端没有绑定状态
    assert adapter.http_url == "" and adapter.ws_url == ""


# ── 热重载：apply_channel_config ────────────────────────────────────


async def test_apply_channel_config_switches_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, message = await adapter.apply_channel_config(
        _config(mode="official", qq_appid="1024", qq_client_secret="secret")
    )

    assert ok is True and "official" in message
    assert adapter.active_mode == "official"
    assert created[0].stop_calls == 1
    assert created[1].mode == "official"


async def test_apply_channel_config_restarts_onebot_on_setting_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, _ = await adapter.apply_channel_config(
        _config(mode="onebot", reverse_ws_host="127.0.0.1", reverse_ws_port=9999)
    )

    assert ok is True
    assert len(created) == 2
    assert created[0].stop_calls == 1
    assert created[1].mode == "onebot"
    assert created[1].settings.port == 9999


async def test_apply_channel_config_rolls_back_onebot_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, failures = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot", reverse_ws_port=8091))
    failures.add("onebot")

    ok, message = await adapter.apply_channel_config(_config(mode="onebot", reverse_ws_port=9999))

    assert ok is False and "已回滚" in message
    assert adapter.active_mode == "onebot"
    assert created[0].start_calls == 1
    assert adapter.settings.port == 8091  # 回滚后仍是旧设置


async def test_apply_channel_config_restarts_official_on_qq_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="official", qq_appid="1024", qq_client_secret="old"))

    ok, message = await adapter.apply_channel_config(_config(mode="official", qq_appid="2048", qq_client_secret="new"))

    assert ok is True and "official" in message
    assert created[0].stop_calls == 1
    assert created[1].mode == "official"
    assert adapter._settings.qq_appid == "2048"


async def test_apply_channel_config_ignores_other_group_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="official", qq_appid="1024"))

    # official 生效时改 onebot 监听设置：只保存，不重启当前后端。
    ok, _ = await adapter.apply_channel_config(_config(mode="official", qq_appid="1024", reverse_ws_port=9999))

    assert ok is True
    assert len(created) == 1
    assert adapter.settings.port == 9999  # 已保存，切回 onebot 时生效


async def test_apply_channel_config_without_adapter_section_is_noop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, _ = await adapter.apply_channel_config(SimpleNamespace())

    assert ok is True
    assert len(created) == 1


async def test_apply_channel_config_rejects_unknown_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))

    ok, message = await adapter.apply_channel_config(_config(mode="bridge"))

    assert ok is False and "未知适配器模式" in message
    assert len(created) == 1


async def test_apply_channel_config_tolerates_partial_adapter_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """老配置对象只有反向 WS 字段时，qq_* 走当前设置，不因缺字段报错。"""
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot"))
    config = SimpleNamespace(
        adapter=SimpleNamespace(
            reverse_ws_host="127.0.0.1",
            reverse_ws_port=9999,
            reverse_ws_access_token="",
        )
    )

    ok, _ = await adapter.apply_channel_config(config)

    assert ok is True
    assert created[1].settings.port == 9999


async def test_apply_channel_config_unchanged_does_not_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created, _ = _install_fake_backends(monkeypatch)
    adapter = SwitchableAdapter(AdapterSettings(mode="onebot", reverse_ws_port=8091))

    ok, _ = await adapter.apply_channel_config(_config(mode="onebot", reverse_ws_port=8091))

    assert ok is True
    assert len(created) == 1
    assert created[0].stop_calls == 0


# ── factory 装配 ────────────────────────────────────────────────────


def test_factory_onebot_returns_switchable_facade() -> None:
    adapter = create_adapter(AdapterSettings(mode="onebot", reverse_ws_host="127.0.0.1", reverse_ws_port=8091))

    assert isinstance(adapter, SwitchableAdapter)
    assert adapter.active_mode == "onebot"
    assert adapter.core.host == "127.0.0.1"
    assert adapter.core.port == 8091
    assert adapter.settings.port == 8091
    assert adapter._backend._event_sink == adapter.publish


def test_factory_local_still_returns_local_adapter() -> None:
    adapter = create_adapter(AdapterSettings(mode="local", local_port=0))

    assert isinstance(adapter, LocalAdapter)
    assert adapter.requires_connection_wait is False


def test_factory_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="未知适配器模式"):
        create_adapter(AdapterSettings(mode="bridge"))


# ── 控制面委托 ──────────────────────────────────────────────────────


async def test_adapter_supervisor_delegates_channel_config() -> None:
    from neobot_app.runtime.adapter_supervisor import AdapterSupervisor

    class _Adapter:
        connected = True

        def __init__(self) -> None:
            self.calls: list[Any] = []

        async def apply_channel_config(self, config: Any) -> tuple[bool, str]:
            self.calls.append(config)
            return True, "delegated"

    adapter = _Adapter()
    config = object()

    await AdapterSupervisor(adapter).apply_config(config)

    assert adapter.calls == [config]


async def test_adapter_supervisor_raises_when_channel_switch_fails() -> None:
    from neobot_app.runtime.adapter_supervisor import AdapterSupervisor

    class _Adapter:
        connected = False

        async def apply_channel_config(self, config: Any) -> tuple[bool, str]:
            return False, "official 适配器启动失败"

    with pytest.raises(RuntimeError, match="official 适配器启动失败"):
        await AdapterSupervisor(_Adapter()).apply_config(object())

"""连接后的机器人身份判定：通道 / 官方性 / 账号自动补全与热重载重放。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

import neobot_adapter.request.private as private_module
from neobot_app.bot_detect import BotDetector
from neobot_app.runtime.application import NeoBotApplication
from neobot_contracts.platform import OFFICIAL_ADAPTER_APP_NAME


def _ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "retcode": 0, "data": data}


_OFFICIAL_VERSION = _ok({"app_name": OFFICIAL_ADAPTER_APP_NAME})
_ONEBOT_VERSION = _ok({"app_name": "NapCat.Onebot"})
_LOGIN = _ok({"user_id": 10001, "nickname": "Neo"})


class _FakeAdapter:
    """按脚本返回响应的假适配器；脚本末项会被重复使用。"""

    def __init__(
        self,
        *,
        connected: bool = True,
        responses: dict[str, list[Any]] | None = None,
    ) -> None:
        self.connected = connected
        self._responses = {key: list(value) for key, value in (responses or {}).items()}
        self.calls: list[str] = []

    async def call_api(
        self,
        action: str,
        params: dict[str, Any],
        timeout: float = 5.0,
        **_: Any,
    ) -> Any:
        self.calls.append(action)
        queue = self._responses.get(action) or [None]
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


class _LateConnectAdapter(_FakeAdapter):
    """启动时未连接、wait_for_connection 返回时视为已连接。"""

    def __init__(self, **kwargs: Any) -> None:
        kwargs["connected"] = False
        super().__init__(**kwargs)
        self.waited: list[float | None] = []

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        self.waited.append(timeout)
        self.connected = True
        return True


def _config(*, account: int = 0, official_mode: str = "auto") -> SimpleNamespace:
    return SimpleNamespace(bot=SimpleNamespace(account=account, official_mode=official_mode))


def _queues() -> tuple[SimpleNamespace, SimpleNamespace]:
    return SimpleNamespace(bot_account=0), SimpleNamespace(bot_account=0)


def _detector(
    adapter: Any,
    config: Any,
    group: Any,
    friend: Any,
) -> BotDetector:
    detector = BotDetector(adapter)
    detector.bind(config, group_queue=group, friend_queue=friend)
    return detector


@pytest.fixture(autouse=True)
def _stub_uin_range(monkeypatch) -> None:
    """身份判定末尾会刷新 UIN 段；单测里断开真实的 OneBot 请求代理。"""

    async def _unavailable():
        raise RuntimeError("OneBot 未连接")

    monkeypatch.setattr(private_module, "get_robot_uin_range", _unavailable)


async def test_unconnected_skips_api_and_keeps_profile_unknown() -> None:
    """未连接时不发任何 API，也不改配置与队列。"""
    adapter = _FakeAdapter(connected=False)
    config = _config(account=123)
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert adapter.calls == []
    assert profile.kind == "unknown"
    assert profile.account == 0
    assert profile.source == "unresolved"
    assert config.bot.account == 123
    assert group.bot_account == 0 and friend.bot_account == 0


async def test_official_channel_is_detected_from_version_info() -> None:
    """app_name 为官方适配器标识 -> official；account=0 时用登录信息回填并同步队列。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    config = _config(account=0)
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == "official"
    assert profile.channel == "qq-official"
    assert profile.source == "auto"
    assert profile.account == 10001
    assert config.bot.account == 10001
    assert group.bot_account == 10001 and friend.bot_account == 10001
    assert profile.resolved_at > 0


async def test_unofficial_channel_is_detected_from_version_info() -> None:
    """app_name 未匹配官方标识 -> onebot 通道、unofficial。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_ONEBOT_VERSION], "get_login_info": [_LOGIN]})
    config = _config()
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == "unofficial"
    assert profile.channel == "onebot"
    assert profile.source == "auto"


@pytest.mark.parametrize(
    ("official_mode", "version", "expected_kind"),
    [
        ("official", _ONEBOT_VERSION, "official"),
        ("unofficial", _OFFICIAL_VERSION, "unofficial"),
    ],
)
async def test_official_mode_forces_kind(official_mode: str, version: dict[str, Any], expected_kind: str) -> None:
    """official / unofficial 强制值优先于 API 判定。"""
    adapter = _FakeAdapter(responses={"get_version_info": [version], "get_login_info": [_LOGIN]})
    config = _config(official_mode=official_mode)
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == expected_kind
    assert profile.source == "forced"


async def test_configured_account_is_not_overwritten() -> None:
    """配置账号非 0 时以配置为准，不用登录信息覆盖。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    config = _config(account=999)
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.account == 999
    assert config.bot.account == 999
    assert group.bot_account == 999 and friend.bot_account == 999


async def test_version_info_is_retried_once() -> None:
    """get_version_info 第一次失败后重试一次成功。"""
    adapter = _FakeAdapter(
        responses={
            "get_version_info": [RuntimeError("timeout"), _OFFICIAL_VERSION],
            "get_login_info": [_LOGIN],
        }
    )
    config = _config()
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == "official"
    assert adapter.calls.count("get_version_info") == 2


async def test_version_info_failure_keeps_previous_profile() -> None:
    """重试后仍拿不到 version_info 时保持既有结论（不把 official 降级成 unknown）。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    config = _config()
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)
    first = await detector.resolve_identity()

    adapter._responses["get_version_info"] = [None]
    second = await detector.resolve_identity()

    assert second == first
    assert adapter.calls.count("get_version_info") == 3


async def test_login_failure_keeps_account_unknown() -> None:
    """login 失败不影响通道判定，account 保持 0（不写配置）。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [None]})
    config = _config(account=0)
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == "official"
    assert profile.account == 0
    assert config.bot.account == 0


async def test_invalid_official_mode_falls_back_to_auto() -> None:
    """非法 official_mode 按 auto 处理。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_ONEBOT_VERSION], "get_login_info": [_LOGIN]})
    config = _config(official_mode="nonsense")
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)

    profile = await detector.resolve_identity()

    assert profile.kind == "unofficial"
    assert profile.source == "auto"


async def test_reapply_replays_identity_after_reload() -> None:
    """配置热重载后重新绑定并通过 reapply 重放身份判定。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    group, friend = _queues()
    detector = _detector(adapter, _config(), group, friend)
    assert (await detector.resolve_identity()).kind == "official"

    new_config = _config(account=777, official_mode="unofficial")
    profile = await detector.reapply(new_config)

    assert profile.account == 777
    assert profile.kind == "unofficial"
    assert profile.source == "forced"
    assert new_config.bot.account == 777
    assert group.bot_account == 777 and friend.bot_account == 777


def _bare_application(adapter: Any, detector: BotDetector) -> NeoBotApplication:
    """只具备身份判定所需字段的 NeoBotApplication（不启动任何真实组件）。"""
    app = object.__new__(NeoBotApplication)
    app.adapter = adapter
    app._bot_detector = detector
    app._shutdown_event = asyncio.Event()
    app._background_tasks = []
    return app


async def test_application_waits_for_connection_then_resolves_identity() -> None:
    """启动时未连接 -> 挂后台任务等 30s 一档，连上后判定身份。"""
    adapter = _LateConnectAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    config = _config()
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)
    app = _bare_application(adapter, detector)

    await app._start_identity_detection()

    assert detector.profile.kind == "unknown"
    assert len(app._background_tasks) == 1

    await asyncio.gather(*app._background_tasks)

    assert adapter.waited == [30.0]
    assert detector.profile.kind == "official"
    assert config.bot.account == 10001


async def test_application_resolves_immediately_when_already_connected() -> None:
    """启动时已连接 -> 直接判定，不挂后台任务。"""
    adapter = _FakeAdapter(responses={"get_version_info": [_OFFICIAL_VERSION], "get_login_info": [_LOGIN]})
    config = _config()
    group, friend = _queues()
    detector = _detector(adapter, config, group, friend)
    app = _bare_application(adapter, detector)

    await app._start_identity_detection()

    assert app._background_tasks == []
    assert detector.profile.kind == "official"

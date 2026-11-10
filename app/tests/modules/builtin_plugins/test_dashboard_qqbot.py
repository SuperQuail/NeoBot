"""面板机器人通道：双通道状态、模式切换与扫码页。

接口用假 console / 假宿主服务直接调用（不起真实监听端口）；页面与脚本用
QQBotPageExtension.handle_request 的返回值断言。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.builtin_plugins.dashboard.api import DashboardApi
from neobot_app.builtin_plugins.dashboard.qqbot_panel import QQBotPageExtension


class _Logger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _Services:
    def __init__(self, **items: object) -> None:
        self._items = items

    def get(self, name: str, default=None):
        return self._items.get(name, default)


class _ConfigManager:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []
        self.section = {"mode": "onebot", "qq_appid": "10086"}

    def update_section(self, section: str, values: dict, **kwargs) -> dict:
        self.updated.append((section, dict(values)))
        self.section.update(values)
        return {"config": {}}

    def instance(self):
        return None

    def section_values(self, section: str) -> dict:
        return dict(self.section) if section == "adapter" else {}


class _HostCommands:
    def __init__(self, result: dict | None = None) -> None:
        self.result = result or {"status": "ok", "message": "配置已热重载"}
        self.calls: list[tuple[str, dict]] = []

    def call(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        return dict(self.result)


class _Console:
    def __init__(
        self,
        services: _Services,
        config_manager: _ConfigManager,
        *,
        manage: bool = True,
        remote_manage: bool = True,
    ) -> None:
        self.services = services
        self.config_manager = config_manager
        self.logger = _Logger()
        self.manage_plugins = manage
        self.allow_remote_manage = remote_manage

    def request_ip(self, request) -> str:
        return str(getattr(request, "ip", "127.0.0.1"))


class _Request:
    def __init__(self, payload: dict | None = None, *, ip: str = "127.0.0.1") -> None:
        self._payload = payload if payload is not None else {}
        self.ip = ip
        self.can_read_body = True

    async def json(self) -> dict:
        return self._payload


class _Adapter:
    """替代 SwitchableAdapter 的双通道可见状态。"""

    def __init__(self, **fields: object) -> None:
        self.rebind_calls = 0
        self.ensure_calls = 0
        self.__dict__.update(fields)

    async def rebind(self) -> None:
        self.rebind_calls += 1

    async def ensure_accounts(self) -> None:
        self.ensure_calls += 1


class _Detector:
    """替代 BotDetector：profile_for 返回 unknown 默认档，不抛错。"""

    def __init__(self, profiles: dict | None = None, accounts: dict | None = None) -> None:
        self.profiles = dict(profiles or {})
        self.accounts = dict(accounts or {})

    def profile_for(self, channel: str):
        return self.profiles.get(channel) or SimpleNamespace(account=0, nickname="")

    def account_for(self, channel: str) -> int:
        return int(self.accounts.get(channel, 0))


def _bind_state(
    *,
    phase: str = "pending",
    url: str = "https://q.qq.com/qqbot/connect.html?task_id=abc",
    svg: str = "<svg>qr</svg>",
) -> SimpleNamespace:
    return SimpleNamespace(
        phase=phase, url=url, svg=svg, expires_at=1730000000, error=""
    )


def _config(
    *,
    mode: str = "dual",
    qq_appid: str = "10086",
    reverse_ws_host: str = "127.0.0.1",
    reverse_ws_port: int = 8080,
    reverse_ws_access_token: str = "tok",
):
    return SimpleNamespace(
        adapter=SimpleNamespace(
            mode=mode,
            qq_appid=qq_appid,
            reverse_ws_host=reverse_ws_host,
            reverse_ws_port=reverse_ws_port,
            reverse_ws_access_token=reverse_ws_access_token,
        )
    )


def _adapter(**overrides: object) -> _Adapter:
    fields: dict[str, object] = {
        "active_mode": "dual",
        "switching": False,
        "connected": True,
        "active_channels": ("onebot", "official"),
        "connected_channels": ("onebot", "official"),
        "accounts": {},
        "bind_state": _bind_state(),
    }
    fields.update(overrides)
    return _Adapter(**fields)


def _make_api(
    *,
    adapter: object = None,
    detector: object = None,
    config: object = None,
    manage: bool = True,
    remote_manage: bool = True,
    commands: _HostCommands | None = None,
):
    config_manager = _ConfigManager()
    host_commands = commands or _HostCommands()
    items: dict[str, object] = {"host_commands": host_commands}
    if adapter is not None:
        items["adapter"] = adapter
    if detector is not None:
        items["bot_detector"] = detector
    if config is not None:
        items["config"] = config
    console = _Console(
        _Services(**items),
        config_manager,
        manage=manage,
        remote_manage=remote_manage,
    )
    return DashboardApi(console=console), config_manager, host_commands


def _channels(payload: dict) -> dict[str, dict]:
    return {item["name"]: item for item in payload["channels"]}


# ----------------------------------------------------------------------
# GET /api/qqbot/status
# ----------------------------------------------------------------------


async def test_status_dual_lists_both_channels_with_own_accounts() -> None:
    adapter = _adapter(accounts={"onebot": 111, "official": 222})
    detector = _Detector(
        profiles={
            "onebot": SimpleNamespace(account=111, nickname="小 O"),
            "official": SimpleNamespace(account=222, nickname="小官"),
        }
    )
    api, _, _ = _make_api(adapter=adapter, detector=detector, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["ok"] is True
    assert payload["mode"] == "dual"
    assert payload["switching"] is False
    assert [item["name"] for item in payload["channels"]] == ["onebot", "official"]
    assert payload["power"]["state"] == "running"

    channels = _channels(payload)
    onebot = channels["onebot"]
    assert onebot["active"] is True
    assert onebot["connected"] is True
    assert onebot["account"] == 111
    assert onebot["nickname"] == "小 O"
    assert onebot["onebot"] == {"host": "127.0.0.1", "port": 8080, "token_set": True}

    official = channels["official"]
    assert official["active"] is True
    assert official["connected"] is True
    assert official["account"] == 222
    assert official["nickname"] == "小官"
    assert official["app_id"] == "10086"
    assert official["bind"]["phase"] == "pending"
    assert official["bind"]["svg"] == "<svg>qr</svg>"
    assert official["bind"]["url"].startswith("https://q.qq.com/")


async def test_status_accounts_fall_back_to_bot_detector() -> None:
    detector = _Detector(
        profiles={
            "onebot": SimpleNamespace(account=10001, nickname="本体"),
            "official": SimpleNamespace(account=20002, nickname="官方号"),
        }
    )
    adapter = _adapter(accounts={})
    api, _, _ = _make_api(adapter=adapter, detector=detector, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    channels = _channels(payload)
    assert channels["onebot"]["account"] == 10001
    assert channels["onebot"]["nickname"] == "本体"
    assert channels["official"]["account"] == 20002
    assert channels["official"]["nickname"] == "官方号"


async def test_status_uses_adapter_accounts_without_detector() -> None:
    adapter = _adapter(accounts={"onebot": 30001, "official": 40002})
    api, _, _ = _make_api(adapter=adapter, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    channels = _channels(payload)
    assert channels["onebot"]["account"] == 30001
    assert channels["official"]["account"] == 40002
    assert channels["onebot"]["nickname"] == ""


async def test_status_single_channel_mode_falls_back_to_connected_flag() -> None:
    adapter = SimpleNamespace(active_mode="onebot", switching=False, connected=True)
    api, _, _ = _make_api(adapter=adapter, config=_config(mode="onebot"))
    payload = json.loads((await api.qqbot_status(_Request())).text)

    channels = _channels(payload)
    assert payload["mode"] == "onebot"
    assert channels["onebot"]["active"] is True
    assert channels["onebot"]["connected"] is True
    assert channels["official"]["active"] is False
    assert channels["official"]["connected"] is False
    assert channels["official"]["bind"]["phase"] == "idle"


async def test_status_dual_without_channel_lists_marks_both_active() -> None:
    adapter = SimpleNamespace(active_mode="dual", switching=False, connected=True)
    api, _, _ = _make_api(adapter=adapter, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    channels = _channels(payload)
    assert channels["onebot"]["active"] is True
    assert channels["official"]["active"] is True
    # dual 下全局 connected 区分不了通道，按未连接展示而不是瞎猜
    assert channels["onebot"]["connected"] is False
    assert channels["official"]["connected"] is False


async def test_status_without_adapter_returns_empty_channels() -> None:
    api, _, _ = _make_api(adapter=None, config=_config(mode="dual"))
    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["ok"] is True
    assert payload["mode"] == "dual"
    assert len(payload["channels"]) == 2
    channels = _channels(payload)
    assert channels["onebot"]["onebot"]["port"] == 8080
    assert channels["official"]["onebot"]["port"] == 0
    for item in payload["channels"]:
        assert item["active"] is True  # dual 模式推导：两条都应启用
        assert item["connected"] is False
        assert item["account"] == 0
        assert item["nickname"] == ""
        assert item["bind"]["svg"] == ""


async def test_status_tolerates_broken_account_sources() -> None:
    class _BrokenAdapter:
        active_mode = "dual"
        switching = False
        connected = True
        active_channels = ("onebot", "official")
        connected_channels = ()
        bind_state = None

        @property
        def accounts(self):
            raise RuntimeError("boom")

    class _BrokenDetector:
        def profile_for(self, channel):
            raise RuntimeError("boom")

        @property
        def accounts(self):
            raise RuntimeError("boom")

    api, _, _ = _make_api(
        adapter=_BrokenAdapter(), detector=_BrokenDetector(), config=_config()
    )
    response = await api.qqbot_status(_Request())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["ok"] is True
    assert all(item["account"] == 0 for item in payload["channels"])
    assert all(item["nickname"] == "" for item in payload["channels"])


async def test_status_hides_official_bind_secrets_from_read_only_sessions() -> None:
    api, _, _ = _make_api(
        adapter=_adapter(), config=_config(), manage=False
    )
    payload = json.loads((await api.qqbot_status(_Request())).text)

    official = _channels(payload)["official"]
    assert official["active"] is True
    assert official["bind"]["phase"] == "idle"
    assert official["bind"]["svg"] == ""
    assert official["bind"]["url"] == ""


async def test_status_asks_adapter_to_fill_missing_accounts() -> None:
    adapter = _adapter(accounts={})
    api, _, _ = _make_api(adapter=adapter, config=_config())

    first = json.loads((await api.qqbot_status(_Request())).text)
    second = json.loads((await api.qqbot_status(_Request())).text)

    assert _channels(first)["onebot"]["account"] == 0
    assert _channels(second)["onebot"]["account"] == 0
    # 取号失败时每次轮询都会再问（门面内部有缓存，成功后无网络开销）
    assert adapter.ensure_calls == 2


async def test_status_reads_accounts_filled_by_ensure_accounts() -> None:
    adapter = _adapter(accounts={})

    async def ensure() -> dict:
        adapter.ensure_calls += 1
        return {"onebot": 30001, "official": 40002}

    adapter.ensure_accounts = ensure  # type: ignore[method-assign]
    api, _, _ = _make_api(adapter=adapter, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    channels = _channels(payload)
    assert adapter.ensure_calls == 1
    assert channels["onebot"]["account"] == 30001
    assert channels["official"]["account"] == 40002


# ----------------------------------------------------------------------
# POST /api/qqbot/switch
# ----------------------------------------------------------------------


async def test_switch_accepts_dual_and_hot_reloads() -> None:
    api, config_manager, commands = _make_api()
    response = await api.qqbot_switch(_Request({"mode": "dual"}))
    payload = json.loads(response.text)

    assert response.status == 200
    assert config_manager.updated == [("adapter", {"mode": "dual"})]
    assert commands.calls == [("config.reload", {})]
    assert payload["ok"] is True
    assert payload["mode"] == "dual"
    assert payload["message"] == "配置已热重载"


async def test_switch_requires_manage_permission() -> None:
    api, config_manager, commands = _make_api(manage=False)
    response = await api.qqbot_switch(_Request({"mode": "dual"}))

    assert response.status == 403
    assert config_manager.updated == []
    assert commands.calls == []


async def test_switch_rejects_remote_ip_when_remote_manage_disabled() -> None:
    api, config_manager, _ = _make_api(remote_manage=False)
    response = await api.qqbot_switch(_Request({"mode": "dual"}, ip="203.0.113.9"))

    assert response.status == 403
    assert "远程管理已关闭" in json.loads(response.text)["error"]
    assert config_manager.updated == []


async def test_switch_rejects_unknown_mode_without_writing() -> None:
    api, config_manager, commands = _make_api()
    response = await api.qqbot_switch(_Request({"mode": "local"}))

    assert response.status == 400
    assert config_manager.updated == []
    assert commands.calls == []


async def test_switch_surfaces_reload_failure() -> None:
    commands = _HostCommands({"status": "failed", "message": "官方适配器启动失败"})
    api, config_manager, _ = _make_api(commands=commands)
    response = await api.qqbot_switch(_Request({"mode": "official"}))
    payload = json.loads(response.text)

    assert config_manager.updated == [("adapter", {"mode": "official"})]
    assert response.status == 500
    assert payload["ok"] is False
    assert "官方适配器启动失败" in payload["error"]
    assert payload["reload"]["ok"] is False


# ----------------------------------------------------------------------
# POST /api/qqbot/bind/rebind
# ----------------------------------------------------------------------


async def test_rebind_calls_adapter_when_supported() -> None:
    adapter = _adapter()
    api, _, _ = _make_api(adapter=adapter)

    response = await api.qqbot_rebind(_Request())

    assert response.status == 200
    assert adapter.rebind_calls == 1


async def test_rebind_returns_503_when_adapter_lacks_capability() -> None:
    api, _, _ = _make_api(adapter=object())

    response = await api.qqbot_rebind(_Request())

    assert response.status == 503
    assert "不支持" in json.loads(response.text)["error"]


# ----------------------------------------------------------------------
# 机器人通道页（自包含 HTML + 同源脚本）
# ----------------------------------------------------------------------


async def test_channel_page_metadata_and_self_contained_response() -> None:
    extension = QQBotPageExtension()

    assert extension.name == "qqbot"
    assert extension.prefixes == ("/qqbot",)
    assert extension.auth_prefixes == ("/qqbot",)
    assert extension.panel_entry() == {
        "title": "机器人通道",
        "path": "/qqbot/",
        "icon": "message",
        "description": "查看 OneBot 与官方机器人通道并扫码绑定",
    }

    page = await extension.handle_request(SimpleNamespace(path="/qqbot/"), "/qqbot/")
    assert page.status == 200
    assert page.content_type == "text/html"
    assert "机器人通道" in page.text
    # 三选一模式 + 两张卡同时存在，不再要求二选一
    assert 'data-mode="onebot"' in page.text
    assert 'data-mode="official"' in page.text
    assert 'data-mode="dual"' in page.text
    assert "OneBot 框架" in page.text
    assert "QQ 官方机器人" in page.text
    assert 'id="account-onebot"' in page.text
    assert 'id="account-official"' in page.text
    assert 'id="official-appid"' in page.text
    assert 'id="qr"' in page.text
    assert "client.js" in page.text

    index = await extension.handle_request(
        SimpleNamespace(path="/qqbot/index.html"), "/qqbot/index.html"
    )
    assert index.status == 200
    assert index.text == page.text


async def test_channel_script_uses_relative_api_and_channels_payload() -> None:
    extension = QQBotPageExtension()
    script = await extension.handle_request(
        SimpleNamespace(path="/qqbot/client.js"), "/qqbot/client.js"
    )

    assert script.status == 200
    assert script.content_type == "application/javascript"
    # 页面在 /qqbot/ 下，相对路径才能同时适配面板 base_path
    assert '"../api/qqbot/"' in script.text
    assert "channels" in script.text
    assert '"dual"' in script.text
    assert "X-CSRF-Token" in script.text
    assert "status" in script.text
    assert "switch" in script.text


async def test_channel_page_redirects_directory_and_leaves_other_paths() -> None:
    extension = QQBotPageExtension()
    redirect = await extension.handle_request(SimpleNamespace(path="/qqbot"), "/qqbot")

    assert redirect.status == 302
    assert redirect.headers["Location"] == "/qqbot/"
    assert (
        await extension.handle_request(SimpleNamespace(path="/qqbot/unknown"), "/qqbot/unknown")
        is None
    )

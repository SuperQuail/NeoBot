"""面板机器人通道：状态字段、通道切换与扫码页。

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
    """替代 SwitchableAdapter / OfficialAdapter 的面板可见状态。"""

    def __init__(self, **fields: object) -> None:
        self.rebind_calls = 0
        self.__dict__.update(fields)

    async def rebind(self) -> None:
        self.rebind_calls += 1


def _config(
    *,
    mode: str = "official",
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
        "active_mode": "official",
        "switching": False,
        "connected": True,
        "bind_state": SimpleNamespace(
            phase="pending",
            url="https://q.qq.com/qqbot/connect.html?task_id=abc",
            svg="<svg>qr</svg>",
            expires_at=1730000000,
            error="",
        ),
        "bound": False,
        "robot_uin": 0,
        "robot_nickname": "",
    }
    fields.update(overrides)
    return _Adapter(**fields)


def _make_api(
    *,
    adapter: object = None,
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
    if config is not None:
        items["config"] = config
    console = _Console(
        _Services(**items),
        config_manager,
        manage=manage,
        remote_manage=remote_manage,
    )
    return DashboardApi(console=console), config_manager, host_commands


# ----------------------------------------------------------------------
# GET /api/qqbot/status
# ----------------------------------------------------------------------


async def test_status_reports_adapter_and_bind_fields() -> None:
    api, _, _ = _make_api(adapter=_adapter(), config=_config())
    response = await api.qqbot_status(_Request())
    payload = json.loads(response.text)

    assert response.status == 200
    assert payload["ok"] is True
    assert payload["mode"] == "official"
    assert payload["switching"] is False
    assert payload["connected"] is True
    assert payload["bind"] == {
        "phase": "pending",
        "url": "https://q.qq.com/qqbot/connect.html?task_id=abc",
        "svg": "<svg>qr</svg>",
        "expires_at": 1730000000,
        "error": "",
    }
    assert payload["onebot"] == {"host": "127.0.0.1", "port": 8080, "token_set": True}
    assert payload["official"] == {
        "bound": False,
        "app_id": "10086",
        "account": 0,
        "nickname": "",
    }
    assert payload["power"]["state"] == "running"


async def test_status_reads_adapter_from_service_registry_each_call() -> None:
    """热切换后注册表里的适配器会换；缓存 console.adapter 会报旧通道。"""
    stale = _adapter(active_mode="onebot", connected=False, bind_state=None)
    live = _adapter(active_mode="official", connected=True)
    api, _, _ = _make_api(adapter=live, config=_config())
    api.console.adapter = stale

    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["mode"] == "official"
    assert payload["connected"] is True
    assert payload["bind"]["phase"] == "pending"


async def test_status_degrades_to_empty_values_without_adapter() -> None:
    api, _, _ = _make_api(adapter=None, config=_config(mode="onebot"))
    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["ok"] is True
    assert payload["mode"] == "onebot"
    assert payload["switching"] is False
    assert payload["connected"] is False
    assert payload["bind"] == {
        "phase": "idle",
        "url": "",
        "svg": "",
        "expires_at": 0,
        "error": "",
    }
    assert payload["official"]["bound"] is False
    assert payload["official"]["app_id"] == "10086"


async def test_status_reports_official_identity_when_bound() -> None:
    adapter = _adapter(
        bound=True,
        robot_uin=3889001234,
        robot_nickname="尼奥",
        bind_state=SimpleNamespace(phase="success", url="", svg="", expires_at=0, error=""),
    )
    api, _, _ = _make_api(adapter=adapter, config=_config())
    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["official"] == {
        "bound": True,
        "app_id": "10086",
        "account": 3889001234,
        "nickname": "尼奥",
    }


async def test_status_hides_bind_secrets_from_read_only_sessions() -> None:
    """扫码绑定等价于替机器人绑定账号，只展示给有管理权限的会话。"""
    api, _, _ = _make_api(adapter=_adapter(), config=_config(), manage=False)
    payload = json.loads((await api.qqbot_status(_Request())).text)

    assert payload["mode"] == "official"
    assert payload["bind"]["phase"] == "idle"
    assert payload["bind"]["svg"] == ""
    assert payload["bind"]["url"] == ""


# ----------------------------------------------------------------------
# POST /api/qqbot/switch
# ----------------------------------------------------------------------


async def test_switch_requires_manage_permission() -> None:
    api, config_manager, commands = _make_api(manage=False)
    response = await api.qqbot_switch(_Request({"mode": "official"}))

    assert response.status == 403
    assert config_manager.updated == []
    assert commands.calls == []


async def test_switch_rejects_remote_ip_when_remote_manage_disabled() -> None:
    api, config_manager, _ = _make_api(remote_manage=False)
    response = await api.qqbot_switch(_Request({"mode": "official"}, ip="203.0.113.9"))

    assert response.status == 403
    assert "远程管理已关闭" in json.loads(response.text)["error"]
    assert config_manager.updated == []


async def test_switch_rejects_unknown_mode_without_writing() -> None:
    api, config_manager, commands = _make_api()
    response = await api.qqbot_switch(_Request({"mode": "local"}))

    assert response.status == 400
    assert config_manager.updated == []
    assert commands.calls == []


async def test_switch_writes_adapter_section_and_hot_reloads() -> None:
    api, config_manager, commands = _make_api()
    response = await api.qqbot_switch(_Request({"mode": "official"}))
    payload = json.loads(response.text)

    assert response.status == 200
    assert config_manager.updated == [("adapter", {"mode": "official"})]
    assert commands.calls == [("config.reload", {})]
    assert payload["ok"] is True
    assert payload["mode"] == "official"
    assert payload["message"] == "配置已热重载"


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
        "description": "选择 OneBot 或官方机器人通道并扫码登录",
    }

    page = await extension.handle_request(SimpleNamespace(path="/qqbot/"), "/qqbot/")
    assert page.status == 200
    assert page.content_type == "text/html"
    assert "机器人通道" in page.text
    assert "OneBot 框架" in page.text
    assert "QQ 官方机器人" in page.text
    assert 'id="qr"' in page.text
    assert "client.js" in page.text

    index = await extension.handle_request(
        SimpleNamespace(path="/qqbot/index.html"), "/qqbot/index.html"
    )
    assert index.status == 200
    assert index.text == page.text


async def test_channel_script_is_same_origin_and_uses_relative_api() -> None:
    extension = QQBotPageExtension()
    script = await extension.handle_request(
        SimpleNamespace(path="/qqbot/client.js"), "/qqbot/client.js"
    )

    assert script.status == 200
    assert script.content_type == "application/javascript"
    # 页面在 /qqbot/ 下，相对路径才能同时适配面板 base_path
    assert '"../api/qqbot/"' in script.text
    assert "status" in script.text
    assert "switch" in script.text
    assert "X-CSRF-Token" in script.text


async def test_channel_page_redirects_directory_and_leaves_other_paths() -> None:
    extension = QQBotPageExtension()
    redirect = await extension.handle_request(SimpleNamespace(path="/qqbot"), "/qqbot")

    assert redirect.status == 302
    assert redirect.headers["Location"] == "/qqbot/"
    assert (
        await extension.handle_request(SimpleNamespace(path="/qqbot/unknown"), "/qqbot/unknown")
        is None
    )

"""连接状态变化必须绕过身份缓存，稳定连接仍复用缓存。"""

from pathlib import Path

import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_contracts.ports.logging import NullLogger


class SwitchingAdapter:
    def __init__(self, connected: bool):
        self.connected = connected
        self.calls: list[str] = []

    async def call_api(self, action: str, params: dict, timeout: float = 5.0):
        self.calls.append(action)
        if not self.connected:
            return None
        if action == "get_login_info":
            return {"status": "ok", "data": {"user_id": 10001, "nickname": "连接状态测试机器人"}}
        if action == "get_version_info":
            return {"status": "ok", "data": {"app_name": "OneBot", "app_version": "11"}}
        raise AssertionError(f"未声明的接口：{action}")


@pytest.mark.parametrize("initially_connected", [False, True], ids=["connect", "disconnect"])
async def test_bot_cache_observes_connection_change_before_profile_ttl(tmp_path: Path, initially_connected: bool):
    adapter = SwitchingAdapter(initially_connected)
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(bot_info_cache_ttl=300),
        data_dir=tmp_path,
        logger=NullLogger(),
        adapter=adapter,
        config_path=tmp_path / "config.toml",
        env_path=tmp_path / ".env",
        backup_dir=tmp_path / "backups",
    )
    before = await server.bot_info()
    assert before["online"] is initially_connected
    calls = list(adapter.calls)
    assert await server.bot_info() == before
    assert adapter.calls == calls

    adapter.connected = not initially_connected
    after = await server.bot_info()
    assert after["online"] is (not initially_connected)
    if not initially_connected:
        assert after["user_id"] == 10001
        assert after["nickname"] == "连接状态测试机器人"
    calls = list(adapter.calls)
    assert await server.bot_info() == after
    assert adapter.calls == calls

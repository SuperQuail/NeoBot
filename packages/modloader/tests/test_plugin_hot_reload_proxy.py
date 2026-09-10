"""插件热重载标注：plugin.toml / Plugin() 声明 -> 快照与重载守卫。"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_modloader import Plugin, PluginRuntime, PluginStateStore
from neobot_modloader.installer import PluginInstaller, ProxySettings
from neobot_modloader.management import PluginSnapshot


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _LoggerFactory:
    def get_logger(self, name: str) -> _NullLogger:
        return _NullLogger()


def _write_plugin(root: Path, name: str, *, manifest_extra: str = "", plugin_extra: str = "") -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.toml").write_text(
        f'name = "{name}"\nversion = "1.0.0"\n{manifest_extra}\n[config]\nvalue = 1\n',
        encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        "from neobot_modloader import Plugin\n\n"
        f'plugin = Plugin("{name}", version="1.0.0"{plugin_extra})\n',
        encoding="utf-8",
    )
    return plugin_dir


def _runtime(tmp_path: Path) -> PluginRuntime:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return PluginRuntime(
        plugin_dir=plugin_dir,
        data_dir=tmp_path / "plugins_data",
        adapter=None,
        logger_factory=_LoggerFactory(),
        state_store=PluginStateStore(tmp_path / "plugins_data" / "plugin_state.json"),
        installer=PluginInstaller(
            plugin_dir=plugin_dir, logger=_NullLogger(), fetcher=None
        ),
    )


def test_manifest_declares_hot_reload_flags(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    _write_plugin(root, "hot", manifest_extra="hot_reload = true\nconfig_hot_reload = true")
    _write_plugin(
        root,
        "cold",
        manifest_extra="hot_reload = false\nconfig_hot_reload = false",
    )
    runtime = _runtime(tmp_path)

    snapshots = {item.name: item for item in runtime.snapshot_plugins()}

    assert snapshots["hot"].hot_reload is True
    assert snapshots["hot"].config_hot_reload is True
    assert snapshots["cold"].hot_reload is False
    assert snapshots["cold"].config_hot_reload is False
    assert snapshots["cold"].hot_reloadable is False


def test_plugin_constructor_declares_flags_without_manifest(tmp_path: Path) -> None:
    _write_plugin(
        tmp_path / "plugins",
        "codeonly",
        plugin_extra=", hot_reload=False, config_hot_reload=False",
    )
    runtime = _runtime(tmp_path)
    runtime.load_all()

    snapshot = {item.name: item for item in runtime.snapshot_plugins()}["codeonly"]

    assert snapshot.hot_reload is False
    assert snapshot.config_hot_reload is False


def test_manifest_rejects_non_bool_flag(tmp_path: Path) -> None:
    _write_plugin(tmp_path / "plugins", "badflag", manifest_extra='hot_reload = "yes"')
    runtime = _runtime(tmp_path)

    snapshot = {item.name: item for item in runtime.snapshot_plugins()}["badflag"]

    assert snapshot.state == "error"
    assert "hot_reload" in str(snapshot.error)


@pytest.mark.asyncio
async def test_reload_refused_when_plugin_declares_no_hot_reload(tmp_path: Path) -> None:
    _write_plugin(tmp_path / "plugins", "cold", manifest_extra="hot_reload = false")
    runtime = _runtime(tmp_path)
    runtime.load_all()

    result = await runtime.reload_plugin_result("cold")

    assert result.ok is False
    assert result.requires_restart is True
    assert "热重载" in str(result.error)


def test_snapshot_hot_reloadable_requires_kind() -> None:
    assert PluginSnapshot(name="a", kind="package", hot_reload=True).hot_reloadable is True
    assert PluginSnapshot(name="a", kind="unknown", hot_reload=True).hot_reloadable is False
    assert PluginSnapshot(name="a", kind="package", hot_reload=False).hot_reloadable is False


def test_proxy_settings_validation() -> None:
    assert ProxySettings(mode="system").description == "跟随系统代理"
    assert ProxySettings(mode="none").description == "直连（不使用代理）"
    custom = ProxySettings(mode="custom", host="127.0.0.1", port=1080)
    assert custom.url == "http://127.0.0.1:1080"
    assert custom.to_dict()["port"] == 1080

    with pytest.raises(ValueError):
        ProxySettings(mode="bogus")
    with pytest.raises(ValueError):
        ProxySettings(mode="custom", host="")
    with pytest.raises(ValueError):
        ProxySettings(mode="custom", port=70000)


def test_installer_proxy_switching(tmp_path: Path, monkeypatch) -> None:
    import urllib.request

    installer = PluginInstaller(plugin_dir=tmp_path / "plugins", logger=_NullLogger())

    assert installer.proxy.mode == "system"
    settings = installer.set_proxy(mode="custom", host="10.0.0.2", port=3128)
    assert settings.mode == "custom"
    assert installer.proxy.url == "http://10.0.0.2:3128"

    captured: list[tuple] = []

    def _fake_build_opener(*handlers):
        captured.append(handlers)
        return urllib.request.OpenerDirector()

    monkeypatch.setattr(urllib.request, "build_opener", _fake_build_opener)

    installer.set_proxy(mode="none")
    installer._build_opener()
    assert captured[-1][0].proxies == {}

    installer.set_proxy(mode="custom")
    installer._build_opener()
    proxies = captured[-1][0].proxies
    assert proxies.get("https") == "http://10.0.0.2:3128"

    installer.set_proxy(mode="system")
    installer._build_opener()
    assert captured[-1] == ()

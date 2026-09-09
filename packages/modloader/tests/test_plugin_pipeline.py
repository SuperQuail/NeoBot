from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest

from neobot_modloader.host import DefaultServiceRegistry, PluginHostFacade, TrackedPluginHostFacade
from neobot_modloader.installer import (
    PluginInstaller,
    compare_versions,
)
from neobot_modloader.loader import FilesystemPluginLoader
from neobot_modloader.loading.models import OFFICIAL_SOURCE, THIRD_PARTY_SOURCE
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.state import PluginStateStore


def write_plugin(root: Path, name: str, *, version: str = "0.1.0", extra: str = "") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "plugin.toml").write_text(
        '\n'.join(
            [
                f'name = "{name}"',
                f'version = "{version}"',
                f'description = "{name} 测试插件"',
                'author = "tester"',
                extra,
                "",
                "[config]",
                'value = "ok"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (directory / "__init__.py").write_text(
        "from neobot_modloader import Plugin\n\nplugin = Plugin(__PLUGIN_NAME__, version=__PLUGIN_VERSION__)\n".replace(
            "__PLUGIN_NAME__", repr(name)
        ).replace("__PLUGIN_VERSION__", repr(version)),
        encoding="utf-8",
    )
    return directory


def build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# 状态存储
# ---------------------------------------------------------------------------


def test_state_store_roundtrip_and_forget(tmp_path: Path) -> None:
    store = PluginStateStore(tmp_path / "plugin_state.json")
    assert store.is_enabled("demo", True) is True
    assert store.is_enabled("demo", False) is False

    store.set_enabled("demo", False)
    store.set_enabled("other", True)

    reloaded = PluginStateStore(tmp_path / "plugin_state.json")
    assert reloaded.is_enabled("demo", True) is False
    assert reloaded.is_enabled("other", False) is True

    reloaded.forget("demo")
    assert PluginStateStore(tmp_path / "plugin_state.json").is_enabled("demo", True) is True


def test_state_store_tolerates_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "plugin_state.json"
    path.write_text("{ not json", encoding="utf-8")

    store = PluginStateStore(path)
    assert store.is_enabled("demo", True) is True

    store.set_enabled("demo", False)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["plugins"]["demo"]["enabled"] is False


# ---------------------------------------------------------------------------
# 加载器
# ---------------------------------------------------------------------------


def test_loader_marks_official_source_and_reads_metadata(tmp_path: Path) -> None:
    root = tmp_path / "official"
    write_plugin(
        root,
        "builtin_demo",
        extra='\n'.join(
            [
                'repo = "https://github.com/example/builtin_demo"',
                'branch = "dev"',
                'homepage = "https://example.com"',
                'license = "MIT"',
                'tags = ["core", "ui"]',
            ]
        ),
    )

    loader = FilesystemPluginLoader(source=OFFICIAL_SOURCE, namespace="neobot_builtin_plugins")
    discovered = loader.discover_all(root)
    assert len(discovered) == 1
    plugin = discovered[0]
    assert plugin.source == OFFICIAL_SOURCE
    assert plugin.official is True
    assert plugin.manageable is False
    assert plugin.repo == "https://github.com/example/builtin_demo"
    assert plugin.branch == "dev"
    assert plugin.tags == ("core", "ui")

    loaded = loader.load_all(root)[0]
    assert loaded.source == OFFICIAL_SOURCE
    assert loaded.repo == "https://github.com/example/builtin_demo"
    assert loaded.manageable is False


def test_loader_enabled_resolver_skips_disabled_plugin(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    write_plugin(root, "demo")
    loader = FilesystemPluginLoader(enabled_resolver=lambda name, default: name != "demo")

    discovered = loader.discover_all(root)[0]
    assert discovered.enabled is False
    assert loader.load_all(root) == []


# ---------------------------------------------------------------------------
# 运行时：官方目录、启停状态
# ---------------------------------------------------------------------------


def build_runtime(tmp_path: Path, *, official: list[Path] | None = None, state_store=None) -> PluginRuntime:
    user_dir = tmp_path / "plugins"
    user_dir.mkdir(parents=True, exist_ok=True)
    return PluginRuntime(
        plugin_dir=user_dir,
        data_dir=tmp_path / "plugins_data",
        adapter=object(),
        logger_factory=object(),
        builtin_plugin_dirs=official or [],
        state_store=state_store,
    )


def test_runtime_scans_official_and_third_party(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "builtin_demo")
    runtime = build_runtime(tmp_path, official=[official_dir])
    write_plugin(tmp_path / "plugins", "user_demo")

    runtime.load_all()
    snapshots = {item.name: item for item in runtime.snapshot_plugins()}

    assert snapshots["builtin_demo"].source == OFFICIAL_SOURCE
    assert snapshots["builtin_demo"].manageable is False
    assert snapshots["user_demo"].source == THIRD_PARTY_SOURCE
    assert snapshots["user_demo"].manageable is True


def test_runtime_official_plugin_wins_name_conflict(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "same_name", version="9.9.9")
    write_plugin(tmp_path / "plugins", "same_name", version="0.0.1")
    runtime = build_runtime(tmp_path, official=[official_dir])

    runtime.load_all()
    snapshots = {item.name: item for item in runtime.snapshot_plugins()}

    assert snapshots["same_name"].source == OFFICIAL_SOURCE
    assert snapshots["same_name"].version == "9.9.9"


async def test_runtime_set_enabled_persists_state(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "builtin_demo")
    store = PluginStateStore(tmp_path / "plugin_state.json")
    runtime = build_runtime(tmp_path, official=[official_dir], state_store=store)

    runtime.load_all()
    await runtime.load_registered()
    await runtime.start_all()
    assert runtime.manager.get_state("builtin_demo").value == "running"

    disabled = await runtime.set_enabled("builtin_demo", False)
    assert disabled.ok is True
    assert runtime.manager.get_state("builtin_demo").value == "unloaded"
    assert store.is_enabled("builtin_demo", True) is False

    enabled = await runtime.set_enabled("builtin_demo", True)
    assert enabled.ok is True
    assert runtime.manager.get_state("builtin_demo").value == "running"


def test_runtime_honours_persisted_disabled_state(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "builtin_demo")
    store = PluginStateStore(tmp_path / "plugin_state.json")
    store.set_enabled("builtin_demo", False)

    runtime = build_runtime(tmp_path, official=[official_dir], state_store=store)
    runtime.load_all()

    assert runtime.manager.get_record("builtin_demo") is None
    snapshot = runtime._snapshot_for("builtin_demo")
    assert snapshot is not None
    assert snapshot.enabled is False


async def test_runtime_official_config_provider_overrides_manifest(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "builtin_demo")
    runtime = build_runtime(tmp_path, official=[official_dir])
    runtime._official_config_provider = lambda name: {"value": "from-bot-config"} if name == "builtin_demo" else None

    runtime.load_all()
    record = runtime.manager.get_record("builtin_demo")
    assert record is not None
    assert record.context.config["value"] == "from-bot-config"
    assert record.context.source == OFFICIAL_SOURCE


async def test_runtime_uninstall_refuses_official_plugin(tmp_path: Path) -> None:
    official_dir = tmp_path / "official"
    write_plugin(official_dir, "builtin_demo")
    installer = PluginInstaller(plugin_dir=tmp_path / "plugins")
    runtime = build_runtime(tmp_path, official=[official_dir])
    runtime.installer = installer
    runtime.load_all()

    result = await runtime.uninstall_plugin("builtin_demo")
    assert result.ok is False
    assert "官方插件" in (result.error or "")


# ---------------------------------------------------------------------------
# 安装器
# ---------------------------------------------------------------------------


def test_installer_parse_spec_variants() -> None:
    installer = PluginInstaller(plugin_dir=Path("unused"))
    assert installer.parse_spec("owner/repo").slug == "owner/repo"
    assert installer.parse_spec("https://github.com/owner/repo").branch == "main"
    assert installer.parse_spec("https://github.com/owner/repo@dev").branch == "dev"
    assert installer.parse_spec("owner/repo", "beta").branch == "beta"
    with pytest.raises(Exception):
        installer.parse_spec("not a repo")


def test_compare_versions() -> None:
    assert compare_versions("1.0.1", "1.0.0") == 1
    assert compare_versions("1.0.0", "1.0.0") == 0
    assert compare_versions("0.9.9", "1.0.0") == -1
    assert compare_versions("1.0.0-alpha.2", "1.0.0-alpha.1") == 1
    assert compare_versions("1.0.0", "1.0.0-rc1") == 1


async def test_installer_installs_from_archive(tmp_path: Path) -> None:
    archive = build_zip(
        {
            "demo-main/plugin.toml": 'name = "demo"\nversion = "1.2.3"\n',
            "demo-main/__init__.py": "from neobot_modloader import Plugin\n\nplugin = Plugin('demo', version='1.0.0')\n",
        }
    )

    async def fetcher(url: str) -> bytes:
        assert "codeload.github.com" in url
        return archive

    installer = PluginInstaller(plugin_dir=tmp_path / "plugins", fetcher=fetcher)
    result = await installer.install("owner/demo")

    assert result.ok is True
    assert result.name == "demo"
    assert result.version == "1.2.3"
    assert (tmp_path / "plugins" / "demo" / "plugin.toml").is_file()

    duplicate = await installer.install("owner/demo")
    assert duplicate.ok is False
    assert "已安装" in (duplicate.error or "")

    updated = build_zip(
        {
            "demo-main/plugin.toml": 'name = "demo"\nversion = "2.0.0"\n',
            "demo-main/__init__.py": "from neobot_modloader import Plugin\n\nplugin = Plugin('demo', version='2.0.0')\n",
        }
    )

    async def updater(url: str) -> bytes:
        return updated

    installer._fetcher = updater
    replaced = await installer.install("owner/demo", replace=True)
    assert replaced.ok is True
    assert replaced.version == "2.0.0"
    assert replaced.backup_path is not None and replaced.backup_path.is_dir()
    assert "version='2.0.0'" in (tmp_path / "plugins" / "demo" / "__init__.py").read_text(encoding="utf-8")


async def test_installer_rejects_path_traversal(tmp_path: Path) -> None:
    archive = build_zip(
        {
            "../evil.txt": "boom",
            "demo-main/plugin.toml": 'name = "demo"\nversion = "1.0.0"\n',
        }
    )

    async def fetcher(url: str) -> bytes:
        return archive

    installer = PluginInstaller(plugin_dir=tmp_path / "plugins", fetcher=fetcher)
    result = await installer.install("owner/demo")

    assert result.ok is False
    assert not (tmp_path / "evil.txt").exists()


async def test_installer_rejects_non_github_host(tmp_path: Path) -> None:
    installer = PluginInstaller(plugin_dir=tmp_path / "plugins")
    with pytest.raises(Exception):
        installer._ensure_allowed_url("https://evil.example.com/x.zip")


async def test_installer_uninstall_moves_directory(tmp_path: Path) -> None:
    write_plugin(tmp_path / "plugins", "demo")
    installer = PluginInstaller(plugin_dir=tmp_path / "plugins")

    result = await installer.uninstall("demo")

    assert result.ok is True
    assert not (tmp_path / "plugins" / "demo").exists()
    assert result.backup_path is not None and result.backup_path.is_dir()


async def test_installer_check_update(tmp_path: Path) -> None:
    async def fetcher(url: str) -> bytes:
        assert url.endswith("/plugin.toml")
        return b'name = "demo"\nversion = "2.0.0"\n'

    installer = PluginInstaller(plugin_dir=tmp_path / "plugins", fetcher=fetcher)
    check = await installer.check_update(
        "demo", repo="owner/demo", current_version="1.0.0"
    )

    assert check.status == "available"
    assert check.remote_version == "2.0.0"

    same = await installer.check_update(
        "demo", repo="owner/demo", current_version="2.0.0"
    )
    assert same.status == "latest"


# ---------------------------------------------------------------------------
# 宿主服务注册表
# ---------------------------------------------------------------------------


def test_service_registry_register_get_require() -> None:
    registry = DefaultServiceRegistry()
    registry.register("config", {"a": 1}, description="配置代理")

    assert registry.get("config") == {"a": 1}
    assert registry.require("config") == {"a": 1}
    assert registry.names() == ["config"]
    assert registry.describe()[0]["description"] == "配置代理"
    assert registry.get("missing") is None
    with pytest.raises(KeyError):
        registry.require("missing")
    with pytest.raises(ValueError):
        registry.register("config", object())


async def test_tracked_service_registry_cleanup() -> None:
    registry = DefaultServiceRegistry()
    host = PluginHostFacade(services=registry)
    cleanups: list = []
    tracked = TrackedPluginHostFacade(host, cleanups.append)

    tracked.services.register("custom", object(), description="插件服务")
    assert registry.has("custom") is True

    for cleanup in reversed(cleanups):
        cleanup()
    assert registry.has("custom") is False


async def test_runtime_exposes_plugin_control_for_install(tmp_path: Path) -> None:
    archive = build_zip(
        {
            "demo-main/plugin.toml": 'name = "demo"\nversion = "1.0.0"\n',
            "demo-main/__init__.py": "from neobot_modloader import Plugin\n\nplugin = Plugin('demo', version='1.0.0')\n",
        }
    )

    async def fetcher(url: str) -> bytes:
        return archive

    runtime = build_runtime(tmp_path)
    runtime.installer = PluginInstaller(plugin_dir=tmp_path / "plugins", fetcher=fetcher)

    result = await runtime.install_plugin("owner/demo")
    assert result.ok is True
    assert runtime.manager.get_state("demo").value == "running"

    await asyncio.sleep(0)
    check = await runtime.check_plugin_update("demo")
    assert check.status in {"unknown", "error"}

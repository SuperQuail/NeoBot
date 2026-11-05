"""浏览器缓存、系统发现和配置路径的边缘场景。"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from neobot_app.bootstrap import _runtime
from neobot_app.browser.agent_browser import manager
from neobot_app.browser.agent_browser.manager_parts import process


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path):
    for name in ("PLAYWRIGHT_BROWSERS_PATH", "XDG_CACHE_HOME", "LOCALAPPDATA", "INIT_CWD", "CHROME_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(process, "_windows", lambda: True)
    monkeypatch.setattr(process.platform, "system", lambda: "Windows")


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)
    return str(path)


@pytest.mark.parametrize("package_local", [False, True])
def test_windows_cache_matches_installer_location(tmp_path, monkeypatch, package_local):
    if package_local:
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
        package = tmp_path / "playwright"
        monkeypatch.setattr(process, "find_spec", lambda name: SimpleNamespace(origin=str(package / "__init__.py")))
        cache = package / "driver" / "package" / ".local-browsers"
    else:
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "redirected"))
        cache = tmp_path / "redirected" / "ms-playwright"
    browser = executable(cache / "chromium-1234" / "chrome-win64" / "chrome.exe")
    assert process._playwright_chromium_path() == browser


@pytest.mark.parametrize(
    "layout,app",
    [
        ("chrome-mac", "Chromium"),
        ("chrome-mac-arm64", "Chromium"),
        ("chrome-mac-x64", "Chromium"),
        ("chrome-mac-arm64", "Google Chrome for Testing"),
        ("chrome-mac-x64", "Google Chrome for Testing"),
    ],
)
def test_macos_old_and_current_bundles(tmp_path, monkeypatch, layout, app):
    monkeypatch.setattr(process, "_windows", lambda: False)
    monkeypatch.setattr(process.platform, "system", lambda: "Darwin")
    cache = tmp_path / "Library" / "Caches" / "ms-playwright"
    browser = executable(cache / "chromium-1234" / layout / f"{app}.app" / "Contents" / "MacOS" / app)
    assert process._playwright_chromium_path() == browser


def test_registry_reads_all_views_in_chrome_first_order(tmp_path, monkeypatch):
    chrome = executable(tmp_path / "custom-chrome.exe")
    edge = executable(tmp_path / "custom-edge.exe")
    registry = Mock(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2, KEY_WOW64_64KEY=256, KEY_WOW64_32KEY=512, KEY_READ=1)
    seen = []

    def open_key(hive, key, reserved, access):
        seen.append((key.rsplit("\\", 1)[-1], hive, access))
        result = Mock()
        result.__enter__ = Mock(return_value=chrome if key.endswith("chrome.exe") else edge)
        result.__exit__ = Mock(return_value=False)
        return result

    registry.OpenKey.side_effect = open_key
    registry.QueryValueEx.side_effect = lambda value, _: (f'"{value}"', 1)
    monkeypatch.setitem(sys.modules, "winreg", registry)
    assert process._windows_registry_browser_paths() == [chrome] * 3 + [edge] * 3
    assert seen == [
        (name, hive, access) for name in ("chrome.exe", "msedge.exe") for hive, access in ((1, 257), (1, 513), (2, 1))
    ]


@pytest.mark.parametrize("chrome_source", ["path", "registry", "installation"])
def test_windows_system_chrome_precedes_edge(tmp_path, monkeypatch, chrome_source):
    monkeypatch.setattr(process, "_playwright_chromium_path", lambda: "")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "programs"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "programs-x86"))
    chrome = executable(
        tmp_path / "programs" / "Google" / "Chrome" / "Application" / "chrome.exe"
        if chrome_source == "installation"
        else tmp_path / "chrome.exe"
    )
    edge = executable(tmp_path / "edge.exe")
    monkeypatch.setattr(
        process.shutil,
        "which",
        lambda name: chrome if name == "chrome" and chrome_source == "path" else edge if name == "msedge" else None,
    )
    monkeypatch.setattr(
        process,
        "_windows_registry_browser_paths",
        lambda names: (
            [chrome]
            if names == ("chrome.exe",) and chrome_source == "registry"
            else [edge]
            if names == ("msedge.exe",)
            else []
        ),
    )
    assert process._find_chrome_binary() == chrome


@pytest.mark.parametrize("configured", ["valid", "missing", "denied", "stat_error"])
@pytest.mark.parametrize("installed", [False, True])
def test_bootstrap_uses_valid_configuration_or_clears_it(tmp_path, monkeypatch, configured, installed):
    import neobot_app.browser as browser_module

    path = tmp_path / "configured.exe"
    if configured != "missing":
        executable(path)
    if configured == "denied":
        monkeypatch.setattr(_runtime.os, "access", lambda *args: False)
    if configured == "stat_error":
        monkeypatch.setattr(Path, "is_file", Mock(side_effect=PermissionError("denied")))
    detector = Mock(side_effect=["detected.exe", "detected.exe"] if installed else ["", "detected.exe"])
    installer = Mock()
    wrapper = Mock()
    logger = Mock()
    monkeypatch.setattr(manager, "_find_chrome_binary", detector)
    monkeypatch.setattr(_runtime, "_auto_install_chromium", installer)
    monkeypatch.setattr(browser_module, "BrowserAgentWrapper", wrapper)
    config = SimpleNamespace(
        agent=SimpleNamespace(
            browser=SimpleNamespace(
                enabled=True,
                browser_path=str(path),
                hold_max_minutes=30,
            )
        )
    )
    result = _runtime.build_browser_components(config=config, data_dir=tmp_path, logger=logger)
    assert result["browser_instance"] is wrapper.return_value
    assert wrapper.call_args.kwargs["browser_path"] == (str(path) if configured == "valid" else "")
    assert installer.call_count == int(configured != "valid" and not installed)
    assert logger.warning.call_count == int(configured != "valid")
    if configured == "valid":
        detector.assert_not_called()


@pytest.mark.parametrize("name", ["chrome.exe", "msedge.exe", "chromium.exe"])
@pytest.mark.parametrize("split_argument", [False, True])
def test_orphan_cleanup_includes_edge_and_keeps_other_profiles(tmp_path, monkeypatch, name, split_argument):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manager, "_WINDOWS", True)
    monkeypatch.setattr(manager, "_has_other_live_instances", lambda instance: False)
    profile = str(tmp_path / "profile")
    psutil = Mock()
    psutil.NoSuchProcess = psutil.AccessDenied = psutil.TimeoutExpired = RuntimeError
    psutil.process_iter.return_value = [
        SimpleNamespace(
            info={
                "pid": 1,
                "name": name,
                "cmdline": ["--user-data-dir", profile] if split_argument else [f'--user-data-dir="{profile}"'],
            }
        ),
        SimpleNamespace(info={"pid": 2, "name": name, "cmdline": [f"--user-data-dir={tmp_path / 'other'}"]}),
        SimpleNamespace(info={"pid": 3, "name": name, "cmdline": [f"--user-data-dir={profile}-other"]}),
        SimpleNamespace(info={"pid": 4, "name": name, "cmdline": [f"--log-file={profile}/browser.log"]}),
        SimpleNamespace(info={"pid": 5, "name": name, "cmdline": ["--user-data-dir=profile"]}),
    ]
    monkeypatch.setitem(sys.modules, "psutil", psutil)
    instance = object.__new__(manager.BrowserManager)
    instance._user_data_dir = profile
    instance._kill_orphaned_chrome()
    psutil.Process.assert_called_once_with(1)
    psutil.Process.return_value.kill.assert_called_once()


def test_equivalent_profile_paths_share_live_instance_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(manager, "_WINDOWS", True)
    monkeypatch.setattr(manager, "_INSTANCE_REGISTRY", {})
    profile = tmp_path / "profile"
    first = object.__new__(manager.BrowserManager)
    first._user_data_dir = str(profile)
    second = object.__new__(manager.BrowserManager)
    second._user_data_dir = str(tmp_path / "unused" / ".." / "profile")
    manager._register_instance(first)
    manager._register_instance(second)
    psutil = Mock()
    monkeypatch.setitem(sys.modules, "psutil", psutil)

    assert manager._has_other_live_instances(first)
    assert manager._has_other_live_instances(second)
    second._kill_orphaned_chrome()
    psutil.process_iter.assert_not_called()
    manager._unregister_instance(first)
    assert not manager._has_other_live_instances(second)
    manager._unregister_instance(second)
    assert manager._INSTANCE_REGISTRY == {}

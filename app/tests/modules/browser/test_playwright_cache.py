"""Playwright 自定义缓存与重复冷启动的回归测试。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from neobot_app.bootstrap import _runtime
from neobot_app.browser.agent_browser.manager_parts import process


@pytest.fixture(autouse=True)
def isolated_linux_cache(tmp_path, monkeypatch):
    for name in ("PLAYWRIGHT_BROWSERS_PATH", "XDG_CACHE_HOME", "INIT_CWD", "CHROME_PATH"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(process, "_windows", lambda: False)
    monkeypatch.setattr(process.platform, "system", lambda: "Linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))


def _chromium(cache: Path, *, revision="1234", layout="chrome-linux64") -> Path:
    executable = cache / f"chromium-{revision}" / layout / "chrome"
    executable.parent.mkdir(parents=True)
    executable.touch()
    executable.chmod(0o755)
    return executable


@pytest.mark.parametrize("layout", ["chrome-linux", "chrome-linux64", "chrome-linux-arm64"])
def test_linux_uses_explicit_cache(tmp_path, monkeypatch, layout):
    cache = tmp_path / "custom browsers"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    executable = _chromium(cache, layout=layout)
    assert process._playwright_chromium_path() == str(executable)


def test_linux_uses_xdg_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    executable = _chromium(tmp_path / "xdg" / "ms-playwright")
    assert process._playwright_chromium_path() == str(executable)


def test_explicit_cache_takes_priority_over_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "explicit"))
    _chromium(tmp_path / "xdg" / "ms-playwright")
    assert process._playwright_chromium_path() == ""


@pytest.mark.parametrize("use_init_cwd", [False, True])
def test_relative_cache_uses_installer_working_directory(tmp_path, monkeypatch, use_init_cwd):
    monkeypatch.chdir(tmp_path)
    base = tmp_path
    if use_init_cwd:
        base = tmp_path / "installer"
        monkeypatch.setenv("INIT_CWD", str(base))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "browsers")
    executable = _chromium(base / "browsers")
    assert process._playwright_chromium_path() == str(executable)


def test_package_local_cache(tmp_path, monkeypatch):
    package = tmp_path / "playwright"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setattr(process, "find_spec", lambda name: SimpleNamespace(origin=str(package / "__init__.py")))
    executable = _chromium(package / "driver" / "package" / ".local-browsers")
    assert process._playwright_chromium_path() == str(executable)


def test_package_local_cache_without_playwright(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    monkeypatch.setattr(process, "find_spec", lambda name: None)
    assert process._playwright_chromium_path() == ""


def test_cache_uses_latest_numeric_revision_and_requires_file(tmp_path):
    cache = tmp_path / ".cache" / "ms-playwright"
    _chromium(cache, revision="999")
    newest = _chromium(cache, revision="1000")
    (cache / "chromium-9999" / "chrome-linux64" / "chrome").mkdir(parents=True)
    assert process._playwright_chromium_path() == str(newest)


@pytest.mark.parametrize("already_installed", [False, True])
def test_repeated_bootstrap_reuses_custom_cache(tmp_path, monkeypatch, already_installed):
    import neobot_app.browser as browser
    from neobot_app.browser.agent_browser import manager

    cache = tmp_path / "custom"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(cache))
    # 隔离系统浏览器，只保留真实的缓存发现与启动分支。
    monkeypatch.setattr(manager, "_find_chrome_binary", process._playwright_chromium_path)
    monkeypatch.setattr(browser, "BrowserAgentWrapper", Mock())
    installer = Mock(side_effect=lambda: bool(_chromium(cache)))
    monkeypatch.setattr(_runtime, "_auto_install_chromium", installer)
    if already_installed:
        _chromium(cache)
    config = SimpleNamespace(agent=SimpleNamespace(browser=SimpleNamespace(enabled=True, hold_max_minutes=30)))
    for _ in range(2):
        result = _runtime.build_browser_components(config=config, data_dir=tmp_path, logger=Mock())
        assert result["browser_instance"] is not None
    assert installer.call_count == (0 if already_installed else 1)

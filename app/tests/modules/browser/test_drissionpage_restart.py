"""用真实 DrissionPage 4.1 构造流程回归重启和连接失败，替换的仅是外部传输。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from websocket import WebSocketBadStatusException

from neobot_app.browser.agent_browser import _compat  # noqa: F401
from DrissionPage import Chromium, ChromiumOptions
from DrissionPage._base import chromium as chromium_module
from DrissionPage._base import driver as driver_module


@pytest.fixture
def transport(monkeypatch):
    monkeypatch.setattr(Chromium, "_BROWSERS", {})
    monkeypatch.setattr(driver_module.BrowserDriver, "BROWSERS", {})
    monkeypatch.setattr(driver_module.Driver, "_recv_loop", lambda self: None)
    monkeypatch.setattr(driver_module.Driver, "_handle_event_loop", lambda self: None)
    monkeypatch.setattr(chromium_module, "connect_browser", Mock())
    monkeypatch.setattr(chromium_module, "DownloadManager", Mock())
    monkeypatch.setattr(
        Chromium,
        "_run_cdp",
        lambda self, command, **kwargs: {"product": "Chrome/123", "processInfo": []},
    )
    state = SimpleNamespace(browser_id="old", headless=False, exists=True, fail_at=None)
    calls = []
    failed_drivers = []

    def connect(address, **kwargs):
        calls.append(address)
        if len(calls) == state.fail_at or address != endpoint(state.browser_id):
            failed_drivers.append(driver_module.BrowserDriver.BROWSERS[state.browser_id])
            raise WebSocketBadStatusException("Handshake status 404 Not Found", 404)
        return Mock()

    def restart_response(*args, **kwargs):
        state.browser_id = "new"
        state.headless = True
        return Mock(json=lambda: {"webSocketDebuggerUrl": endpoint("new")})

    monkeypatch.setattr(driver_module, "create_connection", connect)
    monkeypatch.setattr(
        chromium_module,
        "run_browser",
        lambda options: (state.headless, state.browser_id, state.exists, False),
    )
    session = Mock()
    session.get.side_effect = restart_response
    monkeypatch.setattr(chromium_module, "Session", lambda: session)
    yield state, calls, failed_drivers
    for driver in list(driver_module.BrowserDriver.BROWSERS.values()):
        if isinstance(driver, driver_module.BrowserDriver):
            driver.stop()


def endpoint(browser_id):
    return f"ws://127.0.0.1:19781/devtools/browser/{browser_id}"


def options():
    return ChromiumOptions(read_file=False).set_local_port(19781)


@pytest.mark.parametrize("restart_reason", ["headless", "new_environment"])
def test_restart_connects_to_new_browser_and_reuses_complete_instance(transport, restart_reason):
    state, calls, _ = transport
    config = options()
    if restart_reason == "headless":
        config.headless(True)
    else:
        config.new_env(True)

    browser = Chromium(config)

    assert calls == [endpoint("old"), endpoint("new")]
    assert browser.id == "new"
    assert browser._ws_address == endpoint("new")
    assert browser._driver.is_running
    assert browser._driver._ws is not None
    assert Chromium._BROWSERS == {"new": browser}
    assert driver_module.BrowserDriver.BROWSERS == {"new": browser._driver}
    config.new_env(False)
    state.headless = config.is_headless
    assert Chromium(config) is browser
    assert len(calls) == 2


@pytest.mark.parametrize("failure_call", [1, 2])
def test_failed_connection_is_evicted_and_next_attempt_initializes(transport, failure_call):
    state, calls, failed_drivers = transport
    state.fail_at = failure_call
    unrelated_browser = object()
    unrelated_driver = SimpleNamespace(owner=unrelated_browser)
    Chromium._BROWSERS["unrelated"] = unrelated_browser
    driver_module.BrowserDriver.BROWSERS["unrelated"] = unrelated_driver
    config = options().headless(True)

    with pytest.raises(WebSocketBadStatusException, match="404"):
        Chromium(config)

    assert Chromium._BROWSERS == {"unrelated": unrelated_browser}
    assert driver_module.BrowserDriver.BROWSERS == {"unrelated": unrelated_driver}
    assert failed_drivers[0]._ws is None
    assert not failed_drivers[0].is_running
    state.fail_at = None
    state.headless = True
    browser = Chromium(config)
    assert browser._driver is not failed_drivers[0]
    assert browser._driver.is_running
    assert browser._driver._ws is not None
    assert calls[-1] == endpoint(state.browser_id)
    assert Chromium._BROWSERS["unrelated"] is unrelated_browser
    assert driver_module.BrowserDriver.BROWSERS["unrelated"] is unrelated_driver

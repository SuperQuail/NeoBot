from __future__ import annotations

import io
import logging
import sys
import threading
from types import SimpleNamespace

import loguru
import pytest
from rich.console import Console

from neobot_app.observability import log_console, log_exceptions
from neobot_app.observability.log_console import RichConsoleSink
from neobot_app.observability.logging import configure_loguru


@pytest.fixture(autouse=True)
def isolated_logging():
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    loguru.logger.remove()
    loguru.logger.configure(patcher=None, extra={})
    root.handlers, root.level = handlers, level


def test_logged_exception_uses_rich_call_chain_without_source_or_locals():
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=True, color_system="standard", no_color=False, width=120, height=40)
    configure_loguru()
    loguru.logger.remove()
    loguru.logger.add(RichConsoleSink(stream, console=console), format="{message}")
    try:
        try:
            private_local = "PRIVATE_LOCAL_CANARY"
            raise ValueError("password=PRIVATE_VALUE_CANARY")
        except ValueError as exc:
            assert private_local
            raise RuntimeError("外层任务失败") from exc
    except RuntimeError:
        loguru.logger.exception("任务失败")
    output = stream.getvalue()
    assert "╭" in output
    assert "Traceback" in output
    assert "ValueError" in output and "RuntimeError" in output
    assert "test_rich_exceptions.py" in output
    assert "***REDACTED***" in output
    assert "PRIVATE_LOCAL_CANARY" not in output
    assert "PRIVATE_VALUE_CANARY" not in output
    assert "\x1b[" in output


def test_uncaught_syntax_error_group_is_rich_and_redacted(monkeypatch):
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=True, color_system=None, width=120, height=40)
    monkeypatch.setattr(log_console, "get_console", lambda: console)
    try:
        try:
            compile("password = 'PRIVATE_SOURCE_CANARY' :", "plugin.py", "exec")
        except SyntaxError as exc:
            raise ExceptionGroup("插件初始化异常", [exc, ValueError("token=PRIVATE_TOKEN_CANARY")])
    except ExceptionGroup:
        log_exceptions.display_uncaught_exception(*sys.exc_info())
    output = stream.getvalue()
    assert "╭" in output
    assert "ExceptionGroup" in output and "SyntaxError" in output
    assert "PRIVATE_SOURCE_CANARY" not in output
    assert "PRIVATE_TOKEN_CANARY" not in output
    assert "***REDACTED***" in output


def test_cli_hooks_capture_main_and_worker_crashes(monkeypatch):
    captured = []
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(log_exceptions, "display_uncaught_exception", lambda *args: captured.append(args))
    log_exceptions.install_exception_hooks()
    error = RuntimeError("任务异常")
    sys.excepthook(RuntimeError, error, None)
    threading.excepthook(SimpleNamespace(exc_type=RuntimeError, exc_value=error, exc_traceback=None))
    threading.excepthook(SimpleNamespace(exc_type=SystemExit, exc_value=SystemExit(0), exc_traceback=None))
    assert captured == [(RuntimeError, error, None), (RuntimeError, error, None)]

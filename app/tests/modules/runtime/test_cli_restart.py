"""CLI 进程级重启回归：只使用内存假应用，所有 exec 均拦截。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from neobot_app import cli
from neobot_app.runtime.application import NeoBotApplication


@pytest.fixture(autouse=True)
def _isolate_process_operations(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """禁止替换测试进程或修改进程级信号处理器。"""
    exec_mock = Mock()
    monkeypatch.setattr(os, "execv", exec_mock)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(cli.signal, "signal", Mock())
    monkeypatch.setattr(asyncio.BaseEventLoop, "add_signal_handler", Mock())
    return exec_mock


@pytest.mark.parametrize("restart", [False, True])
def test_run_builds_once_and_returns_restart_intent(monkeypatch, restart) -> None:
    """普通停止和重启均只构建一次应用，并返回该应用的重启意图。"""
    calls: list[str] = []

    class Application:
        restart_requested = restart

        async def run_forever(self):
            calls.extend(["run", "stop"])

    def create():
        calls.append("create")
        assert calls.count("create") == 1, "不能在旧解释器中再次装配应用"
        return Application()

    monkeypatch.setattr(cli, "create_application", create)

    result = asyncio.run(cli.run())

    assert result is restart
    assert calls == ["create", "run", "stop"]


def test_cmd_run_executes_after_application_and_loop_cleanup(monkeypatch) -> None:
    """重启须先完成真实 run_forever 的 stop，再回收孤立任务、生成器、线程和循环。"""
    state = SimpleNamespace(stopped=False, cancelled=False, generator_closed=False)
    release_worker = threading.Event()
    worker_finished = threading.Event()
    create_calls = 0
    original_argv = ["python", "-B", "-m", "neobot_app.cli"]
    monkeypatch.setattr(sys, "orig_argv", original_argv)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    cwd = os.getcwd()

    async def pending_task(ready):
        ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert state.stopped
            state.cancelled = True
            release_worker.set()

    async def pending_generator():
        try:
            yield "open"
        finally:
            state.generator_closed = True

    def worker(loop, ready):
        state.worker_thread = threading.current_thread()
        loop.call_soon_threadsafe(ready.set)
        assert release_worker.wait(5), "测试线程未收到 asyncio.run 取消阶段的释放信号"
        worker_finished.set()

    class Application(NeoBotApplication):
        # 使用实际 run_forever/request_restart，但不装配或启动任何真实服务。
        def __init__(self):
            self._shutdown_event = asyncio.Event()
            self._restart_requested = False

        async def start(self):
            state.loop = asyncio.get_running_loop()
            task_ready, worker_ready = asyncio.Event(), asyncio.Event()
            state.task = asyncio.create_task(pending_task(task_ready))
            state.worker_future = state.loop.run_in_executor(
                None, worker, state.loop, worker_ready
            )
            state.generator = pending_generator()
            assert await anext(state.generator) == "open"
            await task_ready.wait()
            await worker_ready.wait()
            self.request_restart()

        async def stop(self):
            await asyncio.sleep(0)
            assert not state.cancelled
            assert not worker_finished.is_set()
            state.stopped = True

    def create():
        nonlocal create_calls
        create_calls += 1
        assert create_calls == 1, "旧进程不得重新调用 create_application"
        return Application()

    def exec_after_cleanup(executable, argv):
        assert state.stopped
        assert state.cancelled
        assert state.task.cancelled()
        assert state.generator_closed
        assert worker_finished.is_set()
        assert not state.worker_thread.is_alive()
        assert state.loop.is_closed()
        assert os.getcwd() == cwd
        assert executable == sys.executable
        assert argv == [sys.executable, *original_argv[1:]]
        state.executed = True

    monkeypatch.setattr(cli, "create_application", create)
    monkeypatch.setattr(os, "execv", exec_after_cleanup)

    try:
        cli.cmd_run(argparse.Namespace())
    finally:
        release_worker.set()

    assert create_calls == 1
    assert state.executed


@pytest.mark.parametrize(
    "original_argv",
    [
        ["python", "-B", "-X", "utf8", "-m", "neobot_app.cli"],
        ["python", "-W", "error", "path with spaces/入口.py", "中文 参数"],
        ["python", "C:/Bot Path/.venv/Scripts/neobot.exe"],
        ["python", "-c", "from neobot_app.cli import main; main()"],
    ],
)
def test_cmd_run_preserves_original_interpreter_arguments(
    monkeypatch, _isolate_process_operations, original_argv
) -> None:
    """解释器选项、模块/脚本/入口程序以及空格中文参数必须原样保留。"""
    async def run():
        return True

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "executable", "C:/Python Path/python.exe")
    monkeypatch.setattr(sys, "orig_argv", original_argv)
    monkeypatch.setattr(sys, "argv", ["rewritten-by-launcher", "run"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    cli.cmd_run(argparse.Namespace())

    _isolate_process_operations.assert_called_once_with(
        sys.executable, [sys.executable, *original_argv[1:]]
    )


def test_cmd_run_preserves_frozen_executable_arguments(
    monkeypatch, _isolate_process_operations
) -> None:
    """打包程序直接重启当前可执行文件，不把它作为 Python 脚本再次传入。"""
    async def run():
        return True

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "executable", "C:/Bot Path/NeoBot.exe")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "argv", ["NeoBot.exe", "带 空格"])
    monkeypatch.delattr(sys, "orig_argv", raising=False)
    monkeypatch.setenv("PYINSTALLER_RESET_ENVIRONMENT", "0")
    monkeypatch.setenv("NEOBOT_TEST_KEEP_ENV", "preserved")
    original_environment = dict(os.environ)

    cli.cmd_run(argparse.Namespace())

    _isolate_process_operations.assert_called_once_with(
        sys.executable, [sys.executable, "带 空格"]
    )
    assert dict(os.environ) == {
        **original_environment, "PYINSTALLER_RESET_ENVIRONMENT": "1"
    }


def test_cmd_run_does_not_exec_on_normal_stop(monkeypatch, _isolate_process_operations) -> None:
    """普通停止只退出本轮运行，不触发进程重启。"""
    async def run():
        return False

    monkeypatch.setattr(cli, "run", run)

    cli.cmd_run(argparse.Namespace())

    _isolate_process_operations.assert_not_called()


@pytest.mark.parametrize("frozen", [False, True])
def test_cmd_run_quotes_windows_crt_arguments(
    monkeypatch, _isolate_process_operations, frozen
) -> None:
    """Windows CRT 转义保留空参数、空格、中文、引号及末尾反斜杠。"""
    async def run():
        return True

    slash = chr(92)
    arguments = ["", "two words", 'quote"value', "C:/trailing path" + slash, "中文 参数"]
    quoted = [
        '""', '"two words"', 'quote' + slash + '"value',
        '"C:/trailing path' + slash * 2 + '"', '"中文 参数"',
    ]
    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(sys, "executable", "C:/Python Path/python.exe")
    monkeypatch.setattr(sys, "orig_argv", ["python", "C:/Bot Path/入口.py", *arguments])
    monkeypatch.setattr(sys, "argv", ["NeoBot.exe", *arguments])
    monkeypatch.setenv("PYINSTALLER_RESET_ENVIRONMENT", "0")

    cli.cmd_run(argparse.Namespace())

    script = [] if frozen else ['"C:/Bot Path/入口.py"']
    _isolate_process_operations.assert_called_once_with(
        sys.executable, ['"C:/Python Path/python.exe"', *script, *quoted]
    )
    assert os.environ["PYINSTALLER_RESET_ENVIRONMENT"] == ("1" if frozen else "0")


def test_cmd_run_propagates_exec_failure(monkeypatch, _isolate_process_operations) -> None:
    """exec 系统错误继续传播，不吞掉错误或新增自动重试。"""
    async def run():
        return True

    monkeypatch.setattr(cli, "run", run)
    monkeypatch.setattr(sys, "orig_argv", ["python", "-m", "neobot_app.cli"])
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    _isolate_process_operations.side_effect = OSError("exec failed")

    with pytest.raises(OSError, match="exec failed"):
        cli.cmd_run(argparse.Namespace())

    assert _isolate_process_operations.call_count == 1


@pytest.mark.parametrize(
    ("error", "expected_exit"),
    [(cli.ConfigLoadError("bad config"), 1), (KeyboardInterrupt(), 0)],
)
def test_cmd_run_preserves_existing_exit_errors(
    monkeypatch, _isolate_process_operations, error, expected_exit
) -> None:
    """配置失败与键盘中断保留原退出码，不因重启改动启动新进程。"""
    async def run():
        raise error

    monkeypatch.setattr(cli, "run", run)

    with pytest.raises(SystemExit) as exc:
        cli.cmd_run(argparse.Namespace())

    assert exc.value.code == expected_exit
    _isolate_process_operations.assert_not_called()


def test_cmd_run_preserves_connection_timeout(monkeypatch, _isolate_process_operations, capsys) -> None:
    """连接超时保留原有错误输出和返回行为，不触发重启。"""
    async def run():
        raise cli.ConnectionTimeoutError("offline")

    monkeypatch.setattr(cli, "run", run)

    cli.cmd_run(argparse.Namespace())

    assert "offline" in capsys.readouterr().out
    _isolate_process_operations.assert_not_called()

"""Exclusive tests for controlled subprocesses; no external services/dependencies."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import sys
import time

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.processes import ProcessConfig, ProcessTools

OWNER = ToolContext(owner="alice", chat_flow_id="test:one")
FOREIGN = ToolContext(owner="bob", chat_flow_id="test:one")
OTHER_FLOW = ToolContext(owner="alice", chat_flow_id="test:two")


def run(coroutine):
    # asyncio.run selects a Proactor loop on Windows, required for subprocesses.
    return asyncio.run(coroutine)


def shell_code(powershell: str, bash: str) -> str:
    return powershell if os.name == "nt" else bash


def require_shell():
    if not (shutil.which("pwsh") or shutil.which("powershell.exe") if os.name == "nt" else shutil.which("bash")):
        pytest.skip("platform shell unavailable")


def test_python_subprocess_cwd_streams_nonzero(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            result = await manager.execute("run_python", {"code": "import os,sys; print(os.getcwd()); print(sys.executable); print('错误', file=sys.stderr); sys.exit(7)"}, OWNER)
            assert result["exit_code"] == 7
            assert result["status"] == "completed"
            assert str(tmp_path) in result["stdout"]
            assert sys.executable in result["stdout"]
            assert result["stderr"].strip() == "错误"
            assert result["pid"] != os.getpid()
            spill = Path(result["stdout_spill_path"])
            assert spill.read_bytes().decode("utf-8").strip() == result["stdout"].strip()
        finally:
            await manager.close()
        assert not spill.exists()
    run(scenario())


@pytest.mark.parametrize("args", [
    {"code": "print('never')", "timeout": -1},
    {"code": "print('never')", "timeout": float("nan")},
    {"code": "print('never')", "timeout": float("inf")},
    {"code": "print('never')", "timeout": True},
    {"code": "print('never')", "run_in_background": "false"},
    {"code": "print('never')", "executable": "evil.exe"},
    {"code": "print('never')", "cwd": "C:/"},
    {"code": "print('never')", "owner": "alice"},
    {"code": "\x00"}, {},
])
def test_validation_precedes_spawn(tmp_path, monkeypatch, args):
    async def forbidden(*args, **kwargs):
        pytest.fail("invalid arguments reached spawn")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            with pytest.raises(AgentToolError) as error:
                await manager.execute("run_python", args, OWNER)
            assert error.value.code == "invalid_arguments"
        finally:
            await manager.close()
    run(scenario())


def test_context_is_mandatory(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            for context in (None, {}, {"owner": "alice", "chat_flow_id": "test:one"}):
                with pytest.raises(AgentToolError) as error:
                    await manager.execute("job_list", {}, context)
                assert error.value.code == "unauthorized"
        finally:
            await manager.close()
    run(scenario())


def test_output_capture_and_global_disk_cap(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path, config={"output_limit_bytes": 128, "max_spill_bytes": 1200})
        try:
            for _ in range(2):
                result = await manager.execute("run_python", {"code": "import sys; sys.stdout.write('x'*10000); sys.stderr.write('y'*8000)"}, OWNER)
                assert len(result["stdout"]) == len(result["stderr"]) == 128
                assert result["stdout_bytes"] == 10000 and result["stderr_bytes"] == 8000
                assert result["stdout_truncated"] and result["stderr_truncated"]
                assert not result["stdout_spill_complete"] and not result["stderr_spill_complete"]
            assert sum(path.stat().st_size for path in Path(manager._spill_dir.name).iterdir()) == 1200
        finally:
            await manager.close()
    run(scenario())


def test_foreground_total_timeout(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            result = await manager.execute("run_python", {"code": "import time; print('ready',flush=True); time.sleep(60)", "timeout": .5}, OWNER)
            assert result["timed_out"] and result["status"] == "timed_out"
            assert result["exit_code"] is not None
            assert "ready" in result["stdout"]
            assert not manager._records
        finally:
            await manager.close()
    run(scenario())


def test_jobs_incremental_completion_callback_and_isolation(tmp_path):
    async def scenario():
        completed = asyncio.Event()
        notifications = []
        async def notify(context, result):
            notifications.append((context, result))
            completed.set()
        manager = ProcessTools(lambda context: tmp_path, completion_callback=notify)
        try:
            job = await manager.execute("run_python", {"code": "import time; print('first',flush=True); time.sleep(.4); print('second',flush=True)", "run_in_background": True}, OWNER)
            job_id = job["job_id"]
            for context in (FOREIGN, OTHER_FLOW):
                assert await manager.execute("job_list", {}, context) == {"jobs": []}
                for name in ("job_output", "job_kill"):
                    with pytest.raises(AgentToolError) as error:
                        await manager.execute(name, {"job_id": job_id}, context)
                    assert error.value.code == "not_found"
            first = await manager.execute("job_output", {"job_id": job_id, "wait": True, "timeout": 3}, OWNER)
            assert "first" in first["stdout"]
            await asyncio.wait_for(completed.wait(), 5)
            second = await manager.execute("job_output", {"job_id": job_id, "wait": True}, OWNER)
            assert second["status"] == "completed" and second["exit_code"] == 0
            assert "first" not in second["stdout"]
            assert "second" in first["stdout"] + second["stdout"]
            empty = await manager.execute("job_output", {"job_id": job_id}, OWNER)
            assert empty["stdout"] == empty["stderr"] == ""
            assert len(notifications) == 1 and notifications[0][0] == OWNER
            assert "first" in notifications[0][1]["stdout"]
        finally:
            await manager.close()
    run(scenario())


def test_wait_bound_caps_and_kill(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path, config={"max_jobs_per_owner": 1})
        try:
            job = await manager.execute("run_python", {"code": "import time; time.sleep(60)", "run_in_background": True}, OWNER)
            with pytest.raises(AgentToolError) as error:
                await manager.execute("run_python", {"code": "print('never')", "run_in_background": True}, OTHER_FLOW)
            assert error.value.code == "resource_limit"
            start = asyncio.get_running_loop().time()
            out = await manager.execute("job_output", {"job_id": job["job_id"], "wait": True, "timeout": .15}, OWNER)
            elapsed = asyncio.get_running_loop().time() - start
            assert .1 <= elapsed < 1 and out["status"] == "running"
            result = await manager.execute("job_kill", {"job_id": job["job_id"]}, OWNER)
            assert result["cancelled"] and result["exit_code"] is not None
            assert (await manager.execute("job_output", {"job_id": job["job_id"]}, OWNER))["cancelled"]
        finally:
            await manager.close()
    run(scenario())


def test_caller_cancellation_and_close_reap(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        original = manager._start
        started = asyncio.Event()
        records = []
        async def track(*args, **kwargs):
            record = await original(*args, **kwargs)
            records.append(record)
            started.set()
            return record
        manager._start = track
        task = asyncio.create_task(manager.execute("run_python", {"code": "import time; time.sleep(60)"}, OWNER))
        try:
            await asyncio.wait_for(started.wait(), 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert records[0].done.is_set() and records[0].process.returncode is not None
            await manager.execute("run_python", {"code": "import time; time.sleep(60)", "run_in_background": True}, OWNER)
            await manager.close()
            assert all(r.done.is_set() and r.process.returncode is not None for r in records)
            await manager.close()
            with pytest.raises(AgentToolError) as error:
                await manager.execute("job_list", {}, OWNER)
            assert error.value.code == "closed"
        finally:
            await manager.close()
    run(scenario())


def test_platform_shell_nonzero_and_dialect(tmp_path):
    require_shell()
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            result = await manager.execute("execute_command", {"command": shell_code("[Console]::Out.WriteLine('ok'); [Console]::Error.WriteLine('err'); exit 9", "printf 'ok\\n'; printf 'err\\n' >&2; exit 9")}, OWNER)
            assert result["exit_code"] == 9 and "ok" in result["stdout"] and "err" in result["stderr"]
            assert result["dialect"] in str(manager.definitions())
        finally:
            await manager.close()
    run(scenario())


def test_terminal_persistent_state_serialization_isolation_close(tmp_path):
    require_shell()
    (tmp_path / "sub").mkdir()
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            terminal = await manager.execute("terminal_open", {}, OWNER)
            assert terminal["status"] == "running" and terminal["pty"] is False and not terminal["supports_tui"]
            tid = terminal["terminal_id"]
            for context in (FOREIGN, OTHER_FLOW):
                assert await manager.execute("terminal_list", {}, context) == {"terminals": []}
                for name, args in (("terminal_read", {}), ("terminal_send", {"command": "echo forbidden"}), ("terminal_close", {}), ("terminal_signal", {"signal": "kill"})):
                    with pytest.raises(AgentToolError) as error:
                        await manager.execute(name, {"terminal_id": tid, **args}, context)
                    assert error.value.code == "not_found"
            setup = await manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("$persist = 'kept'; Set-Location sub", "persist=kept; cd sub")}, OWNER)
            assert setup["command_completed"] and setup["exit_code"] == 0
            one, two = await asyncio.gather(
                manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("Start-Sleep -Milliseconds 100; $persist += '-one'; $persist", "sleep .1; persist=$persist-one; printf '%s\\n' \"$persist\"")}, OWNER),
                manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("$persist; (Get-Location).Path; [Console]::Error.WriteLine('err')", "printf '%s\\n' \"$persist\"; pwd; printf 'err\\n' >&2")}, OWNER))
            assert one["command_completed"] and two["command_completed"]
            assert "kept-one" in one["stdout"] and "kept-one" in two["stdout"]
            assert "sub" in two["stdout"] and "err" in two["stderr"]
            assert "__NEOBOT_" not in str(one) + str(two)
            closed = await manager.execute("terminal_close", {"terminal_id": tid}, OWNER)
            assert closed["cancelled"] and closed["exit_code"] is not None
            with pytest.raises(AgentToolError) as error:
                await manager.execute("terminal_send", {"terminal_id": tid, "command": "echo closed"}, OWNER)
            assert error.value.code == "terminal_closed"
        finally:
            await manager.close()
    run(scenario())


def test_terminal_timeout_and_cancel(tmp_path):
    require_shell()
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            terminal = await manager.execute("terminal_open", {}, OWNER)
            tid = terminal["terminal_id"]
            result = await manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("Start-Sleep -Seconds 60", "sleep 60"), "timeout": .2}, OWNER)
            assert result["timed_out"] and not result["command_completed"] and result["exit_code"] is not None
            terminal = await manager.execute("terminal_open", {}, OWNER)
            tid = terminal["terminal_id"]
            record = manager._records[tid]
            task = asyncio.create_task(manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("Start-Sleep -Seconds 60", "sleep 60")}, OWNER))
            # Let the coroutine enter its command write, without a process busy loop.
            await asyncio.sleep(.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert record.done.is_set() and record.status == "cancelled"
        finally:
            await manager.close()
    run(scenario())


@pytest.mark.parametrize("config", [{"max_jobs_per_owner": 0}, {"output_limit_bytes": True}, {"max_wait": float("nan")}, {"max_spill_bytes": -1}])
def test_invalid_config(config):
    with pytest.raises(ValueError):
        ProcessConfig(**config)


def test_spill_file_count_is_bounded(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path, config={"max_spill_files": 2})
        try:
            for _ in range(3):
                result = await manager.execute("run_python", {"code": "print('data')"}, OWNER)
            assert result["stdout"].strip() == "data"
            assert not result["stdout_spill_complete"] and result["spill_limit_reached"]
            assert len(list(Path(manager._spill_dir.name).iterdir())) == 2
        finally:
            await manager.close()
    run(scenario())


def wait_until_dead(pid, timeout=5.0):
    """SIGKILL 是异步投递：给内核/init 一点回收时间，避免瞬时断言误报。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.02)
    return not pid_alive(pid)


def pid_alive(pid):
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            # An adopted zombie has terminated, even if init has not reaped it yet.
            stat = Path(f"/proc/{pid}/stat")
            return not (stat.exists() and stat.read_text().split()[2] == "Z")
        except ProcessLookupError:
            return False
    import ctypes
    from ctypes import wintypes as w
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    kernel.WaitForSingleObject.restype = w.DWORD
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


@pytest.mark.parametrize("parent_exits", [False, True])
def test_process_tree_reaped_even_after_parent_exit(tmp_path, parent_exits):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            code = ("import subprocess,sys,time; "
                    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
                    "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                    "print(child.pid, flush=True); " + ("sys.exit(0)" if parent_exits else "time.sleep(60)"))
            job = await manager.execute("run_python", {"code": code, "run_in_background": True}, OWNER)
            result = await manager.execute("job_output", {"job_id": job["job_id"], "wait": True, "timeout": 5}, OWNER)
            child_pid = int(result["stdout"].strip())
            if parent_exits:
                await asyncio.wait_for(manager._records[job["job_id"]].done.wait(), 5)
                assert wait_until_dead(child_pid)
            await manager.close()
            assert wait_until_dead(child_pid)
        finally:
            await manager.close()
    run(scenario())


def test_terminal_nonzero_signal_and_cap(tmp_path):
    require_shell()
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path, config={"max_terminals_per_owner": 1})
        try:
            terminal = await manager.execute("terminal_open", {}, OWNER)
            tid = terminal["terminal_id"]
            with pytest.raises(AgentToolError) as error:
                await manager.execute("terminal_open", {}, OTHER_FLOW)
            assert error.value.code == "resource_limit"
            result = await manager.execute("terminal_send", {"terminal_id": tid, "command": shell_code("throw 'expected failure'", "false")}, OWNER)
            assert result["exit_code"] != 0 and result["command_completed"]
            alive = await manager.execute("terminal_send", {"terminal_id": tid, "command": "echo alive"}, OWNER)
            assert alive["exit_code"] == 0 and "alive" in alive["stdout"]
            result = await manager.execute("terminal_signal", {"terminal_id": tid, "signal": "terminate"}, OWNER)
            assert result["cancelled"] and result["exit_code"] is not None
        finally:
            await manager.close()
    run(scenario())


def test_job_output_wait_cancellation_does_not_cancel_job(tmp_path):
    async def scenario():
        manager = ProcessTools(lambda context: tmp_path)
        try:
            job = await manager.execute("run_python", {"code": "import time; time.sleep(60)", "run_in_background": True}, OWNER)
            task = asyncio.create_task(manager.execute("job_output", {"job_id": job["job_id"], "wait": True}, OWNER))
            await asyncio.sleep(.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (await manager.execute("job_list", {}, OWNER))["jobs"][0]["status"] == "running"
        finally:
            await manager.close()
    run(scenario())

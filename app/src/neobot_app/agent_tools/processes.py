"""Host-authenticated process tools; ownership checks are NOT an OS sandbox.

The adapter must authenticate/authorize before calling execute and provide a trusted
workspace resolver. Commands are arbitrary host code, always run in subprocesses.
Resources are scoped to (context.owner, context.chat_flow_id), never model arguments.
Terminals are persistent UTF-8 pipe shells, not PTYs: no TUI or interactive stdin.
Spills are private temporary files, bounded globally and removed by close().
"""
from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .contracts import AgentToolError, ToolContext, tool_definition

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProcessConfig:
    default_timeout: float = 30.0
    max_timeout: float = 300.0
    max_wait: float = 30.0
    output_limit_bytes: int = 64 * 1024  # per stream, including terminal history
    max_spill_bytes: int = 32 * 1024 * 1024  # total across this manager's lifetime
    max_spill_files: int = 512  # bound filesystem metadata as well as payload bytes
    max_jobs_per_owner: int = 8  # running processes, including foreground
    max_terminals_per_owner: int = 4
    max_records: int = 256  # retained background jobs + terminals + running commands
    max_command_chars: int = 128 * 1024
    cleanup_timeout: float = 5.0

    def __post_init__(self) -> None:
        for name in ("default_timeout", "max_timeout", "max_wait", "cleanup_timeout"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        if self.default_timeout > self.max_timeout:
            raise ValueError("default_timeout exceeds max_timeout")
        for name in ("output_limit_bytes", "max_spill_bytes", "max_spill_files", "max_jobs_per_owner", "max_terminals_per_owner", "max_records", "max_command_chars"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "max_spill_bytes" else 1):
                raise ValueError(f"Invalid {name}")


class _WindowsTree:
    """Kill-on-close Job Object, including children whose original parent exited.

    taskkill remains the fallback during launch/attachment failure. This is process
    lifecycle containment, not a filesystem, credential, or hostile-code sandbox.
    """

    def __init__(self, pid: int):
        import ctypes
        from ctypes import wintypes as w

        class BasicLimits(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                        ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", w.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", w.DWORD), ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

        class IOCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BasicLimits), ("IoInfo", IOCounters),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [w.LPVOID, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        process_handle = None
        try:
            limits = ExtendedLimits()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            process_handle = kernel.OpenProcess(0x0100 | 0x0001, False, pid)  # SET_QUOTA | TERMINATE
            if not process_handle or not kernel.AssignProcessToJobObject(self.handle, process_handle):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise
        finally:
            if process_handle:
                kernel.CloseHandle(process_handle)

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    async def terminate(self, timeout: float) -> None:
        # CloseHandle initiates termination asynchronously. Wait on real process
        # handles so a completed job never announces completion before its children
        # have actually stopped. Native bounded waits run off the event-loop thread.
        import ctypes
        from ctypes import wintypes as w
        import time

        kernel = self.kernel
        kernel.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID]
        kernel.QueryInformationJobObject.restype = w.BOOL
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.WaitForSingleObject.restype = w.DWORD
        handles = []
        capacity = 64
        try:
            while self.handle:
                buffer = ctypes.create_string_buffer(8 + capacity * ctypes.sizeof(ctypes.c_size_t))
                ok = kernel.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None)
                assigned = w.DWORD.from_buffer(buffer, 0).value
                count = w.DWORD.from_buffer(buffer, 4).value
                if not ok and ctypes.get_last_error() == 234 and assigned > capacity:
                    capacity = assigned
                    continue
                if ok:
                    pids = (ctypes.c_size_t * count).from_buffer(buffer, 8)
                    for pid in pids:
                        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                        if handle:
                            handles.append(handle)
                break
        finally:
            self.close()

        def wait_and_close() -> None:
            deadline = time.monotonic() + timeout
            try:
                for handle in handles:
                    milliseconds = max(0, int((deadline - time.monotonic()) * 1000))
                    kernel.WaitForSingleObject(handle, milliseconds)
            finally:
                for handle in handles:
                    kernel.CloseHandle(handle)

        if handles:
            await asyncio.to_thread(wait_and_close)


@dataclass
class _Capture:
    manager: "ProcessTools"
    path: Path
    data: bytearray = field(default_factory=bytearray)
    total: int = 0
    stored: int = 0
    spill_failed: bool = False

    def append(self, data: bytes) -> None:
        if not data:
            return
        self.total += len(data)
        self.data.extend(data)
        limit = self.manager.config.output_limit_bytes
        if len(self.data) > limit:
            del self.data[:-limit]
        budget = max(0, self.manager.config.max_spill_bytes - self.manager._spill_bytes)
        chunk = data[:budget]
        if chunk and not self.spill_failed:
            if self.stored == 0:
                if self.manager._spill_files >= self.manager.config.max_spill_files:
                    self.spill_failed = True
                    return
                self.manager._spill_files += 1
            # Bounded writes; no model code or shell ever executes in the host.
            # Reserve before writing: even a partial disk failure cannot bypass quota.
            self.manager._spill_bytes += len(chunk)
            try:
                with self.path.open("ab") as stream:
                    written = stream.write(chunk)
                self.stored += written
            except OSError:
                self.spill_failed = True

    def read(self, cursor: int) -> tuple[str, int]:
        start = self.total - len(self.data)
        lost = max(0, start - cursor)
        return bytes(self.data[max(0, cursor - start):]).decode("utf-8", errors="replace"), lost


@dataclass
class _Command:
    token: bytes
    done: asyncio.Event = field(default_factory=asyncio.Event)
    seen: dict[str, int] = field(default_factory=dict)
    pending: dict[str, bytes] = field(default_factory=lambda: {"stdout": b"", "stderr": b""})


@dataclass
class _Record:
    id: str
    context: ToolContext
    kind: str
    process: asyncio.subprocess.Process
    stdout: _Capture
    stderr: _Capture
    background: bool = False
    status: str = "running"
    task: asyncio.Task | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)
    stop_requested: asyncio.Event = field(default_factory=asyncio.Event)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    read_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stop_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    cursors: dict[str, int] = field(default_factory=lambda: {"stdout": 0, "stderr": 0})
    command: _Command | None = None
    shell: str | None = None
    dialect: str | None = None
    error: str | None = None
    windows_tree: _WindowsTree | None = None

    @property
    def owner(self) -> tuple[str, str]:
        return self.context.owner, self.context.chat_flow_id


class ProcessTools:
    """An event-loop-local process manager. A missing context is always rejected.

    completion_callback(context, result) may be sync or async; it is called once
    for each background job settled while the manager is open, outside execution. Callback
    failures are logged, never change the job result. close() cancels callbacks.
    """

    def __init__(self, workspace_resolver: Callable[[ToolContext], Path], *,
                 config: ProcessConfig | dict[str, Any] | None = None,
                 completion_callback: Callable[[ToolContext, dict[str, Any]], Any] | None = None):
        if not callable(workspace_resolver):
            raise TypeError("workspace_resolver must be callable")
        self.config = ProcessConfig(**config) if isinstance(config, dict) else (ProcessConfig() if config is None else config)
        if not isinstance(self.config, ProcessConfig):
            raise TypeError("config must be ProcessConfig or a mapping")
        if completion_callback is not None and not callable(completion_callback):
            raise TypeError("completion_callback must be callable")
        self.workspace_resolver = workspace_resolver
        self.completion_callback = completion_callback
        self._records: dict[str, _Record] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._close_task: asyncio.Task | None = None
        self._callbacks: set[asyncio.Task] = set()
        self._spill_dir: tempfile.TemporaryDirectory | None = None
        self._spill_bytes = 0
        self._spill_files = 0

    def _shell(self, requested: str | None = None) -> tuple[str, str, str]:
        name = requested or ("pwsh" if os.name == "nt" else "bash")
        if name == "pwsh":
            executable = shutil.which("pwsh")
            if executable:
                return name, executable, "PowerShell 7+ (pwsh)"
            if os.name == "nt" and (executable := shutil.which("powershell.exe")):
                return name, executable, "Windows PowerShell 5.1 (powershell.exe; not PowerShell 7)"
        elif name == "bash":
            if executable := shutil.which("bash"):
                return name, executable, "Bash"
        raise AgentToolError("shell_unavailable", f"Shell {name!r} is not installed")

    def definitions(self) -> list[dict[str, Any]]:
        platform_name = "pwsh" if os.name == "nt" else "bash"
        try:
            dialect = self._shell()[2]
        except AgentToolError:
            dialect = f"{platform_name} (not currently installed)"
        timeout = {"type": "number", "exclusiveMinimum": 0, "maximum": self.config.max_timeout}
        wait = {"type": "boolean", "description": "Wait for new output or completion, bounded by timeout."}
        wait_timeout = {"type": "number", "minimum": 0, "maximum": self.config.max_wait}
        command = {"type": "string", "minLength": 1, "maxLength": self.config.max_command_chars}
        run = {"timeout": timeout, "run_in_background": {"type": "boolean"}}
        job = {"job_id": {"type": "string"}}
        terminal = {"terminal_id": {"type": "string"}}
        return [
            tool_definition("run_python", "Run Python in a child process using the host's sys.executable and trusted workspace; no host exec.", {"code": command, **run}, ["code"]),
            tool_definition("execute_command", f"Run a one-shot {dialect} command in the trusted workspace; separate bounded stdout/stderr.", {"command": command, **run}, ["command"]),
            tool_definition(platform_name, f"Alias of execute_command, dialect: {dialect}.", {"command": command, **run}, ["command"]),
            tool_definition("job_list", "List only jobs owned by this trusted owner and chat flow."),
            tool_definition("job_output", "Read incremental bounded output; completed jobs remain collectible. Full spills expire at manager close.", {**job, "wait": wait, "timeout": wait_timeout}, ["job_id"]),
            tool_definition("job_kill", "Cancel a job and reap its process tree.", job, ["job_id"]),
            tool_definition("terminal_open", f"Open a persistent {dialect} pipe shell (NOT a PTY; no TUI or interactive stdin).", {}),
            tool_definition("terminal_send", "Serialize a command in the persistent shell and await exit markers on both streams. Timeout/cancellation closes the entire terminal. Do not run interactive stdin consumers.", {**terminal, "command": command, "timeout": timeout}, ["terminal_id", "command"]),
            tool_definition("terminal_read", "Read incremental bounded terminal output, with optional bounded event wait.", {**terminal, "wait": wait, "timeout": wait_timeout}, ["terminal_id"]),
            tool_definition("terminal_signal", "Cancel and close the whole terminal; interrupt is best-effort before tree termination.", {**terminal, "signal": {"type": "string", "enum": ["interrupt", "terminate", "kill"]}}, ["terminal_id", "signal"]),
            tool_definition("terminal_list", "List only terminals owned by this trusted owner and chat flow."),
            tool_definition("terminal_close", "Close and reap the persistent terminal process tree.", terminal, ["terminal_id"]),
        ]

    def _number(self, args: dict, name: str, default: float, maximum: float, *, zero: bool = False) -> float:
        value = args.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or (not zero and value == 0) or value > maximum:
            raise AgentToolError("invalid_arguments", f"{name} must be finite and {'nonnegative' if zero else 'positive'}, at most {maximum}")
        return float(value)

    def _text(self, args: dict, key: str) -> str:
        value = args.get(key)
        if not isinstance(value, str) or not value.strip() or "\x00" in value or len(value) > self.config.max_command_chars:
            raise AgentToolError("invalid_arguments", f"{key} must be nonempty text without NUL, within the command limit")
        return value

    def _validate(self, name: str, args: dict) -> None:
        definitions = {item["function"]["name"]: item["function"]["parameters"] for item in self.definitions()}
        if not isinstance(name, str) or name not in definitions:
            raise AgentToolError("unknown_tool", f"Unknown process tool: {name}")
        schema = definitions[name]
        if not isinstance(args, dict) or set(args) - set(schema["properties"]) or any(key not in args for key in schema["required"]):
            raise AgentToolError("invalid_arguments", "Missing or unknown tool arguments")
        for key in ("command", "code", "job_id", "terminal_id"):
            if key in args:
                self._text(args, key)
        for key in ("wait", "run_in_background"):
            if key in args and type(args[key]) is not bool:
                raise AgentToolError("invalid_arguments", f"{key} must be a boolean")
        if name in ("job_output", "terminal_read"):
            self._number(args, "timeout", self.config.max_wait, self.config.max_wait, zero=True)
        elif "timeout" in args:
            self._number(args, "timeout", self.config.default_timeout, self.config.max_timeout)
        if "signal" in args and args["signal"] not in ("interrupt", "terminate", "kill"):
            raise AgentToolError("invalid_arguments", "signal must be interrupt, terminate or kill")

    def _owned(self, record_id: str, context: ToolContext, kind: str) -> _Record:
        record = self._records.get(record_id)
        if record is None or record.owner != (context.owner, context.chat_flow_id) or record.kind != kind or (kind == "job" and not record.background):
            # Deliberately indistinguishable missing and foreign IDs.
            raise AgentToolError("not_found", f"{kind} not found")
        return record

    async def execute(self, name: str, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        if not isinstance(context, ToolContext) or not isinstance(context.owner, str) or not context.owner.strip() or not isinstance(context.chat_flow_id, str) or not context.chat_flow_id.strip():
            raise AgentToolError("unauthorized", "A trusted, nonempty ToolContext is required")
        if self._closed:
            raise AgentToolError("closed", "ProcessTools is closed")
        self._validate(name, args)  # All parameters checked before any process is started.
        if name in ("run_python", "execute_command", "pwsh", "bash"):
            timeout = self._number(args, "timeout", self.config.default_timeout, self.config.max_timeout)
            shell = None
            dialect = "Python"
            if name == "run_python":
                argv = [sys.executable, "-u", "-c", args["code"]]
            else:
                shell, executable, dialect = self._shell(None if name == "execute_command" else name)
                if shell == "pwsh":
                    code = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); " + args["command"]
                    argv = [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(code.encode("utf-16-le")).decode("ascii")]
                else:
                    argv = [executable, "--noprofile", "--norc", "-c", args["command"]]
            try:
                async with asyncio.timeout(timeout):
                    record = await self._start(argv, context, "job", timeout, bool(args.get("run_in_background")), shell, dialect)
            except TimeoutError as exc:
                raise AgentToolError("process_timeout", "Process launch exceeded its total timeout") from exc
            if record.background:
                return self._metadata(record)
            try:
                await asyncio.shield(record.task)
                return self._output(record, {"stdout": 0, "stderr": 0})
            except asyncio.CancelledError:
                await self._cancel_and_wait(record)
                raise
            finally:
                self._records.pop(record.id, None)
        if name in ("job_list", "terminal_list"):
            kind = "job" if name == "job_list" else "terminal"
            key = "jobs" if kind == "job" else "terminals"
            return {key: [self._metadata(record) for record in self._records.values()
                          if record.kind == kind and record.owner == (context.owner, context.chat_flow_id)
                          and (kind != "job" or record.background)]}
        if name == "terminal_open":
            shell, executable, dialect = self._shell()
            argv = ([executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", "-"] if shell == "pwsh"
                    else [executable, "--noprofile", "--norc"])
            started = asyncio.get_running_loop().time()
            try:
                async with asyncio.timeout(self.config.default_timeout):
                    record = await self._start(argv, context, "terminal", None, False, shell, dialect)
            except TimeoutError as exc:
                raise AgentToolError("process_timeout", "Terminal launch exceeded its total timeout") from exc
            try:
                # Startup is a real command handshake, not a synthetic ready flag.
                init = ("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; $ProgressPreference = 'SilentlyContinue'" if shell == "pwsh" else ":")
                remaining = max(0.001, self.config.default_timeout - (asyncio.get_running_loop().time() - started))
                ready = await self._terminal_send(record, init, remaining)
                if not ready.get("command_completed") or ready["exit_code"] != 0:
                    raise AgentToolError("terminal_start_failed", "Terminal handshake failed or timed out")
                return {**self._metadata(record), "pty": False, "supports_tui": False}
            except BaseException:
                await self._cancel_and_wait(record)
                raise
        kind = "job" if name.startswith("job_") else "terminal"
        record = self._owned(args[f"{kind}_id"], context, kind)
        if name in ("job_output", "terminal_read"):
            return await self._read_output(record, args)
        if name == "terminal_send":
            return await self._terminal_send(record, args["command"], self._number(args, "timeout", self.config.default_timeout, self.config.max_timeout))
        if name == "terminal_signal" and args["signal"] == "interrupt" and record.process.returncode is None:
            try:
                if os.name == "nt":
                    record.process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(record.process.pid, signal.SIGINT)
            except (OSError, ProcessLookupError):
                pass
        await self._cancel_and_wait(record)
        return self._output(record, record.cursors)

    async def _start(self, argv: list[str], context: ToolContext, kind: str,
                     timeout: float | None, background: bool, shell: str | None, dialect: str) -> _Record:
        started = asyncio.get_running_loop().time()
        async with self._lock:
            if self._closed:
                raise AgentToolError("closed", "ProcessTools is closed")
            # Caps are per owner across flows, even though access is more restrictive.
            running = sum(r.kind == kind and r.context.owner == context.owner and not r.done.is_set() for r in self._records.values())
            cap = self.config.max_jobs_per_owner if kind == "job" else self.config.max_terminals_per_owner
            if running >= cap or len(self._records) >= self.config.max_records:
                raise AgentToolError("resource_limit", "Process/retained-record limit reached")
            try:
                cwd = Path(self.workspace_resolver(context)).resolve(strict=True)
            except (OSError, TypeError, ValueError) as exc:
                raise AgentToolError("invalid_workspace", "Trusted workspace could not be resolved") from exc
            if not cwd.is_dir():
                raise AgentToolError("invalid_workspace", "Trusted workspace must be an existing directory")
            if self._spill_dir is None:
                self._spill_dir = tempfile.TemporaryDirectory(prefix="neobot-processes-")
            record_id = f"{kind}_{uuid.uuid4().hex}"
            root = Path(self._spill_dir.name)
            options: dict[str, Any] = {"cwd": str(cwd), "stdin": asyncio.subprocess.PIPE if kind == "terminal" else asyncio.subprocess.DEVNULL,
                                       "stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE,
                                       "env": {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                options["start_new_session"] = True
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(*argv, **options))
            try:
                process = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                process = await spawn
                await self._terminate_tree(process)
                # Drain the pipes as well, avoiding transport leaks on spawn cancellation.
                try:
                    await asyncio.wait_for(process.communicate(), self.config.cleanup_timeout)
                except asyncio.TimeoutError:
                    pass
                raise
            except (OSError, ValueError) as exc:
                raise AgentToolError("process_start_failed", str(exc)) from exc
            windows_tree = None
            if os.name == "nt":
                try:
                    windows_tree = _WindowsTree(process.pid)
                except OSError as exc:
                    # Never leave an uncontrolled running child if containment failed.
                    await self._terminate_tree(process)
                    try:
                        await asyncio.wait_for(process.communicate(), self.config.cleanup_timeout)
                    except TimeoutError:
                        pass
                    raise AgentToolError("process_start_failed", f"Windows process-tree attachment failed: {exc}") from exc
            record = _Record(record_id, context, kind, process,
                             _Capture(self, root / f"{record_id}.stdout"), _Capture(self, root / f"{record_id}.stderr"),
                             background=background, shell=shell, dialect=dialect, windows_tree=windows_tree)
            self._records[record_id] = record
            remaining = None if timeout is None else max(0, timeout - (asyncio.get_running_loop().time() - started))
            record.task = asyncio.create_task(self._watch(record, remaining), name=f"neobot:{record_id}")
            return record

    async def _terminate_tree(self, process: asyncio.subprocess.Process) -> None:
        if os.name == "nt":
            if process.returncode is None:
                try:
                    killer = await asyncio.create_subprocess_exec("taskkill.exe", "/PID", str(process.pid), "/T", "/F",
                                                                 stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                                                                 stderr=asyncio.subprocess.DEVNULL)
                    try:
                        await asyncio.wait_for(killer.wait(), self.config.cleanup_timeout)
                    except asyncio.TimeoutError:
                        killer.kill()
                        await killer.wait()
                except OSError:
                    pass
        else:
            # killpg works even when the original group leader has already exited.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass

    async def _cancel_and_wait(self, record: _Record, status: str = "cancelled") -> None:
        async with record.stop_lock:
            if not record.done.is_set():
                record.status = status
                record.stop_requested.set()
        if record.task is not None:
            await asyncio.shield(record.task)

    def _terminal_feed(self, record: _Record, stream: str, data: bytes, *, eof: bool = False) -> None:
        capture = getattr(record, stream)
        command = record.command
        if command is None or stream in command.seen:
            capture.append(data)
            return
        pending = command.pending[stream] + data
        pattern = rb"\n" + re.escape(command.token) + rb":(-?\d+)__\r?\n"
        match = re.search(pattern, pending)
        if match:
            capture.append(pending[:match.start()])
            capture.append(pending[match.end():])
            command.pending[stream] = b""
            command.seen[stream] = int(match.group(1))
            if len(command.seen) == 2:
                command.done.set()
        elif eof:
            capture.append(pending)
            command.pending[stream] = b""
        else:
            # Withhold only a possible split marker; ordinary output streams live.
            prefix = b"\n" + command.token + b":"
            start = pending.find(prefix)
            if start >= 0 and len(pending) - start <= len(prefix) + 32:
                capture.append(pending[:start])
                command.pending[stream] = pending[start:]
            else:
                keep = next((size for size in range(min(len(prefix), len(pending)), 0, -1)
                             if pending.endswith(prefix[:size])), 0)
                capture.append(pending[:-keep] if keep else pending)
                command.pending[stream] = pending[-keep:] if keep else b""

    async def _pump(self, record: _Record, stream: str) -> None:
        reader = getattr(record.process, stream)
        while data := await reader.read(16 * 1024):
            if record.kind == "terminal":
                self._terminal_feed(record, stream, data)
            else:
                getattr(record, stream).append(data)
            record.changed.set()
        if record.kind == "terminal":
            self._terminal_feed(record, stream, b"", eof=True)
        record.changed.set()

    async def _watch(self, record: _Record, timeout: float | None) -> None:
        pumps = [asyncio.create_task(self._pump(record, stream)) for stream in ("stdout", "stderr")]

        async def settle() -> None:
            await record.process.wait()
            await asyncio.gather(*pumps)

        settled = asyncio.create_task(settle())
        stopped = asyncio.create_task(record.stop_requested.wait())
        try:
            finished, _ = await asyncio.wait((settled, stopped), timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not finished:
                record.status = "timed_out"
            elif settled in finished:
                settled.result()
                if record.status == "running":
                    record.status = "completed"
        except asyncio.CancelledError:
            if record.status == "running":
                record.status = "cancelled"
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
        finally:
            if record.windows_tree is not None:
                await record.windows_tree.terminate(self.config.cleanup_timeout)
            await self._terminate_tree(record.process)
            try:
                async with asyncio.timeout(self.config.cleanup_timeout):
                    await record.process.wait()
                    await asyncio.gather(*pumps, return_exceptions=True)
            except TimeoutError:
                for pump in pumps:
                    pump.cancel()
                await asyncio.gather(*pumps, return_exceptions=True)
            settled.cancel()
            stopped.cancel()
            await asyncio.gather(settled, stopped, return_exceptions=True)
            record.done.set()
            record.changed.set()
            if record.background and self.completion_callback and not self._closed:
                task = asyncio.create_task(self._notify(record))
                self._callbacks.add(task)
                task.add_done_callback(self._callbacks.discard)

    async def _notify(self, record: _Record) -> None:
        try:
            async with asyncio.timeout(self.config.max_wait):
                result = self.completion_callback(record.context, self._output(record, {"stdout": 0, "stderr": 0}, advance=False))
                if inspect.isawaitable(result):
                    await result
        except Exception:
            _LOG.exception("Process completion callback failed for %s", record.id)

    def _metadata(self, record: _Record) -> dict[str, Any]:
        return {f"{record.kind}_id": record.id, "status": record.status, "exit_code": record.process.returncode,
                "pid": record.process.pid, "dialect": record.dialect,
                "timed_out": record.status == "timed_out", "cancelled": record.status == "cancelled"}

    def _output(self, record: _Record, cursors: dict[str, int], *, advance: bool = True) -> dict[str, Any]:
        result = self._metadata(record)
        for stream in ("stdout", "stderr"):
            capture: _Capture = getattr(record, stream)
            text, lost = capture.read(cursors[stream])
            result[stream] = text
            result[f"{stream}_bytes"] = capture.total
            result[f"{stream}_dropped_bytes"] = lost
            result[f"{stream}_truncated"] = lost > 0
            result[f"{stream}_spill_path"] = str(capture.path) if capture.stored else None
            result[f"{stream}_spill_complete"] = capture.stored == capture.total and not capture.spill_failed
            if advance:
                cursors[stream] = capture.total
        result["spill_limit_reached"] = (self._spill_bytes >= self.config.max_spill_bytes
                                         or self._spill_files >= self.config.max_spill_files)
        if record.error:
            result["error"] = record.error
        return result

    async def _read_output(self, record: _Record, args: dict) -> dict[str, Any]:
        timeout = self._number(args, "timeout", self.config.max_wait, self.config.max_wait, zero=True)
        # Bound lock queueing as well as the wait itself; no busy polling.
        try:
            async with asyncio.timeout(timeout if args.get("wait") and timeout else None):
                async with record.read_lock:
                    if args.get("wait") and timeout and not record.done.is_set() and all(getattr(record, s).total == record.cursors[s] for s in ("stdout", "stderr")):
                        record.changed.clear()
                        await record.changed.wait()
                    return self._output(record, record.cursors)
        except TimeoutError:
            return self._output(record, record.cursors)

    def _wrapped_command(self, record: _Record, code: str, token: str) -> bytes:
        if record.shell == "pwsh":
            encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
            line = ("$global:LASTEXITCODE = 0; $global:__nb_ok = $true; try { . ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')))); $global:__nb_ok = $? } catch { [Console]::Error.WriteLine($_.ToString()); $global:__nb_ok = $false }; "
                    "$global:__nb_code = 0; if (-not $global:__nb_ok) { $global:__nb_code = 1 }; if ($global:LASTEXITCODE -ne 0) { $global:__nb_code = $global:LASTEXITCODE }; "
                    "[Console]::Out.Write([string][char]10 + '" + token + ":' + $global:__nb_code + '__' + [char]10); [Console]::Error.Write([string][char]10 + '" + token + ":' + $global:__nb_code + '__' + [char]10)\n")
        else:
            # eval in the current shell preserves variables, functions and cwd.
            quoted = "'" + code.replace("'", "'\"'\"'") + "'"
            line = (f"eval {quoted}\n__nb_code=$?\nprintf '\\n{token}:%s__\\n' \"$__nb_code\"\nprintf '\\n{token}:%s__\\n' \"$__nb_code\" >&2\n")
        return line.encode("utf-8")

    async def _terminal_send(self, record: _Record, code: str, timeout: float) -> dict[str, Any]:
        command: _Command | None = None
        waiter: asyncio.Task | None = None
        exited: asyncio.Task | None = None
        try:
            async with asyncio.timeout(timeout):
                async with record.send_lock:
                    if record.done.is_set() or record.stop_requested.is_set() or record.process.returncode is not None:
                        raise AgentToolError("terminal_closed", "Terminal process has exited")
                    cursors = {s: getattr(record, s).total for s in ("stdout", "stderr")}
                    command = _Command(f"__NEOBOT_{uuid.uuid4().hex}".encode("ascii"))
                    record.command = command
                    record.process.stdin.write(self._wrapped_command(record, code, command.token.decode("ascii")))
                    await record.process.stdin.drain()
                    waiter = asyncio.create_task(command.done.wait())
                    exited = asyncio.create_task(record.done.wait())
                    await asyncio.wait((waiter, exited), return_when=asyncio.FIRST_COMPLETED)
                    result = self._output(record, cursors)
                    record.cursors.update(cursors)
                    if command.done.is_set():
                        result["exit_code"] = command.seen["stdout"]
                        result["command_completed"] = True
                    else:
                        result["command_completed"] = False
                    return result
        except TimeoutError:
            await self._cancel_and_wait(record, "timed_out")
            result = self._output(record, record.cursors)
            result["command_completed"] = False
            return result
        except asyncio.CancelledError:
            await self._cancel_and_wait(record)
            raise
        except (BrokenPipeError, ConnectionResetError) as exc:
            await self._cancel_and_wait(record)
            raise AgentToolError("terminal_closed", "Terminal input pipe is closed") from exc
        finally:
            for task in (waiter, exited):
                if task is not None:
                    task.cancel()
            await asyncio.gather(*(t for t in (waiter, exited) if t is not None), return_exceptions=True)
            if command is not None and record.command is command:
                # Flush partial markers on timeout/exit before releasing command state.
                for stream in ("stdout", "stderr"):
                    self._terminal_feed(record, stream, b"", eof=True)
                record.command = None

    async def close(self) -> None:
        """Idempotently reap all processes and remove all temporary spill files."""
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self) -> None:
        async with self._lock:
            self._closed = True
            records = list(self._records.values())
        await asyncio.gather(*(self._cancel_and_wait(record) for record in records))
        callbacks = list(self._callbacks)
        for task in callbacks:
            task.cancel()
        await asyncio.gather(*callbacks, return_exceptions=True)
        self._records.clear()
        if self._spill_dir is not None:
            self._spill_dir.cleanup()
            self._spill_dir = None

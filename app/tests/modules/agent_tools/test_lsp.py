"""LSP contract tests using a real, dependency-free stdio server subprocess."""
from __future__ import annotations

import asyncio
import json
import sys
import pytest

from neobot_app.agent_tools.contracts import ToolContext
from neobot_app.agent_tools.lsp import LspTools


_SERVER = r'''
import json, os, sys, time
from pathlib import Path

def send(value):
    raw = json.dumps(value).encode("utf-8")
    sys.stdout.buffer.write(b"Content-Length: " + str(len(raw)).encode() + b"\r\n\r\n" + raw)
    sys.stdout.buffer.flush()

def read():
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError()
        if line == b"\r\n":
            break
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1])
    return json.loads(sys.stdin.buffer.read(length))

mode = sys.argv[1]
root = Path.cwd()
(root / "server-started").write_text(str(os.getpid()))
document = {}
while True:
    try:
        request = read()
    except EOFError:
        break
    method = request.get("method", "")
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"capabilities": {"positionEncoding": "utf-8" if mode == "encoding" else "utf-16"}}})
    elif method == "textDocument/didOpen":
        document = request["params"]["textDocument"]
    elif method.startswith("textDocument/") and "id" in request:
        (root / "request-started").write_text(str(os.getpid()))
        if mode == "timeout":
            time.sleep(60)
        if mode == "oversize":
            sys.stdout.buffer.write(b"Content-Length: 999999999\r\n\r\n")
            sys.stdout.buffer.flush()
            time.sleep(60)
        if mode == "duplicate":
            sys.stdout.buffer.write(b"Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}")
            sys.stdout.buffer.flush()
            time.sleep(60)
        if mode == "header":
            sys.stdout.buffer.write(b"X:" + b"x" * 9000 + b"\r\n\r\n")
            sys.stdout.buffer.flush()
            time.sleep(60)
        if mode == "error":
            send({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -1, "message": "SECRET SERVER DETAIL"}})
            continue
        pos = request["params"]["position"]
        location_range = {"start": pos, "end": {"line": pos["line"], "character": pos["character"] + 1}}
        if method == "textDocument/hover":
            result = {"contents": {"kind": "markdown", "value": json.dumps({"pid": os.getpid(), "position": pos, "text": document.get("text"), "root": str(root)})}, "range": location_range}
        else:
            # Both Location and LocationLink, plus out-of-workspace locations.
            result = [
                {"uri": document["uri"], "range": location_range},
                {"targetUri": (root / "target.py").as_uri(), "targetSelectionRange": location_range},
                {"uri": (root.parent / "other-owner" / "private.py").as_uri(), "range": location_range},
                {"uri": "https://example.invalid/private.py", "range": location_range},
            ]
        # A server-initiated edit must be refused; diagnostics must not leak.
        send({"jsonrpc": "2.0", "id": "server-edit", "method": "workspace/applyEdit", "params": {"edit": {}}})
        reply = read()
        assert reply["error"]["code"] == -32601
        send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"private": "SECRET SERVER DETAIL"}})
        send({"jsonrpc": "2.0", "id": request["id"], "result": result})
'''


@pytest.fixture
def setup_lsp(tmp_path):
    script = tmp_path / "mock_server.py"
    script.write_text(_SERVER, encoding="utf-8")
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "sample.py").write_text("a😀b = 1\n", encoding="utf-8")
    (root / "target.py").write_text("target = 1\n", encoding="utf-8")

    def build(mode="normal", **kwargs):
        return LspTools(lambda context: root, {".py": {"command": [sys.executable, "-B", str(script), mode], "language_id": "python"}}, **kwargs)

    return root, build


def test_deployment_executable_is_resolved_before_owner_cwd(setup_lsp):
    _, build = setup_lsp
    tools = build()
    configured = tools._servers[".py"][0]
    assert configured[0] == str(__import__("pathlib").Path(sys.executable).resolve())


def context(owner="owner-a"):
    return ToolContext(owner=owner, chat_flow_id="group:123", user_id=123, human_request=True)


def arguments(operation="hover", **kwargs):
    return {"operation": operation, "path": "sample.py", "line": 1, "column": 4, **kwargs}


async def test_unconfigured_is_not_registered_and_never_starts(tmp_path):
    tools = LspTools(lambda ctx: tmp_path, {})
    assert tools.definitions() == []
    assert (await tools.execute("lsp", arguments(), context()))["error"]["code"] == "tool_unavailable"
    assert not tools._clients
    await tools.close()


@pytest.mark.parametrize("operation", ["definition", "references", "implementation", "hover"])
async def test_real_server_operations_and_utf16_positions(setup_lsp, operation):
    root, build = setup_lsp
    tools = build()
    assert not (root / "server-started").exists()
    try:
        result = await tools.execute("lsp", arguments(operation), context())
        assert result["ok"], result
        assert result["position_encoding"] == "utf-16"
        assert result["position_base"] == 1
        if operation == "hover":
            content = json.loads(result["contents"])
            assert content["position"] == {"line": 0, "character": 3}
            assert content["text"] == (root / "sample.py").read_bytes().decode("utf-8")
            assert result["range"]["start"] == {"line": 1, "column": 4}
        else:
            assert [item["path"] for item in result["locations"]] == ["sample.py", "target.py"]
            assert result["locations"][0]["range"]["start"] == {"line": 1, "column": 4}
        assert "SECRET SERVER DETAIL" not in json.dumps(result)
        processes = [server.process for server in tools._clients.values()]
    finally:
        await tools.close()
    assert all(process.returncode is not None for process in processes)


async def test_owner_isolation_and_server_reuse(setup_lsp):
    _, build = setup_lsp
    tools = build()
    try:
        a, b = await asyncio.gather(
            tools.execute("lsp", arguments(), context("a")),
            tools.execute("lsp", arguments(), context("b")),
        )
        again = await tools.execute("lsp", arguments(), context("a"))
        assert json.loads(a["contents"])["pid"] != json.loads(b["contents"])["pid"]
        assert json.loads(a["contents"])["pid"] == json.loads(again["contents"])["pid"]
    finally:
        await tools.close()


@pytest.mark.parametrize("updates, code", [
    ({"path": "../other-owner/private.py"}, "path_out_of_scope"),
    ({"command": ["untrusted"]}, "invalid_arguments"),
    ({"owner": "other-owner"}, "invalid_arguments"),
    ({"line": 0}, "invalid_arguments"),
    ({"column": True}, "invalid_arguments"),
    ({"line": 100}, "invalid_arguments"),
    ({"operation": "rename"}, "invalid_arguments"),
])
async def test_invalid_or_unsafe_arguments_do_not_spawn(setup_lsp, updates, code):
    root, build = setup_lsp
    tools = build()
    args = arguments()
    args.update(updates)
    try:
        result = await tools.execute("lsp", args, context())
        assert result["error"]["code"] == code
        assert not tools._clients
        assert not (root / "server-started").exists()
    finally:
        await tools.close()


@pytest.mark.parametrize("mode, code", [
    ("timeout", "lsp_timeout"), ("oversize", "lsp_protocol_error"),
    ("duplicate", "lsp_protocol_error"), ("header", "lsp_protocol_error"),
    ("encoding", "lsp_encoding"), ("error", "lsp_server_error"),
])
async def test_timeout_and_malformed_server_cleanup(setup_lsp, mode, code):
    _, build = setup_lsp
    tools = build(mode, timeout_seconds=0.8)
    try:
        result = await tools.execute("lsp", arguments(), context())
        assert result["error"]["code"] == code, result
        assert not tools._clients
        assert "SECRET SERVER DETAIL" not in json.dumps(result)
    finally:
        await tools.close()


async def test_cancellation_reaps_real_server(setup_lsp):
    root, build = setup_lsp
    tools = build("timeout", timeout_seconds=15)
    task = asyncio.create_task(tools.execute("lsp", arguments(), context()))
    try:
        # Bounded async test wait, not a production busy poll.
        async with asyncio.timeout(5):
            while not (root / "request-started").exists():
                await asyncio.sleep(0.01)
        process = next(iter(tools._clients.values())).process
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.returncode is not None
        assert not tools._clients
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await tools.close()


async def test_result_limits_and_close_rejection(setup_lsp):
    _, build = setup_lsp
    tools = build(max_results=1, max_hover_chars=8)
    try:
        result = await tools.execute("lsp", arguments("definition"), context())
        assert len(result["locations"]) == 1 and result["truncated"]
        result = await tools.execute("lsp", arguments(), context())
        assert len(result["contents"]) == 8 and result["truncated"]
    finally:
        await tools.close()
    assert (await tools.execute("lsp", arguments(), context()))["error"]["code"] == "lsp_closed"


async def test_close_during_startup_reaps_process(setup_lsp, monkeypatch):
    _, build = setup_lsp
    real_spawn = asyncio.create_subprocess_exec
    started = asyncio.Event()
    release = asyncio.Event()
    processes = []

    async def delayed_spawn(*args, **kwargs):
        process = await real_spawn(*args, **kwargs)
        if "taskkill.exe" not in str(args[0]).lower():
            processes.append(process)
            started.set()
            await release.wait()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed_spawn)
    tools = build()
    task = asyncio.create_task(tools.execute("lsp", arguments(), context()))
    await asyncio.wait_for(started.wait(), 5)
    closing = asyncio.create_task(tools.close())
    release.set()
    try:
        await asyncio.wait_for(closing, 5)
        await asyncio.wait_for(task, 5)
        assert processes and all(process.returncode is not None for process in processes)
        assert not tools._clients
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, closing, return_exceptions=True)
        await tools.close()


async def test_canceling_queued_call_does_not_kill_active_owner_server(setup_lsp):
    root, build = setup_lsp
    tools = build("timeout", timeout_seconds=15)
    active = asyncio.create_task(tools.execute("lsp", arguments(), context()))
    queued = None
    try:
        async with asyncio.timeout(5):
            while not (root / "request-started").exists():
                await asyncio.sleep(0.01)
        process = next(iter(tools._clients.values())).process
        queued = asyncio.create_task(tools.execute("lsp", arguments(), context()))
        await asyncio.sleep(0.02)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert process.returncode is None
        assert len(tools._clients) == 1
    finally:
        active.cancel()
        if queued is not None:
            queued.cancel()
        await asyncio.gather(active, *([queued] if queued is not None else []), return_exceptions=True)
        await tools.close()


async def test_workspace_identity_is_part_of_server_key(setup_lsp):
    root, build = setup_lsp
    tools = build()
    other = root.parent / "second-workspace"
    other.mkdir()
    (other / "sample.py").write_text("sample = 2", encoding="utf-8")
    try:
        first = await tools.execute("lsp", arguments(), context())
        tools._workspace_resolver = lambda ctx: other
        second = await tools.execute("lsp", arguments(), context())
        assert first["ok"] and second["ok"]
        assert json.loads(first["contents"])["pid"] != json.loads(second["contents"])["pid"]
        assert len(tools._clients) == 2
    finally:
        await tools.close()

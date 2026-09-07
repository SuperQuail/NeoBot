"""Owner-isolated lazy stdio LSP client; commands are deployment-owned."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .contracts import AgentToolError, ToolContext, tool_definition

_METHODS = {
    "definition": "textDocument/definition",
    "references": "textDocument/references",
    "implementation": "textDocument/implementation",
    "hover": "textDocument/hover",
}


def _inside(path: Path, root: Path) -> bool:
    return path.is_relative_to(root)


def _position(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError("Invalid LSP position")
    line, character = value.get("line"), value.get("character")
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (line, character)):
        raise ValueError("Invalid LSP position")
    return {"line": line + 1, "column": character + 1}


def _range(value: Any) -> dict[str, Any]:
    return {"start": _position(value["start"]), "end": _position(value["end"])}


class _Server:
    def __init__(self, command: list[str], root: Path, *, max_frame_bytes: int) -> None:
        self.command = command
        self.root = root
        self.max_frame_bytes = max_frame_bytes
        self.process: asyncio.subprocess.Process | None = None
        self.stderr_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.next_id = 0
        self.active_id: int | None = None
        self.closed = False
        self.initialized = False
        self._start_task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self.closed:
            raise AgentToolError("lsp_unavailable", "LSP server is closed")
        if self.process is not None:
            return
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        self._start_task = asyncio.create_task(asyncio.create_subprocess_exec(
            *self.command, cwd=str(self.root), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=8192, **options,
        ))
        # Cancellation must not lose the child between creation and assignment.
        try:
            self.process = await asyncio.shield(self._start_task)
        except OSError as exc:
            raise AgentToolError("lsp_unavailable", "Language server executable could not be started") from exc
        if self.closed:
            raise AgentToolError("lsp_closed", "LSP server was closed during startup")
        self.stderr_task = asyncio.create_task(self._drain_stderr())

    async def _drain_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        while await self.process.stderr.read(4096):
            pass  # Never retain or surface potentially sensitive server diagnostics.

    async def send(self, value: dict[str, Any]) -> None:
        if self.closed or self.process is None or self.process.stdin is None:
            raise AgentToolError("lsp_unavailable", "LSP server is unavailable")
        raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
        if len(raw) > self.max_frame_bytes:
            raise AgentToolError("lsp_limit", "LSP request exceeds frame limit")
        self.process.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw)
        await self.process.stdin.drain()

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def _read(self) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        reader = self.process.stdout
        header_bytes = 0
        length: int | None = None
        while True:
            line = await reader.readuntil(b"\r\n")
            header_bytes += len(line)
            if header_bytes > 8192:
                raise ValueError("LSP header limit")
            if line == b"\r\n":
                break
            name, separator, value = line[:-2].partition(b":")
            if not separator:
                raise ValueError("Invalid LSP header")
            if name.strip().lower() == b"content-length":
                value = value.strip()
                if length is not None or not value.isdigit() or len(value) > 10:
                    raise ValueError("Invalid LSP content length")
                length = int(value)
        if length is None or length <= 0 or length > self.max_frame_bytes:
            raise ValueError("LSP frame limit")
        result = json.loads((await reader.readexactly(length)).decode("utf-8"))
        if not isinstance(result, dict) or result.get("jsonrpc") != "2.0":
            raise ValueError("Invalid LSP response")
        return result

    async def request(self, method: str, params: dict[str, Any]) -> Any:
        self.next_id += 1
        request_id = self.next_id
        self.active_id = request_id
        await self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        for _ in range(256):
            response = await self._read()
            if "method" in response:
                if "id" in response:
                    # Do not grant workspace/applyEdit, executeCommand or other server requests.
                    await self.send({"jsonrpc": "2.0", "id": response["id"],
                                     "error": {"code": -32601, "message": "Client request unsupported"}})
                continue
            if response.get("id") != request_id:
                continue
            self.active_id = None
            if "error" in response:
                error = response["error"]
                if isinstance(error, dict) and error.get("code") == -32601:
                    raise AgentToolError("lsp_unsupported_operation", "Language server does not support this operation")
                raise AgentToolError("lsp_server_error", "Language server rejected the request")
            return response.get("result")
        raise AgentToolError("lsp_limit", "Too many unrelated LSP messages")

    async def initialize(self) -> None:
        if self.initialized:
            return
        await self.start()
        result = await self.request("initialize", {
            "processId": os.getpid(), "rootUri": self.root.as_uri(),
            "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
            "capabilities": {"general": {"positionEncodings": ["utf-16"]}},
        })
        capabilities = result.get("capabilities", {}) if isinstance(result, dict) else {}
        if capabilities.get("positionEncoding", "utf-16") != "utf-16":
            raise AgentToolError("lsp_encoding", "Language server must support UTF-16 positions")
        await self.notify("initialized", {})
        self.initialized = True

    async def close(self) -> None:
        if self._close_task is None:
            self._close_task = asyncio.create_task(self._close())
        await asyncio.shield(self._close_task)

    async def _close(self) -> None:
        if self.active_id is not None:
            try:
                await asyncio.wait_for(self.notify("$/cancelRequest", {"id": self.active_id}), 0.2)
            except Exception:
                pass
        self.closed = True
        if self.process is None and self._start_task is not None:
            try:
                self.process = await self._start_task
            except Exception:
                pass
        process = self.process
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            if process.returncode is None:
                try:
                    if os.name == "nt":
                        # A server may start helper processes. Kill its tree, not other owners.
                        taskkill = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe")
                        killer = await asyncio.create_subprocess_exec(
                            taskkill, "/PID", str(process.pid), "/T", "/F",
                            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        )
                        try:
                            await asyncio.wait_for(killer.wait(), 2)
                        except asyncio.TimeoutError:
                            killer.kill()
                            await killer.wait()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                await process.wait()
        if self.stderr_task is not None:
            self.stderr_task.cancel()
            await asyncio.gather(self.stderr_task, return_exceptions=True)


class LspTools:
    """Read-only navigation using configured commands, one server per owner/workspace.

    Paths and locations are workspace-relative. All line/column positions use
    one-based UTF-16 code units; no model argument controls server commands.
    Language servers are trusted deployment code, not an OS filesystem sandbox.
    """

    def __init__(
        self, workspace_resolver: Callable[[ToolContext], Path],
        servers: dict[str, dict[str, Any]], *, timeout_seconds: float = 15.0,
        max_servers: int = 16, max_frame_bytes: int = 2 * 1024 * 1024,
        max_file_bytes: int = 1024 * 1024, max_results: int = 100,
        max_hover_chars: int = 16 * 1024,
    ) -> None:
        if timeout_seconds <= 0 or min(max_servers, max_frame_bytes, max_file_bytes, max_results, max_hover_chars) <= 0:
            raise ValueError("LSP limits must be positive")
        self._workspace_resolver = workspace_resolver
        self._servers: dict[str, tuple[list[str], str]] = {}
        for extension, config in servers.items():
            command, language = config.get("command"), config.get("language_id")
            if (not isinstance(extension, str) or not extension.startswith(".")
                or not isinstance(command, list) or not command
                or not all(isinstance(item, str) and item and "\0" not in item for item in command)
                or not isinstance(language, str) or not language):
                raise ValueError("Invalid deployment LSP server configuration")
            # Resolve the executable before entering any owner-controlled cwd.
            # Otherwise a planted workspace executable could shadow a PATH name.
            executable = shutil.which(command[0]) or command[0]
            configured_command = [str(Path(executable).resolve()), *command[1:]]
            self._servers[extension.lower()] = (configured_command, language)
        self._timeout = timeout_seconds
        self._max_servers = max_servers
        self._max_frame_bytes = max_frame_bytes
        self._max_file_bytes = max_file_bytes
        self._max_results = max_results
        self._max_hover_chars = max_hover_chars
        self._clients: dict[tuple[str, str, str], _Server] = {}
        self._closed = False

    def definitions(self) -> list[dict[str, Any]]:
        if not self._servers:
            return []
        return [tool_definition("lsp",
            "Read-only language navigation: workspace-relative path, 1-based UTF-16 line/column. "
            "Only deployment-configured language servers are available.", {
                "operation": {"type": "string", "enum": list(_METHODS)},
                "path": {"type": "string"},
                "line": {"type": "integer", "minimum": 1},
                "column": {"type": "integer", "minimum": 1},
                "include_declaration": {"type": "boolean", "default": True},
            }, ["operation", "path", "line", "column"])]

    def _source(self, args: dict[str, Any], root: Path) -> tuple[Path, str]:
        value = args.get("path")
        if not isinstance(value, str) or not value or "\0" in value:
            raise AgentToolError("invalid_arguments", "A workspace file path is required")
        path = (root / value).resolve()
        if not _inside(path, root):
            raise AgentToolError("path_out_of_scope", "File must be inside the current workspace")
        with path.open("rb") as handle:
            content = handle.read(self._max_file_bytes + 1)
        if len(content) > self._max_file_bytes:
            raise AgentToolError("lsp_limit", "Source file exceeds size limit")
        return path, content.decode("utf-8-sig")

    def _locations(self, raw: Any, root: Path) -> tuple[list[dict[str, Any]], bool]:
        values = raw if isinstance(raw, list) else [raw] if raw else []
        result = []
        truncated = False
        for value in values:
            try:
                uri = value.get("targetUri", value.get("uri"))
                parsed = urlsplit(uri)
                if parsed.scheme != "file" or parsed.netloc not in ("", "localhost") or parsed.query or parsed.fragment:
                    continue
                name = unquote(parsed.path)
                if os.name == "nt" and len(name) > 2 and name[0] == "/" and name[2] == ":":
                    name = name[1:]
                target = Path(name)
                if not target.is_absolute():
                    continue
                target = target.resolve()
                if not _inside(target, root):
                    continue
                location = {"path": target.relative_to(root).as_posix(),
                            "range": _range(value.get("targetSelectionRange", value.get("range")))}
                if len(result) == self._max_results:
                    truncated = True
                    break
                result.append(location)
            except (AttributeError, KeyError, TypeError, ValueError, OSError):
                continue
        return result, truncated

    def _result(self, operation: str, raw: Any, root: Path) -> dict[str, Any]:
        base: dict[str, Any] = {"ok": True, "operation": operation, "position_encoding": "utf-16", "position_base": 1}
        if operation != "hover":
            base["locations"], base["truncated"] = self._locations(raw, root)
            return base
        contents = raw.get("contents", []) if isinstance(raw, dict) else []
        items = contents if isinstance(contents, list) else [contents]
        text = "\n\n".join(item if isinstance(item, str) else str(item.get("value", ""))
                            for item in items if isinstance(item, (str, dict)))
        base.update(contents=text[:self._max_hover_chars], truncated=len(text) > self._max_hover_chars)
        if isinstance(raw, dict) and "range" in raw:
            try:
                base["range"] = _range(raw["range"])
            except (KeyError, TypeError, ValueError):
                pass
        return base

    async def execute(self, name: str, args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        client = None
        key = None
        acquired = False
        try:
            if self._closed:
                raise AgentToolError("lsp_closed", "LSP tools are closed")
            if name != "lsp" or not self._servers:
                raise AgentToolError("tool_unavailable", "LSP is not configured")
            if not isinstance(context, ToolContext) or not context.owner:
                raise AgentToolError("missing_context", "Trusted tool context is required")
            if set(args) - {"operation", "path", "line", "column", "include_declaration"}:
                raise AgentToolError("invalid_arguments", "Unexpected LSP argument")
            operation = args.get("operation")
            if not isinstance(operation, str) or operation not in _METHODS:
                raise AgentToolError("invalid_arguments", "Unsupported LSP operation")
            line, column = args.get("line"), args.get("column")
            if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in (line, column)):
                raise AgentToolError("invalid_arguments", "line and column must be positive UTF-16 positions")
            if "include_declaration" in args and not isinstance(args["include_declaration"], bool):
                raise AgentToolError("invalid_arguments", "include_declaration must be boolean")
            root = Path(self._workspace_resolver(context)).resolve(strict=True)
            path, text = self._source(args, root)
            lines = text.split("\n")
            if line > len(lines) or column - 1 > len(lines[line - 1].rstrip("\r").encode("utf-16-le")) // 2:
                raise AgentToolError("invalid_arguments", "Position is outside the source file")
            extension = path.suffix.lower()
            if extension not in self._servers:
                raise AgentToolError("lsp_unconfigured", "No language server is configured for this extension")
            command, language = self._servers[extension]
            key = (context.owner, str(root), extension)
            client = self._clients.get(key)
            if client is None:
                if len(self._clients) >= self._max_servers:
                    raise AgentToolError("lsp_limit", "Too many active owner/workspace language servers")
                client = _Server(command, root, max_frame_bytes=self._max_frame_bytes)
                self._clients[key] = client
            # Queue waiting is bounded too; a canceled waiter must not kill another call.
            await asyncio.wait_for(client.lock.acquire(), timeout=self._timeout)
            acquired = True
            async with asyncio.timeout(self._timeout):
                await client.initialize()
                uri = path.as_uri()
                await client.notify("textDocument/didOpen", {"textDocument": {
                    "uri": uri, "languageId": language, "version": 1, "text": text,
                }})
                params: dict[str, Any] = {"textDocument": {"uri": uri}, "position": {"line": line - 1, "character": column - 1}}
                if operation == "references":
                    params["context"] = {"includeDeclaration": args.get("include_declaration", True)}
                raw = await client.request(_METHODS[operation], params)
                await client.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
                return self._result(operation, raw, root)
        except asyncio.CancelledError:
            if acquired and client is not None:
                await asyncio.shield(client.close())
                if self._clients.get(key) is client:
                    self._clients.pop(key, None)
            raise
        except Exception as exc:
            if acquired and client is not None:
                await client.close()
                if self._clients.get(key) is client:
                    self._clients.pop(key, None)
            if isinstance(exc, AgentToolError):
                code, message = exc.code, str(exc)
            elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
                code, message = "lsp_timeout", "Language server request timed out"
            elif isinstance(exc, (FileNotFoundError, IsADirectoryError, PermissionError, UnicodeError)):
                code, message = "file_unavailable", "Source file is unavailable or not UTF-8 text"
            else:
                code, message = "lsp_protocol_error", "Language server failed or returned an invalid response"
            return {"ok": False, "error": {"code": code, "message": message}}
        finally:
            if acquired and client is not None:
                client.lock.release()

    async def close(self) -> None:
        self._closed = True
        clients, self._clients = list(self._clients.values()), {}
        await asyncio.gather(*(client.close() for client in clients))

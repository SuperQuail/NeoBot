"""Bounded, observation-protected agent file tools shared with sandbox_manager.

API: AgentFileTools(service).execute(name, args, *, owner=trusted_run_id,
chat_flow_id=trusted_pipeline_key). Never obtain either identity from model args.
Files are shared within a flow; observations are isolated by (owner, flow, path).
Relative/absolute paths stay within that flow. Persistent access is explicit
shared:tools/... (see SandboxService.SHARED_DIRECTORIES). is_shared_write lets
an outer credential gate recognize writes; it does not grant authorization.

read: 1-based offset/limit lines; column is a 0-based Unicode character offset
for an oversized single line. Follow next_offset/next_column until None.
write: existing files need a complete observed version (sequential pages count).
edit: requires an observed version, but loads the COMPLETE bounded file itself.
expected_version is optional, but when present must match the owner's observation.
Successful writes/edits advance the owner observation for sequential edits.
For concurrent work, pass expected_version explicitly; other owners keep their
stale observation. Editing a partial read does not grant full-overwrite access.
Search is bounded, reports truncation explicitly, and has no implicit spill files.
Python regex runs ONLY in a killable child process with a hard timeout.
Locks coordinate this service in-process; arbitrary external writers must still
cooperate (the final version recheck is not an OS compare-and-swap primitive).
"""
from __future__ import annotations

import asyncio
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from neobot_app.runtime.sandbox_service import SandboxService, MAX_TEXT_READ_BYTES

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SEARCH_BYTES = 8 * 1024 * 1024
MAX_SCAN_ENTRIES = 10000
MAX_SCAN_FILES = 2000
MAX_SEARCH_SECONDS = 5.0
REGEX_TIMEOUT_SECONDS = 2.0
MAX_OBSERVATIONS = 4096

# Input/output are bounded by the parent; user regex never executes in its host.
_REGEX_WORKER = r'''
import json, re, sys
request = json.load(sys.stdin)
try:
    regex = re.compile(request["pattern"], re.I if request["ignore_case"] else 0)
except re.error as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(0)
results = []
truncated = False
for path, text in request["files"]:
    for number, line in enumerate(text.splitlines(), 1):
        if regex.search(line):
            if len(results) >= request["limit"]:
                truncated = True
                break
            results.append({"path": path, "lineNumber": number,
                            "line": line[:500], "line_truncated": len(line) > 500})
    if truncated:
        break
print(json.dumps({"matches": results, "truncated": truncated}))
'''


class FileToolError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _integer(args: dict, key: str, default: int, minimum: int, maximum: int) -> int:
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FileToolError("invalid_argument", f"{key} must be {minimum}..{maximum}")
    return value


def _string(args: dict, key: str, default: Any = None) -> str:
    value = args.get(key, default)
    if not isinstance(value, str):
        raise FileToolError("invalid_argument", f"{key} must be a string")
    return value


def _pattern(value: str) -> str:
    value = value.replace("\\", "/")
    if not value or len(value) > 512 or value.startswith("/") or ":" in value or ".." in value.split("/"):
        raise FileToolError("invalid_pattern", "Use a relative glob without parent traversal (max 512 characters)")
    return value


def _matches(path: str, pattern: str) -> bool:
    # No slash means basename matching at any depth (DSH convention).
    if "/" not in pattern:
        return fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], pattern)
    parts, patterns = path.split("/"), pattern.split("/")
    states = {0}
    for token in patterns:
        if token == "**":
            states = set(range(min(states), len(parts) + 1)) if states else set()
        else:
            states = {i + 1 for i in states if i < len(parts) and fnmatch.fnmatchcase(parts[i], token)}
    return len(parts) in states


class AgentFileTools:
    def __init__(self, sandbox_service: SandboxService):
        self.sandbox = sandbox_service

    def resolve_path(self, path: str, *, owner: str, chat_flow_id: str, write: bool = False) -> Path:
        """Public trusted path resolver for image/LSP and other caller adapters."""
        return self.sandbox.resolve_agent_path(path, owner=owner, chat_flow_id=chat_flow_id, write=write)

    @staticmethod
    def is_shared_write(name: str, args: dict, chat_flow_id: str | None = None) -> bool:
        return name in {"write", "edit", "write_file", "edit_file"} and str(
            args.get("file_path", args.get("path", ""))).startswith("shared:")

    @staticmethod
    def definitions() -> list[dict]:
        path = {"type": "string", "description": "Current-flow path, or explicit shared:tools/..."}
        version = {"type": "string", "description": "Version returned by your last read"}
        schemas = {
            "read": ({"file_path": path, "offset": {"type": "integer", "minimum": 1},
                      "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                      "column": {"type": "integer", "minimum": 0}}, ["file_path"],
                     "Read UTF-8 with numbered lines; follow next_offset/next_column for partial output."),
            "write": ({"file_path": path, "content": {"type": "string"}, "expected_version": version},
                      ["file_path", "content"], "Atomic UTF-8 write. Existing files require a complete prior read; empty content is valid."),
            "edit": ({"file_path": path, "old_string": {"type": "string"}, "new_string": {"type": "string"},
                      "replace_all": {"type": "boolean"}, "expected_version": version},
                     ["file_path", "old_string", "new_string"], "Edit complete UTF-8 file after read; old_string must be unique unless replace_all."),
            "glob": ({"path": path, "pattern": {"type": "string"},
                      "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ["pattern"],
                     "Find files only, newest first. Basename globs recurse. Bounded scan reports truncation."),
            "grep": ({"path": path, "pattern": {"type": "string"}, "include": {"type": "string"},
                      "ignore_case": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 250}},
                     ["pattern"], "Regex search with line numbers, bounded input/output and hard worker timeout."),
        }
        return [{"type": "function", "function": {"name": name, "description": description,
                 "parameters": {"type": "object", "properties": properties, "required": required,
                                "additionalProperties": False}}}
                for name, (properties, required, description) in schemas.items()]

    async def execute(self, name: str, args: dict, *, owner: str, chat_flow_id: str) -> dict:
        """The trusted caller must bind owner/flow, never forward model identities."""
        try:
            if not isinstance(args, dict):
                raise FileToolError("invalid_argument", "args must be an object")
            if "owner" in args or "chat_flow_id" in args or "pipeline_key" in args:
                raise FileToolError("untrusted_context", "Identity must be supplied by the trusted caller, not arguments")
            return await asyncio.to_thread(self._execute, name, dict(args), owner, chat_flow_id)
        except FileToolError as exc:
            return {"ok": False, "code": exc.code, "error": str(exc)}
        except PermissionError as exc:
            return {"ok": False, "code": "permission_denied", "error": str(exc)}
        except UnicodeDecodeError:
            return {"ok": False, "code": "not_utf8", "error": "File is not UTF-8 text"}
        except FileNotFoundError:
            return {"ok": False, "code": "not_found", "error": "File/directory does not exist"}
        except (ValueError, OSError) as exc:
            return {"ok": False, "code": "file_error", "error": str(exc)}

    def _execute(self, name: str, args: dict, owner: str, flow: str) -> dict:
        if name not in {"read", "write", "edit", "glob", "grep"}:
            raise FileToolError("unknown_tool", f"Unknown file tool: {name}")
        raw = _string(args, "file_path", args.get("path", "." if name in {"glob", "grep"} else None))
        path = self.sandbox.resolve_agent_path(raw, owner=owner, chat_flow_id=flow, write=name in {"write", "edit"})
        if name in {"glob", "grep"}:
            shared = raw.replace("\\", "/").split("/", 1)[0] if raw.startswith("shared:") else None
            shared_root = self.sandbox.resolve_agent_path(shared, owner=owner, chat_flow_id=flow) if shared else None

            def validate(candidate):
                value = shared + "/" + candidate.relative_to(shared_root).as_posix() if shared else str(candidate)
                return self.sandbox.resolve_agent_path(value, owner=owner, chat_flow_id=flow)

            return self._search(name, args, path, validate)
        with self.sandbox.file_lock(path):
            # Re-resolve under the lock, so queued operations cannot reuse an old link.
            checked = self.sandbox.resolve_agent_path(raw, owner=owner, chat_flow_id=flow, write=name != "read")
            if checked != path:
                raise FileToolError("stale_version", "Path changed; read again")
            return self._file_operation(name, args, path, owner, flow)

    async def execute_legacy(self, name: str, args: dict, *, owner: str, chat_flow_id: str | None) -> dict:
        """Compatibility only: legacy root/flow path authority is unchanged.

        Do NOT expose this adapter to new agents. Old edit-without-read remains
        available, but is now full-file, locked, atomic and explicitly reported.
        Existing-file write requires a complete prior legacy read.
        """
        def operation():
            raw = _string(args, "file_path", args.get("path", "."))
            resolver = self.sandbox.resolve_path if name in {"write", "edit"} else self.sandbox.resolve_read_path
            path = resolver(raw, chat_flow_id)
            if name in {"glob", "grep"}:
                def validate(candidate):
                    if not self.sandbox.is_path_allowed(candidate) or candidate.is_symlink():
                        raise PermissionError("path not allowed")
                return self._search(name, args, path, validate)
            with self.sandbox.file_lock(path):
                return self._file_operation(name, args, path, owner, chat_flow_id or "", legacy_edit=True)
        try:
            return await asyncio.to_thread(operation)
        except FileToolError as exc:
            prefix = {"ambiguous_match": "old_string 不唯一：", "no_match": "未找到匹配：",
                      "invalid_pattern": "正则表达式无效："}.get(exc.code, "")
            return {"ok": False, "code": exc.code, "error": prefix + str(exc)}
        except (OSError, ValueError) as exc:
            return {"ok": False, "code": "file_error", "error": str(exc)}

    def _observation(self, key):
        with self.sandbox._observations_guard:
            return self.sandbox._file_observations.get(key)

    def _observe(self, key, version: str | None, start: int, end: int, total: int):
        with self.sandbox._observations_guard:
            observations = self.sandbox._file_observations
            previous = observations.get(key)
            # Sequential pagination accumulates complete coverage without unbounded intervals.
            covered = previous[1] if previous and previous[0] == version else 0
            if start <= covered:
                covered = max(covered, end)
            observations[key] = (version, covered, covered >= total)
            observations.move_to_end(key)
            while len(observations) > MAX_OBSERVATIONS:
                observations.popitem(last=False)

    def _file_operation(self, name: str, args: dict, path: Path, owner: str, flow: str,
                        *, legacy_edit: bool = False) -> dict:
        key = (owner, flow, os.path.normcase(str(path)))
        exists = path.exists()
        data = self.sandbox.read_complete(path, MAX_FILE_BYTES) if exists else None
        version = self.sandbox.file_version(path, data) if data is not None else None
        if name == "read":
            if data is None:
                # A confirmed absence supersedes an old version, allowing safe
                # recreation after a delete without changing owner identity.
                self._observe(key, None, 0, 0, 0)
                raise FileNotFoundError(path)
            text = data.decode("utf-8")
            return self._read_page(args, path, text, len(data), version, key)
        if name == "edit" and data is None:
            raise FileNotFoundError(path)
        observation = self._observation(key)
        expected = args.get("expected_version")
        if expected is not None and (not observation or expected != observation[0]):
            raise FileToolError("stale_version", "expected_version does not match your observation; read again")
        if data is not None:
            if observation is None and not (legacy_edit and name == "edit" and expected is None):
                raise FileToolError("read_required", "Read this existing file before modifying it")
            if observation and observation[0] != version:
                raise FileToolError("stale_version", "File changed since your read; read again")
            if name == "write" and observation and not observation[2]:
                raise FileToolError("incomplete_read", "Only a partial view was read; use edit or read all pages before overwriting")
        elif (observation and observation[0] is not None) or expected is not None:
            raise FileToolError("stale_version", "Previously observed file was removed; read again to confirm absence")
        replacements = 0
        if name == "write":
            content = _string(args, "content")
        else:
            text = data.decode("utf-8")
            old, new = _string(args, "old_string"), _string(args, "new_string")
            replace_all = args.get("replace_all", False)
            if not isinstance(replace_all, bool) or not old:
                raise FileToolError("invalid_argument", "Nonempty old_string and boolean replace_all required")
            replacements = text.count(old)
            if not replacements:
                raise FileToolError("no_match", "old_string was not found")
            if replacements != 1 and not replace_all:
                raise FileToolError("ambiguous_match", f"old_string occurs {replacements} times; make it unique or set replace_all")
            new_size = len(data) + replacements * (len(new.encode("utf-8")) - len(old.encode("utf-8")))
            if new_size > MAX_FILE_BYTES:
                raise FileToolError("file_too_large", f"Replacement exceeds {MAX_FILE_BYTES} bytes")
            content = text.replace(old, new, -1 if replace_all else 1)
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_FILE_BYTES:
            raise FileToolError("file_too_large", f"Maximum file size is {MAX_FILE_BYTES} bytes")
        # Detect non-cooperating external writers before replacement as best effort.
        if data is not None:
            current = self.sandbox.read_complete(path, MAX_FILE_BYTES)
            if self.sandbox.file_version(path, current) != version:
                raise FileToolError("stale_version", "File changed during operation; read again")
        elif path.exists():
            raise FileToolError("stale_version", "File appeared during operation; read first")
        self.sandbox.atomic_write(path, encoded)
        new_version = self.sandbox.file_version(path, encoded)
        # Advance only this owner. Preserve incomplete coverage after partial-read
        # edits: knowing the replacement does not mean knowing unseen file content.
        complete = name == "write" or bool(observation and observation[2])
        self._observe(key, new_version, 0, len(content) if complete else 0, len(content))
        result = {"ok": True, "path": str(path), "size": len(encoded), "version": new_version,
                  "operation": "create" if data is None else name}
        if name == "edit":
            result["replacements"] = replacements
            if legacy_edit and observation is None:
                result["compatibility_note"] = "Legacy edit performed a complete locked read; use read_file first for stale-version protection."
        return result

    def _read_page(self, args, path, text, size, version, key):
        offset = _integer(args, "offset", 1, 1, MAX_FILE_BYTES + 1)
        limit = _integer(args, "limit", 2000, 1, 2000)
        column = _integer(args, "column", 0, 0, MAX_FILE_BYTES)
        lines = text.splitlines(keepends=True)
        if column and (offset > len(lines) or column > len(lines[offset - 1])):
            raise FileToolError("invalid_argument", "column exceeds line length")
        start = sum(map(len, lines[:offset - 1])) + column
        position = start
        remaining = MAX_TEXT_READ_BYTES
        output = []
        next_offset = next_column = None
        for index in range(offset - 1, min(len(lines), offset - 1 + limit)):
            begin = column if index == offset - 1 else 0
            segment = lines[index][begin:]
            chunk = segment.encode("utf-8")[:remaining].decode("utf-8", errors="ignore")
            if not chunk and segment:
                next_offset, next_column = index + 1, begin
                break
            output.append({"number": index + 1, "text": chunk, "column": begin})
            position += len(chunk)
            remaining -= len(chunk.encode("utf-8"))
            if len(chunk) < len(segment):
                next_offset, next_column = index + 1, begin + len(chunk)
                break
            if index + 1 < len(lines):
                next_offset, next_column = index + 2, 0
            else:
                next_offset = next_column = None
        self._observe(key, version, start, position, len(text))
        truncated = position < len(text)
        return {"ok": True, "path": str(path), "version": version, "size": size,
                "offset": offset, "column": column, "lines": output,
                "content": "".join(item["text"] for item in output), "totalLines": len(lines),
                "truncated": truncated, "next_offset": next_offset, "next_column": next_column,
                "complete_observation": self._observation(key)[2]}

    def _search(self, name: str, args: dict, base: Path, validate) -> dict:
        limit = _integer(args, "limit", 100 if name == "glob" else 250, 1, 100 if name == "glob" else 250)
        pattern = _string(args, "pattern")
        if not pattern or len(pattern) > 512:
            raise FileToolError("invalid_pattern", "pattern must have 1..512 characters")
        include = _pattern(pattern if name == "glob" else _string(args, "include", "*"))
        if not base.exists():
            raise FileNotFoundError(base)
        deadline = time.monotonic() + MAX_SEARCH_SECONDS
        stack = [base]
        candidates = []
        visited = 0
        reasons = set()
        while stack:
            current = stack.pop()
            if time.monotonic() > deadline or visited >= MAX_SCAN_ENTRIES or len(candidates) >= MAX_SCAN_FILES:
                reasons.add("scan_limit")
                break
            try:
                validate(current)
                if current.is_file():
                    relative = current.relative_to(base).as_posix() if current != base else current.name
                    if _matches(relative, include):
                        candidates.append((current.stat().st_mtime_ns, current, relative))
                elif current.is_dir():
                    with os.scandir(current) as entries:
                        for entry in entries:
                            visited += 1
                            if visited >= MAX_SCAN_ENTRIES or time.monotonic() > deadline:
                                reasons.add("scan_limit")
                                break
                            if entry.name in {".git", ".hg", ".svn"} or entry.name.startswith(".neobot-write-"):
                                continue
                            if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                                continue
                            stack.append(Path(entry.path))
            except (OSError, ValueError):
                reasons.add("skipped_unreadable")
        candidates.sort(key=lambda item: (-item[0], str(item[1])))
        if name == "glob":
            if len(candidates) > limit:
                reasons.add("result_limit")
            paths = [str(item[1]) for item in candidates[:limit]]
            return {"ok": True, "root": str(base), "paths": paths, "count": len(paths),
                    "truncated": bool(reasons), "truncation_reasons": sorted(reasons),
                    "scanned_entries": visited, "total_is_exact": not reasons}
        files, total_bytes = [], 0
        for _, path, _ in candidates:
            if time.monotonic() > deadline:
                reasons.add("scan_limit")
                break
            try:
                validate(path)
                with self.sandbox.file_lock(path):
                    data = self.sandbox.read_complete(path, min(MAX_FILE_BYTES, MAX_SEARCH_BYTES - total_bytes))
                total_bytes += len(data)
                text = data.decode("utf-8")
                if "\x00" not in text:
                    files.append((str(path), text))
            except UnicodeDecodeError:
                continue
            except ValueError:
                reasons.add("byte_limit")
            except OSError:
                reasons.add("skipped_unreadable")
        request = {"pattern": pattern, "ignore_case": bool(args.get("ignore_case", False)), "files": files, "limit": limit}
        try:
            process = subprocess.run([sys.executable, "-I", "-c", _REGEX_WORKER],
                                     input=json.dumps(request).encode("utf-8"), capture_output=True,
                                     timeout=REGEX_TIMEOUT_SECONDS, check=False)
        except subprocess.TimeoutExpired:
            raise FileToolError("search_timeout", "Regex worker exceeded hard time limit; simplify pattern") from None
        if process.returncode:
            raise FileToolError("search_failed", "Isolated regex worker failed")
        result = json.loads(process.stdout)
        if "error" in result:
            raise FileToolError("invalid_pattern", result["error"])
        if result["truncated"]:
            reasons.add("result_limit")
        return {"ok": True, "root": str(base), "matches": result["matches"],
                "truncated": bool(reasons), "truncation_reasons": sorted(reasons),
                "files_searched": len(files), "bytes_searched": total_bytes,
                "total_is_exact": not reasons, "backend": "isolated_python_regex"}

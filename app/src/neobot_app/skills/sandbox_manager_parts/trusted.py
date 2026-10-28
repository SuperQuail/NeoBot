"""可信调用（CURRENT_INVOCATION）下的参数界定与执行。"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .common import _json, display_result_path
from .dispatch import _HANDLERS

class TrustedMixin:

    async def _execute_trusted(self, name: str, args: dict, context: Any) -> str:
        """Production model entry. Never mint authority from tool arguments.

        This is separate from the historical handlers so host-only integrations
        retain their old contract without weakening flow-bound model calls.
        """
        from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
        from neobot_app.runtime.agent_file_tools import MAX_FILE_BYTES
        try:
            if not isinstance(context, ToolContext):
                raise AgentToolError("CONTEXT_REQUIRED", "Trusted ToolContext required")
            # Reply has already checked the qualified legacy skill capability.
            # allowed_tools contains NEW runtime names, not legacy skill names.
            if self._file_tools is None or self._sandbox is None:
                raise AgentToolError("SANDBOX_REQUIRED", "sandbox_service 未配置")
            if not isinstance(args, dict):
                raise AgentToolError("INVALID_ARGS", "Tool arguments must be an object")
            for key in ("chat_flow_id", "pipeline_key"):
                if args.get(key) not in (None, "", context.chat_flow_id):
                    raise AgentToolError("FLOW_MISMATCH", "Tool arguments cannot change the trusted chat flow")
            if any(key in args for key in ("owner", "context", "invocation")):
                raise AgentToolError("CONTEXT_REQUIRED", "Identity/context fields are host-only")
            clean = {key: value for key, value in args.items() if key not in {"chat_flow_id", "pipeline_key"}}
            bound = {**clean, "chat_flow_id": context.chat_flow_id}

            def resolve(value, *, write=False):
                if not isinstance(value, str) or not value:
                    raise AgentToolError("INVALID_ARGS", "A nonempty string path is required")
                return self._file_tools.resolve_path(value, owner=context.owner,
                                                     chat_flow_id=context.chat_flow_id, write=write)

            def shared(value):
                return isinstance(value, str) and value.startswith("shared:")

            async def execute_file(operation, values):
                return await self._file_tools.execute(operation, values, owner=context.owner,
                                                      chat_flow_id=context.chat_flow_id)

            mapping = {"read_file": "read", "write_file": "write", "edit_file": "edit",
                       "glob_files": "glob", "grep_files": "grep"}
            if name in mapping:
                operation = mapping[name]
                raw = clean.get("file_path", clean.get("path", "." if operation in {"glob", "grep"} else None))
                path = resolve(raw, write=operation in {"write", "edit"})
                if operation in {"write", "edit"} and shared(raw):
                    await self._permissions.authorize(
                        context, "agent_shared_write", tool_name=name, arguments=clean
                    )
                values = dict(clean)
                if operation in {"glob", "grep"}:
                    values.pop("file_path", None)
                    values["path"] = raw
                else:
                    values.pop("path", None)
                    values["file_path"] = raw
                if operation == "grep":
                    values["include"] = values.pop("glob", None) or "*"
                    values["ignore_case"] = values.pop("-i", False)
                    values["limit"] = values.pop("head_limit", 50)
                    mode = values.pop("output_mode", "files_with_matches")
                    if mode not in {"content", "count", "files_with_matches"}:
                        raise AgentToolError("INVALID_ARGS", "Invalid output_mode")
                if operation == "read":
                    from neobot_app.runtime.sandbox_service import detect_file_type, MAX_BASE64_BYTES
                    info = detect_file_type(path)
                    if info["type"] in {"image", "binary"}:
                        return _json({"ok": True, **info,
                                      "note": "图片分析请使用 image_parse；发送请用 send_file/send_chat_file。"})
                result = await execute_file(operation, values)
                if operation == "read" and result.get("code") == "not_utf8":
                    with path.open("rb") as stream:
                        preview = stream.read(MAX_BASE64_BYTES)
                    return _json({"ok": True, "type": "unknown_binary", "size": path.stat().st_size,
                                  "content_base64": base64.b64encode(preview).decode(),
                                  "truncated": path.stat().st_size > len(preview),
                                  "note": "只读二进制预览；不可把预览作为完整文件覆盖。"})
                if result.get("ok") and operation in {"glob", "grep"}:
                    base = Path(result["root"])
                    root = self._sandbox.root
                    def relative(value):
                        return display_result_path(value, base, root)
                    if operation == "glob":
                        result["matches"] = [{"path": relative(p), "is_dir": False} for p in result["paths"]]
                    elif mode == "content":
                        result["results"] = [{"file": relative(m["path"]), "line": m["lineNumber"], "text": m["line"]}
                                             for m in result["matches"]]
                    else:
                        counts = {}
                        for match in result["matches"]:
                            key = relative(match["path"])
                            counts[key] = counts.get(key, 0) + 1
                        result["results"] = [{"file": key, "count" if mode == "count" else "match_count": count}
                                             for key, count in counts.items()]
                    if operation == "grep":
                        result["total_matches"] = len(result["matches"])
                return _json(result)

            if name in {"move_file", "copy_file"}:
                source, destination = clean.get("source"), clean.get("destination")
                src = resolve(source, write=name == "move_file")
                dst = resolve(destination, write=True)
                # Service move/copy may append the basename for a directory target.
                if dst.is_dir():
                    resolve(destination.rstrip("/\\") + "/" + src.name, write=True)
                if shared(destination) or (name == "move_file" and shared(source)):
                    await self._permissions.authorize(
                        context, "agent_shared_write", tool_name=name, arguments=clean
                    )
                operation = self._sandbox.move_file if name == "move_file" else self._sandbox.copy_file
                await operation(src, dst)
                return _json({"ok": True})

            if name == "list_files":
                raw = clean.get("path") or "."
                base = resolve(raw)
                if clean.get("pattern"):
                    result = await execute_file("glob", {"path": raw, "pattern": clean["pattern"]})
                    if result.get("ok"):
                        result["files"] = [{"name": Path(p).name, "path": p, "is_dir": False} for p in result["paths"]]
                    return _json(result)
                if not base.is_dir():
                    raise NotADirectoryError(base)
                import os
                files, truncated = [], False
                with os.scandir(base) as entries:
                    for count, entry in enumerate(entries):
                        if count >= 2000:
                            truncated = True
                            break
                        try:
                            path = resolve(raw.rstrip("/\\") + "/" + entry.name)
                        except PermissionError:
                            continue
                        stat = path.stat()
                        files.append({"name": path.name, "path": str(path), "is_dir": path.is_dir(),
                                      "size": stat.st_size if path.is_file() else 0, "mtime": stat.st_mtime})
                return _json({"ok": True, "files": files, "truncated": truncated})

            if name == "hold_temp":
                resolve(".", write=True)
                return await _HANDLERS[name](self, bound)

            raw = clean.get("save_name") if name == "download_file" else clean.get("path")
            writing = name in {"delete_file", "write_file_base64", "download_file"}
            path = resolve(raw, write=writing)
            if name == "delete_file":
                if shared(raw):
                    await self._permissions.authorize(
                        context, "agent_shared_write", tool_name=name, arguments=clean
                    )
                await self._sandbox.delete_file(path)
                return _json({"ok": True})
            if name == "write_file_base64":
                value = clean.get("content_base64")
                if not isinstance(value, str) or len(value) > 4 * ((MAX_FILE_BYTES + 2) // 3):
                    raise AgentToolError("INVALID_ARGS", "Invalid or oversized base64 content")
                data = base64.b64decode(value, validate=True)
                if len(data) > MAX_FILE_BYTES:
                    raise AgentToolError("FILE_TOO_LARGE", "Binary write exceeds file limit")
                with self._sandbox.file_lock(path):
                    resolve(raw, write=True)
                    if shared(raw):
                        await self._permissions.authorize(
                            context, "agent_shared_write", tool_name=name, arguments=clean
                        )
                    elif path.exists():
                        await self._permissions.authorize(
                            context, "agent_execute", tool_name=name, arguments=clean
                        )
                    self._sandbox.atomic_write(path, data)
                return _json({"ok": True, "path": str(path), "size": len(data)})
            if name == "download_file":
                if shared(raw):
                    await self._permissions.authorize(
                        context, "agent_shared_write", tool_name=name, arguments=clean
                    )
                bound["save_name"] = str(path)
                return await _HANDLERS[name](self, bound)
            if name in {"send_file", "send_chat_file"}:
                kind, recipient = context.chat_flow_id.split(":", 1)
                for key, expected in (("group_id", recipient if kind == "group" else ""),
                                      ("user_id", recipient if kind == "private" else "")):
                    if str(clean.get(key) or "") not in {"", expected}:
                        raise AgentToolError("FLOW_MISMATCH", "File delivery recipient must be the trusted flow")
                    bound[key] = expected
                # Preserve explicit shared syntax: strict _resolve_send_path checks again.
                bound["path"] = raw
                return await _HANDLERS[name](self, bound)
            raise AgentToolError("UNKNOWN_TOOL", name)
        except AgentToolError as exc:
            return _json({"ok": False, "code": exc.code, "error": str(exc), "details": exc.details})
        except PermissionError as exc:
            return _json({"ok": False, "code": "permission_denied", "error": str(exc)})
        except (OSError, ValueError, TypeError) as exc:
            # 只回传 str(exc) 时，像 FileNotFoundError 这类异常可能只剩一个路径；
            # 带上异常类型并给出下一步建议，模型才能自愈而不是反复换参数重试。
            return _json({
                "ok": False,
                "code": "file_error",
                "error": f"{type(exc).__name__}: {exc}",
                "hint": "确认路径存在且在允许目录内；目录不存在时先列上级目录，不要重复相同调用。",
            })

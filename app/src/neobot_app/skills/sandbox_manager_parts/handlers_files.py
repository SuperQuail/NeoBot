"""读写/编辑/搜索/删除/列表/移动/复制的处理函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import base64
from pathlib import Path

from .common import _json, display_result_path

if TYPE_CHECKING:
    from ..sandbox_manager_skill import SandboxManagerSkill

# ── Handlers ──

async def _handle_read_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/")
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        from neobot_app.runtime.sandbox_service import (
            MAX_BASE64_BYTES,
            detect_file_type,
        )

        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_read_path(rel_path, chat_flow_id)

        info = detect_file_type(path)
        ftype = info["type"]
        fmt = info.get("format")
        size = info["size"]

        if ftype == "error":
            return _json({"ok": False, "error": f"无法读取文件: {rel_path}"})

        if ftype == "image":
            return _json({
                "ok": True,
                "type": "image",
                "format": fmt,
                "size": size,
                "note": (
                    f"这是 {fmt} 图片文件（{size} 字节），内容不会直接以文本/base64 返回。"
                    "请使用 image_parse 工具分析图片内容；发送图片请使用 send_file。"
                ),
            })

        if ftype == "binary":
            return _json({
                "ok": True,
                "type": "binary",
                "format": fmt,
                "size": size,
                "note": (
                    f"这是 {fmt} 二进制文件（{size} 字节），无法以文本读取。"
                    "发送此文件请使用 send_chat_file；分析内容请委托 background_trigger__submit_problem。"
                ),
            })

        # UTF-8 is decoded from the COMPLETE bounded file, then paginated.
        # This correctly handles a multibyte character straddling the old 64KiB cut.
        result = await self._file_tools.execute_legacy(
            "read", {**args, "file_path": rel_path}, owner=self._file_owner, chat_flow_id=chat_flow_id)
        if result.get("ok"):
            return _json(result)
        # Unknown binary is only a preview; never register it as a complete read.
        with path.open("rb") as stream:
            preview = stream.read(MAX_BASE64_BYTES)
        try:
            preview.decode("utf-8")
        except UnicodeDecodeError:
            return _json({"ok": True, "type": "unknown_binary",
                          "content_base64": base64.b64encode(preview).decode(),
                          "size": size, "truncated": size > len(preview),
                          "note": "二进制预览；发送文件请使用 send_chat_file。"})
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_write_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    flow = self._get_chat_flow_id(args)
    if not args.get("path") or not flow or "content" not in args:
        return _json({"ok": False, "error": "缺少必要参数 path/content/chat_flow_id"})
    return _json(await self._file_tools.execute_legacy(
        "write", args, owner=self._file_owner, chat_flow_id=flow))


async def _handle_write_file_base64(self: SandboxManagerSkill, args: dict) -> str:
    """二进制内容通过 base64 写入。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    content_b64 = str(args.get("content_base64", "")).strip()
    chat_flow_id = self._get_chat_flow_id(args)
    if not rel_path or not content_b64 or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 path/content_base64/chat_flow_id"})
    try:
        data = base64.b64decode(content_b64)
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_edit_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    return _json(await self._file_tools.execute_legacy(
        "edit", args, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None))


async def _handle_glob_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    result = await self._file_tools.execute_legacy(
        "glob", args, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None)
    if result.get("ok"):
        base = Path(result["root"])
        root = self._sandbox.root
        result["matches"] = [
            {"path": display_result_path(p, base, root), "is_dir": False} for p in result["paths"]
        ]
    return _json(result)


async def _handle_grep_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    mode = args.get("output_mode", "files_with_matches")
    if mode not in {"content", "files_with_matches", "count"}:
        return _json({"ok": False, "error": "invalid output_mode"})
    translated = {**args, "include": args.get("glob") or "*",
                  "ignore_case": args.get("-i", False), "limit": args.get("head_limit", 50)}
    result = await self._file_tools.execute_legacy(
        "grep", translated, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None)
    if result.get("ok"):
        base = Path(result["root"])
        root = self._sandbox.root
        def relative(p):
            return display_result_path(p, base, root)
        if mode == "content":
            result["results"] = [{"file": relative(m["path"]), "line": m["lineNumber"], "text": m["line"]}
                                 for m in result["matches"]]
        else:
            counts: dict[str, int] = {}
            for match in result["matches"]:
                p = relative(match["path"])
                counts[p] = counts.get(p, 0) + 1
            result["results"] = [{"file": p, "count" if mode == "count" else "match_count": count}
                                 for p, count in counts.items()]
        result["total_matches"] = len(result["matches"])
        # Counts explicitly describe the bounded matched prefix when truncated.
    return _json(result)


async def _handle_delete_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        path = self._sandbox.resolve_path(rel_path, chat_flow_id or None)
        await self._sandbox.delete_file(path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_list_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/") or "."
    pattern = args.get("pattern")
    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_read_path(rel_path, chat_flow_id)
        files = await self._sandbox.list_files(path, pattern)
        return _json({"ok": True, "files": files})
    except (FileNotFoundError, NotADirectoryError):
        # 旧实现只回传 str(exc)，最坏情况下 error 里只有一个路径，模型无法据此
        # 判断该换参数还是换工具，只能反复猜（随后改去试别的工具）。
        return _json({
            "ok": False,
            "code": "not_found",
            "error": f"目录不存在或不是目录: {rel_path}",
            "hint": "先用 path=\".\" 列出当前目录确认可用路径；不要重复同样的参数。",
        })
    except PermissionError as e:
        return _json({
            "ok": False,
            "code": "permission_denied",
            "error": str(e),
            "hint": "该路径不在允许范围内：改用当前会话目录，或在允许时使用 shared: 前缀。",
        })
    except Exception as e:
        return _json({
            "ok": False,
            "code": "file_error",
            "error": f"{type(e).__name__}: {e}",
            "hint": "检查路径拼写与后缀；若仍失败请换一个路径或改用其它工具。",
        })


async def _handle_move_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.move_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_copy_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_read_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.copy_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

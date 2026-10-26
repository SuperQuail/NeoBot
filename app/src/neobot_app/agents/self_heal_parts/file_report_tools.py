"""沙箱文件读写与调试报告工具。"""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4



from .models import (
    _json,
)


class SelfHealToolFileReportMixin:
    """沙箱文件读写与调试报告工具。"""

    def _debug_report_dir(self) -> Path | None:
        if self._sandbox is None:
            return None
        return self._sandbox.resolve_path(self._sandbox_debug_dir)

    async def _execute_write_debug_report(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        content_b64 = str(args.get("content_base64", "")).strip()
        if not content_b64:
            return _json({"ok": False, "error": "缺少 content_base64"})
        try:
            data = base64.b64decode(content_b64)
        except Exception as exc:
            return _json({"ok": False, "error": f"base64 解码失败: {exc}"})
        rel_dir = self._sandbox_debug_dir
        # Ensure dir exists under sandbox
        dir_path = self._sandbox.resolve_path(rel_dir)
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _json({"ok": False, "error": f"创建 debug 目录失败: {exc}"})

        file_name = str(args.get("file_name", "")).strip()
        safe_suffix = ".md"
        if not file_name:
            from neobot_app.time_context import get_current_time_and_lunar_date

            ts = (
                get_current_time_and_lunar_date()
                .replace(" ", "_")
                .replace(":", "")
                .replace("/", "")
            )
            # ts may include lunar info; use a simple timestamp instead
            import datetime as _dt

            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"report_{ts}{safe_suffix}"
        else:
            # Sanitize
            cleaned = Path(file_name).name
            if not cleaned:
                file_name = f"report_{uuid4().hex[:8]}{safe_suffix}"
            else:
                file_name = cleaned
        rel_path = f"{rel_dir}/{file_name}"
        path = self._sandbox.resolve_path(rel_path)
        try:
            await self._sandbox.write_file(path, data)
        except Exception as exc:
            return _json({"ok": False, "error": f"写入报告失败: {exc}"})
        return _json({"ok": True, "debug_file": rel_path, "absolute_path": str(path)})

    async def _execute_list_debug_reports(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        try:
            dir_path = self._sandbox.resolve_path(self._sandbox_debug_dir)
            if not dir_path.exists():
                return _json({"ok": True, "files": []})
            files = await self._sandbox.list_files(dir_path)
            return _json({"ok": True, "dir": self._sandbox_debug_dir, "files": files})
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})

    async def _execute_read_debug_report(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        file_name = str(args.get("file_name", "")).strip()
        if not file_name:
            return _json({"ok": False, "error": "缺少 file_name"})
        rel = f"{self._sandbox_debug_dir}/{Path(file_name).name}"
        try:
            path = self._sandbox.resolve_path(rel)
            data = await self._sandbox.read_file(path)
            try:
                text = data.decode("utf-8")
                return _json({"ok": True, "file": rel, "content": text})
            except UnicodeDecodeError:
                return _json(
                    {
                        "ok": True,
                        "file": rel,
                        "content_base64": base64.b64encode(data).decode("utf-8"),
                    }
                )
        except Exception as exc:
            return _json({"ok": False, "error": str(exc)})

    # ── sandbox generic ──

    async def _execute_list_files(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        rel = str(args.get("path", "")).strip().lstrip("/") or "."
        try:
            path = self._sandbox.resolve_path(rel)
            files = await self._sandbox.list_files(path)
            return _json({"ok": True, "files": files})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _execute_read_file(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        rel = str(args.get("path", "")).strip().lstrip("/")
        if not rel:
            return _json({"ok": False, "error": "缺少 path"})
        try:
            from neobot_app.runtime.sandbox_service import (
                MAX_BASE64_BYTES,
                MAX_TEXT_READ_BYTES,
                detect_file_type,
            )

            path = self._sandbox.resolve_read_path(rel)
            info = detect_file_type(path)
            ftype = info["type"]
            fmt = info.get("format")
            size = info["size"]
            if ftype == "error":
                return _json({"ok": False, "error": f"无法读取: {rel}"})
            if ftype == "empty":
                return _json({"ok": True, "content_base64": "", "size": 0})
            if ftype == "image":
                return _json(
                    {
                        "ok": True,
                        "type": "image",
                        "format": fmt,
                        "size": size,
                        "note": "图片文件，请使用 parse_image 工具读取内容",
                    }
                )
            if ftype == "binary":
                return _json(
                    {
                        "ok": True,
                        "type": "binary",
                        "format": fmt,
                        "size": size,
                        "note": "二进制文件，请通过 send_chat_file 发送或使用 parse_image",
                    }
                )
            data = await self._sandbox.read_file(path)
            try:
                text = data.decode("utf-8")
                if len(data) > MAX_TEXT_READ_BYTES:
                    return _json(
                        {
                            "ok": True,
                            "content": text[:MAX_TEXT_READ_BYTES],
                            "size": len(data),
                            "truncated": True,
                        }
                    )
                return _json({"ok": True, "content": text, "size": len(data)})
            except UnicodeDecodeError:
                preview_size = min(len(data), MAX_BASE64_BYTES)
                return _json(
                    {
                        "ok": True,
                        "type": "unknown_binary",
                        "content_base64": base64.b64encode(
                            data[:preview_size]
                        ).decode(),
                        "size": len(data),
                        "truncated": len(data) > MAX_BASE64_BYTES,
                    }
                )
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

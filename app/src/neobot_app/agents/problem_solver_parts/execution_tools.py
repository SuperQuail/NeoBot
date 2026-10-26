"""run_python / parse_image / 文件读写工具。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path



from .models import (
    _json,
)


class ProblemSolverToolExecutionMixin:
    """run_python / parse_image / 文件读写工具。"""

    async def _execute_run_python(self, args: dict) -> str:
        code = str(args.get("code", "")).strip()
        if not code:
            return "错误：code 不能为空"
        timeout = min(int(args.get("timeout", 30)), 120)
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", encoding="utf-8", delete=False
            ) as f:
                f.write(code)
                script_path = f.name
            cwd = str(self._get_sandbox_work_dir()) if self._sandbox else None
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [sys.executable, script_path],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=timeout,
                        cwd=cwd,
                    ),
                ),
                timeout=timeout + 5,
            )
            Path(script_path).unlink(missing_ok=True)
            output = result.stdout.strip()
            error = result.stderr.strip()
            # 如果超时被 subprocess 自己捕获
            if result.returncode != 0:
                return _json(
                    {
                        "ok": True,
                        "stdout": output,
                        "stderr": error,
                        "returncode": result.returncode,
                        "note": "进程退出码非零，请检查 stderr",
                    }
                )
            return _json(
                {
                    "ok": True,
                    "stdout": output,
                    "stderr": error or None,
                    "returncode": 0,
                }
            )
        except subprocess.TimeoutExpired:
            Path(script_path).unlink(missing_ok=True)
            return _json({"ok": False, "error": f"Python 执行超时（{timeout}秒）"})
        except Exception as e:
            Path(script_path).unlink(missing_ok=True)
            return _json({"ok": False, "error": str(e)})

    async def _execute_parse_image(self, args: dict) -> str:
        if self._vision_provider is None:
            self._logger.warning("视觉模型未配置，跳过图片解析（仅记录日志）")
            return _json({"ok": True, "skipped": True, "note": ""})
        from neobot_app.runtime.sandbox_service import detect_file_type

        image_path = str(args.get("image_path", "")).strip()
        if not image_path:
            return _json({"ok": False, "error": "缺少 image_path"})

        requirement = str(
            args.get("requirement") or "请简洁描述这张图片的主要内容。"
        ).strip()
        chat_flow_id = str(args.get("chat_flow_id", "")).strip() or None

        try:
            if self._sandbox is not None:
                path = self._sandbox.resolve_read_path(image_path, chat_flow_id)
            else:
                path = Path(image_path)

            info = detect_file_type(path)
            if info["type"] != "image":
                return _json(
                    {
                        "ok": False,
                        "error": f"文件不是图片（检测为 {info['type']}"
                        + (f"/{info['format']}" if info.get("format") else "")
                        + "），请确认路径正确",
                    }
                )

            import base64

            data = path.read_bytes()
            content_parts = [
                {"type": "text", "text": requirement},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": f"image/{info['format'].lower()}"
                        if info.get("format")
                        else "image/png",
                        "data": base64.b64encode(data).decode("utf-8"),
                    },
                },
            ]
            result = await self._vision_provider.chat(
                [{"role": "user", "content": content_parts}]
            )
            text = (
                result.get("content", "") if isinstance(result, dict) else str(result)
            )
            return _json({"ok": True, "description": text[:2000]})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _execute_write_file(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        import base64

        rel_path = str(args.get("path", "")).strip()
        content_b64 = args.get("content_base64", "")
        if not rel_path or not content_b64:
            return _json({"ok": False, "error": "缺少 path 或 content_base64"})
        try:
            data = base64.b64decode(content_b64)
            chat_flow_id = self._parse_chat_flow_id()
            path = self._sandbox.resolve_path(rel_path, chat_flow_id)
            await self._sandbox.write_file(path, data)
            return _json({"ok": True, "path": str(path)})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _execute_read_file(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        import base64
        from neobot_app.runtime.sandbox_service import (
            MAX_BASE64_BYTES,
            MAX_TEXT_READ_BYTES,
            detect_file_type,
        )

        rel_path = str(args.get("path", "")).strip().lstrip("/")
        if not rel_path:
            return _json({"ok": False, "error": "缺少 path"})
        try:
            chat_flow_id = self._parse_chat_flow_id()
            path = self._sandbox.resolve_read_path(rel_path, chat_flow_id)

            info = detect_file_type(path)
            ftype = info["type"]
            fmt = info.get("format")
            size = info["size"]

            if ftype == "error":
                return _json({"ok": False, "error": f"无法读取文件: {rel_path}"})
            if ftype == "empty":
                return _json({"ok": True, "content_base64": "", "size": 0})

            if ftype == "image":
                return _json(
                    {
                        "ok": True,
                        "type": "image",
                        "format": fmt,
                        "size": size,
                        "note": (
                            f"这是 {fmt} 图片文件（{size} 字节），内容不会以文本/base64 返回。"
                            "请使用 parse_image 工具分析图片内容。"
                        ),
                    }
                )

            if ftype == "binary":
                return _json(
                    {
                        "ok": True,
                        "type": "binary",
                        "format": fmt,
                        "size": size,
                        "note": (
                            f"这是 {fmt} 二进制文件（{size} 字节），无法以文本读取。"
                            "请在解题结果中引用此文件路径，由主 Agent 通过 send_chat_file 发送。"
                        ),
                    }
                )

            # 文本或未知类型 → 读取内容
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
                            "note": (
                                f"[PARTIAL view] 文本过大（{len(data)} 字节），"
                                f"仅返回前 {MAX_TEXT_READ_BYTES} 字节。"
                            ),
                        }
                    )
                return _json({"ok": True, "content": text, "size": len(data)})
            except UnicodeDecodeError:
                preview_size = min(len(data), MAX_BASE64_BYTES)
                truncated = len(data) > MAX_BASE64_BYTES
                return _json(
                    {
                        "ok": True,
                        "type": "unknown_binary",
                        "content_base64": base64.b64encode(
                            data[:preview_size]
                        ).decode(),
                        "size": len(data),
                        "truncated": truncated,
                        "note": (
                            f"未知二进制格式（{len(data)} 字节）"
                            + (
                                f"，仅返回前 {MAX_BASE64_BYTES} 字节预览。"
                                if truncated
                                else "。"
                            )
                        ),
                    }
                )
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _execute_list_files(self, args: dict) -> str:
        if self._sandbox is None:
            return _json({"ok": False, "error": "sandbox 未配置"})
        rel_path = str(args.get("path", "")).strip().lstrip("/") or "."
        try:
            chat_flow_id = self._parse_chat_flow_id()
            path = self._sandbox.resolve_path(rel_path, chat_flow_id)
            files = await self._sandbox.list_files(path)
            return _json({"ok": True, "files": files})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

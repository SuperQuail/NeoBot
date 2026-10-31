"""run_python / parse_image 与修复钩子、结论提交。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path



from .models import (
    _HEAL_TASK,
    _json,
)


class SelfHealToolSandboxMixin:
    """run_python / parse_image 与修复钩子、结论提交。"""

    def _get_sandbox_work_dir(self) -> Path | None:
        if self._sandbox is None:
            return None
        return self._sandbox.resolve_path(".")

    async def _execute_run_python(self, args: dict) -> str:
        code = str(args.get("code", "")).strip()
        if not code:
            return _json({"ok": False, "error": "code 不能为空"})
        timeout = min(int(args.get("timeout", 30)), 60)
        script_path: str | None = None
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
                        timeout=timeout,
                        cwd=cwd,
                    ),
                ),
                timeout=timeout + 5,
            )
            output = result.stdout.decode("utf-8", errors="replace").strip()
            error = result.stderr.decode("utf-8", errors="replace").strip()
            return _json(
                {
                    "ok": True,
                    "stdout": output,
                    "stderr": error or None,
                    "returncode": result.returncode,
                }
            )
        except subprocess.TimeoutExpired:
            return _json({"ok": False, "error": f"Python 执行超时（{timeout}秒）"})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})
        finally:
            if script_path is not None:
                Path(script_path).unlink(missing_ok=True)

    async def _execute_parse_image(self, args: dict) -> str:
        if self._vision_provider is None:
            return _json({"ok": True, "skipped": True, "note": ""})
        from neobot_app.runtime.sandbox_service import detect_file_type

        image_path = str(args.get("image_path", "")).strip()
        if not image_path:
            return _json({"ok": False, "error": "缺少 image_path"})
        requirement = str(
            args.get("requirement") or "请简洁描述这张图片的主要内容。"
        ).strip()
        try:
            if self._sandbox is not None:
                path = self._sandbox.resolve_read_path(image_path)
            else:
                path = Path(image_path)
            info = detect_file_type(path)
            if info["type"] != "image":
                return _json(
                    {
                        "ok": False,
                        "error": f"文件不是图片（检测为 {info['type']}）",
                    }
                )
            data = path.read_bytes()
            from neobot_app.image.parser import _build_vision_image_part

            part = _build_vision_image_part(data, logger=self._logger)
            content_parts = [
                {"type": "text", "text": requirement},
                part,
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

    # ── repair hooks ──

    async def _execute_repair_hook(self, hook_name: str, args: dict) -> str:
        hook = self._repair_hooks.get(hook_name)
        if hook is None:
            return _json({"ok": False, "error": f"修复钩子 {hook_name} 未配置"})
        try:
            result = hook(args)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, dict):
                return _json(result)
            return _json({"ok": True, "result": str(result)})
        except Exception as exc:
            return _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # ── submit resolution ──

    async def _execute_submit_resolution(self, args: dict) -> str:
        summary = str(args.get("summary", "")).strip()
        if not summary:
            return "错误：summary 不能为空"
        task = _HEAL_TASK.get(None)
        if task is None:
            return "错误：无活跃自修复任务上下文"
        task.summary = summary
        task.root_cause = str(args.get("root_cause", "")).strip() or None
        task.debug_file = str(args.get("debug_file", "")).strip() or None
        repaired_raw = args.get("repaired", False)
        try:
            task.repaired = bool(repaired_raw)
        except Exception:
            task.repaired = False
        task.status = "completed"
        return "已记录诊断结论。系统将自动通过通知系统向管理员私聊推送最终通知。"

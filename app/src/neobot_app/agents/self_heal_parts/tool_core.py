"""执行器生命周期、工具分发与错误/日志读取。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.web_search_package import WebSearchExecutor

from .models import (
    _HEAL_TASK,
    _json,
)


class SelfHealToolCoreMixin:
    """执行器生命周期、工具分发与错误/日志读取。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
        sandbox_service: Any = None,
        source_roots: list[Path] | None = None,
        log_file: Path | None = None,
        sandbox_debug_dir: str = "debug/self_heal",
        repair_hooks: dict[str, Any] | None = None,
        web_search_config: dict | None = None,
        vision_provider: Any = None,
    ) -> None:
        self._logger = logger or NullLogger()
        self._sandbox = sandbox_service
        self._source_roots = source_roots or []
        self._log_file = log_file
        self._sandbox_debug_dir = (
            str(sandbox_debug_dir).strip().lstrip("/") or "debug/self_heal"
        )
        self._repair_hooks = repair_hooks or {}
        self._vision_provider = vision_provider
        ws = web_search_config or {}
        self._search = WebSearchExecutor(
            engines=ws.get("engines"),
            max_rounds=ws.get("max_rounds", 5),
            preview_pages_limit=ws.get("preview_pages_limit", 30),
            variant_result_limit=ws.get("variant_result_limit", 6),
            deepseek_enabled=ws.get("deepseek_enabled"),
            deepseek_api_key=ws.get("deepseek_api_key", ""),
            deepseek_base_url=ws.get("deepseek_base_url", ""),
            deepseek_timeout_seconds=ws.get("deepseek_timeout_seconds", 20.0),
            deepseek_quota_cooldown_seconds=ws.get("deepseek_quota_cooldown_seconds", 3600.0),
        )

    def reset_search(self) -> None:
        self._search.reset()

    async def close(self) -> None:
        """释放执行器资源。"""

    async def execute(self, name: str, args: dict) -> str:
        if name == "read_errors":
            return await self._execute_read_errors(args)
        if name == "read_log_tail":
            return await self._execute_read_log_tail(args)
        if name == "read_source_code":
            return await self._execute_read_source_code(args)
        if name == "search_source_code":
            return await self._execute_search_source_code(args)
        if name == "write_debug_report":
            return await self._execute_write_debug_report(args)
        if name == "list_debug_reports":
            return await self._execute_list_debug_reports(args)
        if name == "read_debug_report":
            return await self._execute_read_debug_report(args)
        if name == "search_web":
            return await self._search.execute("search", args)
        if name == "read_search_result":
            return await self._search.execute("read", args)
        if name == "search_status":
            return await self._search.execute("status", args)
        if name == "list_files":
            return await self._execute_list_files(args)
        if name == "read_file":
            return await self._execute_read_file(args)
        if name == "run_python":
            return await self._execute_run_python(args)
        if name == "parse_image":
            return await self._execute_parse_image(args)
        if name == "clear_drawing_cooldown":
            return await self._execute_repair_hook("clear_drawing_cooldown", args)
        if name == "trigger_image_cleanup":
            return await self._execute_repair_hook("trigger_image_cleanup", args)
        if name == "submit_resolution":
            return await self._execute_submit_resolution(args)
        return f"未知工具: {name}"

    # ── error snapshot ──

    async def _execute_read_errors(self, args: dict) -> str:
        task = _HEAL_TASK.get(None)
        if task is None:
            return _json({"ok": False, "error": "无活跃自修复任务上下文"})
        return _json(
            {
                "ok": True,
                "task_id": task.task_id,
                "trigger_reason": task.trigger_reason,
                "first_error_time": task.first_error_time,
                "last_error_time": task.last_error_time,
                "error_count": len(task.error_snapshot),
                "errors": task.error_snapshot,
            }
        )

    # ── log tail ──

    async def _execute_read_log_tail(self, args: dict) -> str:
        log_path = self._log_file
        if log_path is None or not log_path.exists():
            return _json({"ok": False, "error": "未配置或不存在日志文件"})
        try:
            lines = int(args.get("lines", self.DEFAULT_LOG_TAIL_LINES))
        except (TypeError, ValueError):
            lines = self.DEFAULT_LOG_TAIL_LINES
        lines = max(1, min(lines, self.MAX_LOG_TAIL_LINES))
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
        except OSError as exc:
            return _json({"ok": False, "error": f"读取日志失败: {exc}"})
        tail = all_lines[-lines:]
        text = "".join(tail)
        return _json({"ok": True, "lines_returned": len(tail), "log": text})

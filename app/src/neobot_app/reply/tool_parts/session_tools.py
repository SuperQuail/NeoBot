"""会话工具提交、排队与取消（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from neobot_app.time_context import monotonic_seconds

from neobot_app.reply.tool_parts.common import _SESSION_ERROR_KEYS, _SESSION_FAILURE_PREFIXES, _bounded_text


class _SessionToolsMixin:
    async def _execute_session_tool(
        self, name: str, args: dict, token: Any = None
    ) -> str:
        """将会话工具提交到后台执行（同一管线最多 1 运行 + 1 排队）。"""
        if self._closed:
            return json.dumps(
                {
                    "ok": False,
                    "status": "closed",
                    "tool": name,
                    "message": "回复执行器已关闭，拒绝提交新的会话工具。",
                },
                ensure_ascii=False,
            )
        pipeline_key = str(args.get("pipeline_key", "") or "")
        if not pipeline_key:
            return json.dumps(
                {
                    "ok": False,
                    "status": "missing_pipeline",
                    "tool": name,
                    "message": "无法确定当前会话，会话工具已拒绝执行。",
                },
                ensure_ascii=False,
            )
        conv_kind = self._conv_kind
        conv_id = self._conv_id

        has_running = any(
            info["pipeline_key"] == pipeline_key
            for info in self._session_task_info.values()
        )

        if has_running:
            if pipeline_key in self._session_task_queue:
                return json.dumps(
                    {
                        "ok": False,
                        "status": "queue_full",
                        "tool": name,
                        "message": (
                            "当前已有会话工具正在执行且已有排队任务（最多排队1个）。"
                            "请等待当前任务完成后重试，或调用 cancel_task 取消当前任务/排队。"
                        ),
                    },
                    ensure_ascii=False,
                )
            self._session_task_queue[pipeline_key] = {
                "name": name,
                "args": args,
                "token": token,
                "conv_kind": conv_kind,
                "conv_id": conv_id,
                "queued_at": monotonic_seconds(),
            }
            self._logger.info(
                "会话工具已加入排队",
                tool=name,
                pipeline_key=pipeline_key,
            )
            return json.dumps(
                {
                    "ok": True,
                    "status": "queued",
                    "tool": name,
                    "message": (
                        "已有会话工具正在执行，当前任务已加入排队。"
                        "系统会在当前任务完成后自动执行排队的任务。请立即结束本轮回复。"
                    ),
                },
                ensure_ascii=False,
            )

        return self._start_session_tool(
            name, args, pipeline_key, conv_kind, conv_id, token
        )

    def _start_session_tool(
        self,
        name: str,
        args: dict,
        pipeline_key: str,
        conv_kind: str,
        conv_id: str,
        token: Any = None,
    ) -> str:
        """创建并启动会话工具任务，完成后自动处理排队。"""
        if self._closed:
            return json.dumps(
                {
                    "ok": False,
                    "status": "closed",
                    "tool": name,
                    "message": "回复执行器已关闭，拒绝提交新的会话工具。",
                },
                ensure_ascii=False,
            )
        task = asyncio.create_task(
            self._run_session_tool(
                name=name,
                args=args,
                pipeline_key=pipeline_key,
                conv_kind=conv_kind,
                conv_id=conv_id,
                token=token,
            )
        )
        tid = id(task)
        self._session_tasks.add(task)
        self._session_task_info[tid] = {
            "name": name,
            "pipeline_key": pipeline_key,
            "started_at": monotonic_seconds(),
        }

        def _cleanup(t: asyncio.Task) -> None:
            self._session_tasks.discard(t)
            info = self._session_task_info.pop(tid, None)
            # 关闭后不得消费排队项、不得再启动新任务
            if self._closed:
                return
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    self._logger.warning(
                        "会话工具任务异常",
                        tool=name,
                        pipeline_key=info["pipeline_key"] if info else "",
                        error_type=type(exc).__name__,
                    )
                    if info is not None:
                        started = info.get("started_at", 0.0) or 0.0
                        self._record_session_completion(
                            info["name"],
                            info["pipeline_key"],
                            "error",
                            "工具执行异常",
                            max(0.0, monotonic_seconds() - started),
                        )
            if info:
                pk = info["pipeline_key"]
                if pk and pk in self._session_task_queue:
                    queued = self._session_task_queue.pop(pk)
                    self._logger.info(
                        "会话工具排队任务开始执行",
                        tool=queued["name"],
                        pipeline_key=pk,
                    )
                    self._start_session_tool(
                        name=queued["name"],
                        args=queued["args"],
                        pipeline_key=pk,
                        conv_kind=queued["conv_kind"],
                        conv_id=queued["conv_id"],
                        token=queued.get("token"),
                    )

        task.add_done_callback(_cleanup)

        self._logger.info(
            "会话工具已提交（后台执行）",
            tool=name,
            pipeline_key=pipeline_key,
        )

        return json.dumps(
            {
                "ok": True,
                "status": "session_submitted",
                "tool": name,
                "message": (
                    "任务已提交到后台执行，完成后会自动通知你。"
                    "请立即结束本轮回复，不要等待、不要轮询、不要调用 wait 工具。"
                ),
            },
            ensure_ascii=False,
        )

    async def _execute_cancel_task(self, args: dict) -> str:
        """手动取消后台任务或会话工具。"""
        task_type = str(args.get("task_type", ""))
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"

        if task_type == "session_tool":
            cancelled: list[str] = []
            # 取消排队中的会话工具
            if pipeline_key in self._session_task_queue:
                queued = self._session_task_queue.pop(pipeline_key)
                cancelled.append(f"排队任务 {queued['name']}")
            # 取消运行中的会话工具
            cancelled_running = 0
            for tid, info in list(self._session_task_info.items()):
                if info["pipeline_key"] == pipeline_key:
                    for task in list(self._session_tasks):
                        if id(task) == tid:
                            task.cancel()
                            cancelled_running += 1
                            break
            if cancelled_running > 0:
                cancelled.append(f"运行中任务({cancelled_running}个)")

            if not cancelled:
                return json.dumps(
                    {
                        "ok": True,
                        "message": "当前管线没有正在执行或排队的会话工具",
                    },
                    ensure_ascii=False,
                )
            self._logger.info(
                "主Agent取消会话工具",
                pipeline_key=pipeline_key,
                cancelled=cancelled,
            )
            return json.dumps(
                {
                    "ok": True,
                    "cancelled": cancelled,
                    "message": f"已取消：{', '.join(cancelled)}。排队的任务（如有）将不会执行。",
                },
                ensure_ascii=False,
            )

        if task_type == "drawing_cooldown":
            if self._drawing_manager is None:
                return json.dumps(
                    {"ok": False, "error": "绘图系统未配置"}, ensure_ascii=False
                )
            self._drawing_manager.cancel_cooldown(pipeline_key)
            self._logger.info("主Agent取消绘图冷却", pipeline_key=pipeline_key)
            return json.dumps(
                {"ok": True, "message": "已取消当前管线的绘图冷却限制"},
                ensure_ascii=False,
            )

        return json.dumps(
            {"ok": False, "error": f"未知任务类型: {task_type}"}, ensure_ascii=False
        )

    @staticmethod
    def _parse_session_timeout(raw: Any) -> int:
        """防御性解析模型传入的 timeout_seconds 并钳制到 [1, 1800]。

        数值零、空值、布尔值、Infinity/NaN 与畸形输入回退默认 300；
        负数钳制为 1，正小数向零取整。
        """
        if raw is None or isinstance(raw, bool):
            return 300
        try:
            if isinstance(raw, int):
                parsed = raw
                if parsed == 0:
                    return 300
            else:
                numeric = float(raw)
                if not math.isfinite(numeric) or numeric == 0:
                    return 300
                parsed = int(numeric)
        except (TypeError, ValueError, OverflowError):
            return 300
        return max(1, min(parsed, 1800))

    @staticmethod
    def _classify_session_result(result_text: str) -> tuple[bool, str]:
        """Return success and a safe failure summary for a session result."""
        parsed: Any = None
        parsed_json = False
        try:
            parsed = json.loads(result_text)
            parsed_json = True
        except (json.JSONDecodeError, TypeError):
            pass

        bare_text = parsed if isinstance(parsed, str) else result_text
        stripped = bare_text.strip()
        if stripped.startswith(
            _SESSION_FAILURE_PREFIXES
        ) or stripped.lower().startswith("error:"):
            return False, stripped

        if not parsed_json or not isinstance(parsed, dict):
            # Empty JSON containers are valid successful results.
            return True, ""

        for key, value in parsed.items():
            if str(key).casefold() in _SESSION_ERROR_KEYS:
                return False, _bounded_text(value, 200)

        status = parsed.get("status")
        if isinstance(status, str) and status.strip().casefold() in {
            "cancelled",
            "error",
            "failed",
            "failure",
            "timeout",
        }:
            return False, status.strip()

        if "ok" not in parsed:
            return True, ""
        ok = parsed["ok"]
        if isinstance(ok, bool):
            success = ok
        elif ok is None:
            success = False
        elif isinstance(ok, (int, float)):
            success = bool(ok) and (not isinstance(ok, float) or math.isfinite(ok))
        elif isinstance(ok, str):
            success = ok.strip().casefold() not in {
                "false",
                "no",
                "0",
                "0.0",
                "none",
                "",
            }
        else:
            success = True
        return success, "" if success else result_text

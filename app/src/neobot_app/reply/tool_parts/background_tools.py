"""后台任务、绘图与定时任务工具（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.time_context import monotonic_seconds
from neobot_chat.schema.types import ToolDefinition

from neobot_app.reply.tool_parts.common import _tool_def


class _BackgroundToolsMixin:
    async def _execute_check_background_tasks(self, args: dict) -> str:
        """查询当前聊天流的后台任务状态（绘图、定时任务、解题、会话工具）。"""
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )

        has_any_manager = (
            self._drawing_manager is not None
            or self._scheduled_task_manager is not None
            or self._problem_solver_manager is not None
            or self._notification_hub is not None
        )
        has_session_activity = (
            bool(self._session_task_info)
            or bool(self._session_task_queue)
            or bool(self._session_completed.get(pipeline_key, []))
        )

        if not has_any_manager and not has_session_activity:
            return json.dumps(
                {"ok": False, "error": "后台任务未配置"}, ensure_ascii=False
            )

        status: dict[str, Any] = {}
        if self._drawing_manager is not None:
            status.update(self._drawing_manager.get_pipeline_status(pipeline_key))
        if self._scheduled_task_manager is not None:
            status.update(
                self._scheduled_task_manager.get_pipeline_status(pipeline_key)
            )
        if self._problem_solver_manager is not None:
            status.update(
                self._problem_solver_manager.get_pipeline_status(pipeline_key)
            )
        if self._notification_hub is not None:
            status.update(self._notification_hub.get_pipeline_status(pipeline_key))

        # 当前管线的会话工具 — 运行中 + 排队中
        now = monotonic_seconds()
        active_session_tools: list[dict] = []
        for info in self._session_task_info.values():
            # "or not info["pipeline_key"]" 为防御性处理，当前逻辑下 pipeline_key 始终非空
            if info["pipeline_key"] == pipeline_key or not info["pipeline_key"]:
                active_session_tools.append(
                    {
                        "tool": info["name"],
                        "pipeline_key": info["pipeline_key"] or pipeline_key,
                        "elapsed_seconds": round(now - info["started_at"]),
                    }
                )
        if active_session_tools:
            status["active_session_tools"] = active_session_tools

        queued_tools: list[dict] = []
        for pk, queued in self._session_task_queue.items():
            if pk == pipeline_key:
                queued_tools.append(
                    {
                        "tool": queued["name"],
                        "queued_seconds": round(now - queued["queued_at"]),
                    }
                )
        if queued_tools:
            status["queued_session_tools"] = queued_tools

        # 最近完成的会话工具（防止 agent 重复执行已完成的相同任务）
        completed = self._session_completed.get(pipeline_key, [])
        if completed:
            status["completed_session_tools"] = [
                {
                    "tool": c["tool"],
                    "status": c["status"],
                    "summary": c["summary"],
                    "elapsed_seconds": c["elapsed_seconds"],
                    "completed_ago_seconds": round(now - c["completed_at"]),
                }
                for c in completed
            ]

        # 补充绘图任务的已运行时长
        active_draw = status.get("active_task")
        if isinstance(active_draw, dict) and active_draw.get("created_at"):
            try:
                created = float(active_draw["created_at"])
                active_draw["elapsed_seconds"] = round(now - created)
            except (ValueError, TypeError):
                pass

        self._logger.info(
            "主Agent查询后台任务状态",
            pipeline_key=pipeline_key,
            has_active=status.get("has_active_task"),
            cooldown=status.get("cooldown_remaining_seconds"),
            session_tools=len(active_session_tools),
            queued=len(queued_tools),
            completed=len(completed),
        )
        return json.dumps(
            {"ok": True, "pipeline_key": pipeline_key, **status}, ensure_ascii=False
        )

    async def _execute_mark_scheduled_task_complete(self, args: dict) -> str:
        if self._scheduled_task_manager is None:
            return json.dumps(
                {"ok": False, "error": "定时任务系统未配置"}, ensure_ascii=False
            )
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return json.dumps(
                {"ok": False, "error": "task_id 不能为空"}, ensure_ascii=False
            )
        result = await self._scheduled_task_manager.mark_completed(task_id)
        self._logger.info(
            "主Agent标记定时任务完成",
            task_id=task_id,
            ok=result.get("ok"),
        )
        return json.dumps(result, ensure_ascii=False)

    async def _execute_check_last_drawing(self, args: dict) -> str:
        """查询当前聊天流上一次绘图任务的详细记录。"""
        if self._drawing_manager is None:
            return json.dumps(
                {"ok": False, "error": "后台任务未配置"}, ensure_ascii=False
            )
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )
        info = self._drawing_manager.get_last_draw_info(pipeline_key)
        if info.get("found"):
            self._logger.info(
                "主Agent查询上一次绘图记录",
                pipeline_key=pipeline_key,
                task_id=info.get("task_id"),
                status=info.get("status"),
            )
        return json.dumps(
            {"ok": True, "pipeline_key": pipeline_key, **info}, ensure_ascii=False
        )

    def _define_background_tools(self, tools: list[ToolDefinition]) -> None:
        if (
            self._skill_manager is not None
            or self._drawing_manager is not None
            or self._scheduled_task_manager is not None
            or self._notification_hub is not None
        ):
            tools.append(
                _tool_def(
                    "check_background_tasks",
                    "查询当前聊天流的后台任务状态（可扩展，当前支持绘图任务）。"
                    "返回：后台任务列表及各任务的状态、进行中/冷却/最近完成/失败等信息；"
                    "活跃的会话工具（含已运行时长）；排队的会话工具；"
                    "最近完成的会话工具（含状态和结果摘要，防止重复执行已完成的相同操作）。"
                    "在决定是否调用 generate_image 之前，必须优先调用此工具检查是否有正在进行的后台任务，避免重复提交。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        # cancel_task：手动取消后台任务/会话工具
        tools.append(
            _tool_def(
                "cancel_task",
                "手动取消后台任务或会话工具。"
                "可取消正在执行的会话工具（如下载、图片解析）和其排队任务，"
                "也可取消绘图冷却限制。"
                "适用于用户想中止当前操作、或需要立即执行其他操作的场景。",
                {
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "enum": ["session_tool", "drawing_cooldown"],
                            "description": "要取消的任务类型：session_tool（取消会话工具的当前任务和排队）、drawing_cooldown（取消绘图冷却）",
                        },
                    },
                    "required": ["task_type"],
                },
            )
        )
        if self._drawing_manager is not None:
            tools.append(
                _tool_def(
                    "check_last_drawing",
                    "查看当前聊天流上一次绘图任务的详细记录。"
                    "包括：任务ID、状态（完成/失败/超时）、图片ID、提示词、错误信息等。"
                    "用于确认上一次绘图是否成功、查看生成的图片ID或失败原因。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        if self._scheduled_task_manager is not None:
            tools.append(
                _tool_def(
                    "mark_scheduled_task_complete",
                    "标记指定 UUID 的定时任务已完成。定时任务提醒会提供任务 UUID；"
                    "当你已经完成该提醒对应的事项，或用户明确表示该事项已完成时调用。"
                    "如果提醒内容注明任务配置为一次性通知且系统已自动完成当前触发窗口，发送提醒后不要再调用本工具。"
                    "对于持续通知的提醒任务和生日祝福任务，只要已经发送提醒或祝福消息，就应调用本工具标记完成；"
                    "对于持续提醒类任务，如果已经提醒三到五次仍然没有用户反馈，发送最后一次自然提醒后也应调用本工具结束本次任务。",
                    {
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "定时任务提醒中提供的 UUID。",
                            },
                        },
                        "required": ["task_id"],
                    },
                )
            )

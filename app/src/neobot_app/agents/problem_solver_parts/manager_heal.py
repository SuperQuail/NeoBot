"""解题任务执行、通知推送与失败重试。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from neobot_chat.schema.types import (
    State,
)

from neobot_app.agent_tools.contracts import ToolContext

from .models import (
    SolveTask,
    _SOLUTION_RESULT,
)


class ProblemSolverManagerHealMixin:
    """解题任务执行、通知推送与失败重试。"""

    async def _run_solve(self, task: SolveTask) -> None:
        """后台执行解题。"""
        try:
            chat_flow_id = f"{task.conversation_kind}:{task.conversation_id}"
            tool_context = ToolContext(
                owner=f"{task.pipeline_key}:{task.task_id}", chat_flow_id=task.pipeline_key,
                agent_id=task.task_id, parent_agent_id="main", human_request=False,
                user_id=task.execution_context.user_id if task.execution_context else None,
                allowed_tools=task.execution_context.allowed_tools if task.execution_context else None,
            )
            state: State = {
                "messages": [{"role": "user", "content": task.question}],
                "_delegate_context": task.delegate_context,
                "_chat_flow_id": chat_flow_id,
                "_agent_tool_context": tool_context,
            }
            result_state = await asyncio.wait_for(
                self._agent._invoke_direct(state),
                timeout=self._config.timeout_seconds,
            )

            solution = _SOLUTION_RESULT.get("")
            if not solution:
                # 尝试从结果消息中提取：收集所有 assistant 消息的文本内容
                messages = result_state.get("messages", [])
                texts = []
                for msg in messages:
                    if msg.get("role") == "assistant" and msg.get("content"):
                        texts.append(str(msg["content"]))
                if texts:
                    solution = "\n\n".join(texts)

            # 如果 agent 未提交任何答复，保留上下文再次唤起，要求明确提供答复
            if not solution:
                messages = result_state.get("messages", [])
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "你尚未调用 submit_solution 提交任何解答。"
                            "请立即提交你的最终解答（调用 submit_solution）。"
                            "即使无法解答，也必须说明失败原因（如缺少关键信息、超出能力范围等）。"
                        ),
                    }
                )
                retry_state: State = {
                    "messages": messages,
                    "_delegate_context": task.delegate_context,
                    "_chat_flow_id": chat_flow_id,
                "_agent_tool_context": tool_context,
                }
                retry_timeout = max(self._config.timeout_seconds * 0.5, 120)
                self._logger.info(
                    "解题 Agent 未提交答复，保留上下文重新唤起",
                    task_id=task.task_id,
                    retry_timeout=retry_timeout,
                )
                result_state = await asyncio.wait_for(
                    self._agent._invoke_direct(retry_state),
                    timeout=retry_timeout,
                )
                solution = _SOLUTION_RESULT.get("")
                if not solution:
                    messages = result_state.get("messages", [])
                    texts = []
                    for msg in messages:
                        if msg.get("role") == "assistant" and msg.get("content"):
                            texts.append(str(msg["content"]))
                    if texts:
                        solution = "\n\n".join(texts)

            if not solution:
                raise RuntimeError("解题 Agent 经重新唤起后仍未提交解答内容")

            task.markdown_solution = solution
            task.status = "completed"

            self._logger.info(
                "后台解题任务完成",
                task_id=task.task_id,
                solution_length=len(solution),
            )
            await self._on_completed(task)

        except asyncio.TimeoutError:
            task.status = "timeout"
            task.error = f"解题超时 ({self._config.timeout_seconds}s)"
            self._logger.warning("后台解题任务超时", task_id=task.task_id)
            await self._on_failed(task)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            self._logger.warning(
                "后台解题任务失败",
                task_id=task.task_id,
                error=str(exc),
            )
            await self._on_failed(task)

    async def _on_completed(self, task: SolveTask) -> None:
        question_preview = task.question[:200]
        solution = task.markdown_solution or ""
        header = json.dumps(
            {
                "ok": True,
                "kind": "solve_result",
                "status": "completed",
                "task_id": task.task_id,
                "question": question_preview,
                "next": [
                    {"action": "reply_to_user", "text": "按下方解题结果原文回复用户"},
                    {
                        "action": "note",
                        "text": "需要发文件时用 sandbox_manager__send_chat_file；"
                        "长文可用 send_long_reply 转图片",
                    },
                ],
            },
            ensure_ascii=False,
        )
        # 解答保持裸 Markdown：写进 JSON 会把换行转义成 \n，
        # 标题/列表/代码块在通知里变成一行字，模型抄给用户时更容易走样。
        notification = (
            f"{header}\n\n"
            "--- 解题结果（Markdown 原文，直接据此回复用户）---\n\n"
            f"{solution}\n\n"
            "--- 解题结果结束 ---"
        )
        self._logger.info(
            "推送解题完成通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
        )
        await self._push_notification(task, notification)

    async def _on_failed(self, task: SolveTask) -> None:
        question_preview = task.question[:200]
        notification = json.dumps(
            {
                "ok": False,
                "kind": "solve_result",
                "status": task.status,
                "task_id": task.task_id,
                "question": question_preview,
                "error": "解题失败",
                "next": [
                    {
                        "action": "reply_to_user",
                        "text": "告知用户解题失败，请稍后重试或补充信息；不要复述技术错误",
                    }
                ],
            },
            ensure_ascii=False,
        )
        self._logger.info(
            "推送解题失败通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            status=task.status,
        )
        await self._push_notification(task, notification)

    async def _push_notification(self, task: SolveTask, notification: str) -> None:
        if self._notification_hub is not None:
            started = await self._publish_hub_notification(task, notification)
            self._logger.info(
                "解题通知已交给统一通知中心",
                task_id=task.task_id,
                pipeline_key=task.pipeline_key,
                started_pipeline=started,
            )
            if not started and not task.notified and task.notification_count == 0:
                self._spawn_bg_task(self._retry_notification(task))
            return

        if self._orchestrator is None:
            self._logger.warning(
                "通知推送失败：orchestrator 为空", task_id=task.task_id
            )
            return

        pipeline_active = self._orchestrator.is_pipeline_key_active(task.pipeline_key)
        if not pipeline_active:
            try:
                result = self._orchestrator.start_background_reply(
                    kind=task.conversation_kind,
                    conversation_id=task.conversation_id,
                    content=notification,
                )
                if result is not None:
                    task.notified = True
                    return
            except Exception as exc:
                self._logger.warning(
                    "启动后台回复管线失败",
                    task_id=task.task_id,
                    error=str(exc),
                )

        queue = self._notification_queues.setdefault(task.pipeline_key, asyncio.Queue())
        await queue.put(notification)

        if not task.notified and task.notification_count == 0:
            self._spawn_bg_task(self._retry_notification(task))

    async def _publish_hub_notification(
        self, task: SolveTask, notification: str
    ) -> bool:
        """通过 BackgroundNotificationHub 发布通知。返回是否启动了新管线。"""
        if self._notification_hub is None:
            return False

        def _on_consumed(n: Any) -> None:
            task.notified = True

        try:
            return await self._notification_hub.publish(
                source="problem_solver",
                kind=task.conversation_kind,
                conversation_id=task.conversation_id,
                content=notification,
                manager_name="problem_solver",
                reasons=["problem solving result"],
                metadata={
                    "task_id": task.task_id,
                    "status": task.status,
                },
                on_consumed=_on_consumed,
            )
        except Exception as exc:
            self._logger.warning(
                "解题通知发布到通知中心失败",
                task_id=task.task_id,
                error=str(exc),
            )
            return False

    async def _retry_notification(self, task: SolveTask) -> None:
        max_attempts = self._config.max_retries + 1
        while task.notification_count < max_attempts and not task.notified:
            await asyncio.sleep(self._config.notification_retry_seconds)
            if task.notified:
                break
            task.notification_count += 1
            if task.notified:
                break
            self._logger.info(
                "解题通知重试",
                task_id=task.task_id,
                attempt=task.notification_count,
                max_attempts=max_attempts,
            )
            notification_text = self._build_retry_content(task)
            if self._notification_hub is not None:
                await self._publish_hub_notification(task, notification_text)

    def _build_retry_content(self, task: SolveTask) -> str:
        if task.status == "completed":
            return json.dumps(
                {
                    "ok": True,
                    "kind": "solve_result_retry",
                    "status": "completed",
                    "task_id": task.task_id,
                    "question": task.question[:200],
                    "next": [
                        {"action": "reply_to_user", "text": "检查并发送解题结果"}
                    ],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": False,
                "kind": "solve_result_retry",
                "status": task.status,
                "task_id": task.task_id,
                "error": task.error,
                "next": [
                    {
                        "action": "reply_to_user",
                        "text": "告知用户任务未完成及原因",
                    }
                ],
            },
            ensure_ascii=False,
        )

    async def shutdown(self) -> None:
        self._closed = True
        for task in list(self._tasks.values()):
            if task.status == "solving":
                task.status = "failed"
                task.error = "系统关闭，任务被取消"
        pending = list(self._bg_tasks)
        for bg_task in pending:
            bg_task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._bg_tasks.clear()
        self._tasks.clear()
        self._notification_queues.clear()
        agent = self._agent
        self._agent = None
        close = getattr(agent, "close", None)
        if callable(close):
            await close()

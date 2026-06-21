"""Background drawing task manager — submission, cooldown, notification, retry."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import httpx

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.drawing.config import DrawServiceConfig, ImageGenerationError
from neobot_app.drawing.tasks import DrawTask
from neobot_app.time_context import monotonic_seconds

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

from neobot_app.drawing.service import _record_payload

if TYPE_CHECKING:
    from neobot_app.drawing.service import CreatorImageService

class BackgroundDrawingManager:
    """管理后台绘图任务的提交、冷却、通知与重试。"""

    def __init__(
        self,
        *,
        image_service: "CreatorImageService | None" = None,
        config: DrawServiceConfig | None = None,
        logger: Logger | None = None,
        notification_hub: Any = None,
    ) -> None:
        self._service = image_service
        self._config = config or DrawServiceConfig()
        self._logger = logger or NullLogger()
        self._tasks: dict[str, DrawTask] = {}
        self._cooldowns: dict[str, float] = {}  # pipeline_key -> monotonic end time
        self._notification_queues: dict[str, asyncio.Queue[str]] = {}
        self._orchestrator: Any = None  # ReplyOrchestrator reference, set after creation
        self._notification_hub = notification_hub

    def set_image_service(self, service: "CreatorImageService") -> None:
        self._service = service

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
        if self._notification_hub is not None:
            self._notification_hub.set_orchestrator(orchestrator)

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    @property
    def background_enabled(self) -> bool:
        return self._config.draw_background_enabled and self._service is not None

    def _pipeline_key(self, kind: str, conv_id: str) -> str:
        return f"{kind}:{conv_id}"

    def check_cooldown(self, pipeline_key: str) -> int:
        """返回冷却剩余秒数，0 表示不在冷却期。"""
        deadline = self._cooldowns.get(pipeline_key, 0.0)
        remaining = deadline - monotonic_seconds()
        return max(0, int(remaining))

    def _set_cooldown(self, pipeline_key: str) -> None:
        self._cooldowns[pipeline_key] = monotonic_seconds() + self._config.draw_cooldown_seconds

    def cancel_cooldown(self, pipeline_key: str) -> None:
        self._cooldowns.pop(pipeline_key, None)

    def _get_active_task(self, pipeline_key: str) -> DrawTask | None:
        """获取指定管线的活跃绘图任务（status == drawing）。"""
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key and task.status == "drawing":
                return task
        return None

    def _enforce_task_limit(self, pipeline_key: str) -> None:
        """确保每个管线不超过最大任务数，超出时销毁最旧的非活跃任务。"""
        limit = self._config.draw_max_tasks_per_pipeline
        if limit <= 0:
            return
        pipeline_tasks = [
            t for t in self._tasks.values()
            if t.pipeline_key == pipeline_key
        ]
        if len(pipeline_tasks) <= limit:
            return
        # 按创建时间升序，优先移除旧任务；活跃任务（drawing）不删除
        pipeline_tasks.sort(key=lambda t: t.created_at)
        removed = 0
        for task in pipeline_tasks:
            if len(pipeline_tasks) - removed <= limit:
                break
            if task.status == "drawing":
                continue
            self._tasks.pop(task.task_id, None)
            removed += 1
            self._logger.info(
                "后台绘图任务超出上限已自动销毁",
                task_id=task.task_id,
                pipeline_key=pipeline_key,
                status=task.status,
                limit=limit,
            )

    def get_pipeline_status(self, pipeline_key: str) -> dict[str, Any]:
        """查询指定管线的后台绘图状态（供主 Agent 工具调用）。"""
        cooldown_remaining = self.check_cooldown(pipeline_key)
        active = self._get_active_task(pipeline_key)
        recent: list[dict[str, Any]] = []
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key and task.status != "drawing":
                recent.append({
                    "task_id": task.task_id,
                    "status": task.status,
                    "image_id": task.image_id,
                    "error": task.error,
                    "created_at": task.created_at,
                })
        return {
            "cooldown_remaining_seconds": cooldown_remaining,
            "has_active_task": active is not None,
            "active_task": {
                "task_id": active.task_id,
                "status": active.status,
                "created_at": active.created_at,
            } if active else None,
            "recent_tasks": recent[-5:],
        }

    def get_last_draw_info(self, pipeline_key: str) -> dict[str, Any]:
        """查询指定管线上一次绘图任务的详细信息（供工具调用）。

        返回最近一个已完成/失败/超时的绘图任务记录，包括开始时间、
        完成时间（通过 created_at 推算）、绘图信息或错误信息。
        若该管线从未提交过绘图任务则返回空状态。
        """
        best: DrawTask | None = None
        for task in self._tasks.values():
            if task.pipeline_key != pipeline_key:
                continue
            if task.status == "drawing":
                continue
            if best is None or task.created_at > best.created_at:
                best = task

        if best is None:
            return {"found": False, "message": "当前聊天流暂无已完成的绘图记录"}

        info: dict[str, Any] = {
            "found": True,
            "task_id": best.task_id,
            "status": best.status,
            "created_at": best.created_at,
            "prompt": best.prompt,
            "image_id": best.image_id,
            "record_payload": best.record_payload,
            "requester": best.requester or None,
            "requirements": best.requirements or None,
        }
        if best.status == "failed":
            info["error"] = best.error or "未知错误"
        if best.image_id:
            info["image_id"] = best.image_id
        if best.record_payload:
            info["record_payload"] = best.record_payload
        return info

    async def submit(
        self,
        *,
        pipeline_key: str,
        conversation_kind: str,
        conversation_id: str,
        prompt: str,
        requester: str = "",
        requirements: str = "",
        references: list[str] | None = None,
        reference_id: int | None = None,
        negative_prompt: str | None = None,
        image_size: str | None = None,
        seed: int | None = None,
    ) -> str:
        """提交后台绘图任务。返回 JSON 状态字符串。"""
        if not self.background_enabled:
            return _json({"ok": False, "error": "后台绘图未启用或服务未配置"})

        # 先检查是否有活跃任务
        active = self._get_active_task(pipeline_key)
        if active is not None:
            task_info = f"委托者: {active.requester}, 绘图要求: {active.requirements}"
            return _json({
                "ok": True,
                "status": "busy",
                "message": f"已有绘图任务正在进行中，任务信息：{task_info}，请等待任务完成后再试",
                "existing_task_id": active.task_id,
            })

        # 无活跃任务但冷却中
        remaining = self.check_cooldown(pipeline_key)
        if remaining > 0:
            return _json({
                "ok": True,
                "status": "cooldown",
                "message": f"绘图冷却中，剩余 {remaining} 秒",
                "remaining_seconds": remaining,
            })

        task = DrawTask(
            task_id=f"draw_{uuid4().hex[:12]}",
            pipeline_key=pipeline_key,
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            prompt=prompt,
            requester=requester,
            requirements=requirements,
            references=references,
            reference_id=reference_id,
            negative_prompt=negative_prompt,
            image_size=image_size,
            seed=seed,
        )
        self._tasks[task.task_id] = task
        self._enforce_task_limit(pipeline_key)
        self._set_cooldown(pipeline_key)

        bg_task = asyncio.create_task(self._run_draw(task))
        bg_task.add_done_callback(lambda _: None)  # prevent "task not awaited" warning

        grace = self._config.draw_startup_grace_seconds
        await asyncio.sleep(min(grace, 3.0))
        if task.status == "failed":
            self.cancel_cooldown(pipeline_key)
            return _json({"ok": False, "error": task.error or "绘图启动失败"})

        self._logger.info(
            "后台绘图任务已启动",
            task_id=task.task_id,
            pipeline_key=pipeline_key,
            prompt=prompt[:80],
        )
        return _json({
            "ok": True,
            "status": "drawing",
            "task_id": task.task_id,
            "message": "正在绘图，已加入后台绘图任务",
        })

    async def _run_draw(self, task: DrawTask) -> None:
        """后台执行绘图。"""
        try:
            references_raw = task.references
            references: list[str] | None = None
            if isinstance(references_raw, list):
                references = [str(r) for r in references_raw]
            image_source = f"{task.requester}要求{task.requirements}" if task.requester else None
            record = await self._service.generate_image(
                prompt=task.prompt,
                references=references,
                reference_id=task.reference_id,
                negative_prompt=task.negative_prompt,
                image_size=task.image_size,
                seed=task.seed,
                image_source=image_source,
                conv_id=f"{task.conversation_kind}:{task.conversation_id}",
            )
            task.status = "completed"
            task.image_id = record.image_id
            task.record_payload = _record_payload(record)
            self._logger.info(
                "后台绘图任务完成",
                task_id=task.task_id,
                image_id=record.image_id,
            )
            await self._on_completed(task)
        except Exception as exc:
            task.status = "failed"
            task.error = self._serialize_draw_error(exc)
            self.cancel_cooldown(task.pipeline_key)
            self._logger.warning(
                "后台绘图任务失败",
                task_id=task.task_id,
                error=task.error,
            )
            await self._on_failed(task)

    @staticmethod
    def _serialize_draw_error(exc: Exception) -> str:
        """将绘图异常序列化为完整的错误信息 JSON，供 agent 诊断。"""
        if isinstance(exc, ImageGenerationError):
            return str(exc)
        error_info: dict[str, Any] = {
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        if isinstance(exc, httpx.HTTPStatusError):
            error_info["status_code"] = exc.response.status_code
            error_info["response_body"] = exc.response.text
            error_info["request_url"] = str(exc.request.url)
        return json.dumps(error_info, ensure_ascii=False)

    async def _on_completed(self, task: DrawTask) -> None:
        """绘图完成后的通知流程——向主 Agent 提交必须处理的绘图结果。"""
        if not task.image_id:
            self._logger.error(
                "后台绘图完成但 image_id 为空，转为失败处理",
                task_id=task.task_id,
            )
            task.status = "failed"
            task.error = "绘图完成但未获取到图片ID"
            await self._on_failed(task)
            return
        record_json = _json(task.record_payload) if task.record_payload else "{}"
        requester_info = (
            f"{task.requester} - {task.requirements}"
            if task.requester
            else ""
        )
        notification = (
            f"<这是新的必须要回答的内容>\n"
            f"绘图结果通知（图片已生成完毕，不是绘图请求！）\n"
            f"\n"
            f"图片ID: {task.image_id}\n"
            f"来源: tmp（临时图片，可直接发送）\n"
            f"图片数据: {record_json}\n"
            f"原始委托: {requester_info}\n"
            f"\n"
            f"你必须立即处理此绘图结果：\n"
            f"1. 告知用户绘图已完成\n"
            f'2. 如需发送图片，使用 image_send__send 工具（image_id="{task.image_id}"，source="tmp"）\n'
            f'3. 如需加入图库，使用 gallery__add 工具（image_id="{task.image_id}"）\n'
            f"\n"
            f"注意：不要再重新绘图！图片已经生成好了。\n"
            f"</这是新的必须要回答的内容>"
        )
        self._logger.info(
            "推送绘图完成通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            image_id=task.image_id,
        )
        await self._push_notification(task, notification)

    async def _on_failed(self, task: DrawTask) -> None:
        """绘图失败后的通知流程——向主 Agent 提交必须处理的失败结果。"""
        requester_info = (
            f"{task.requester} - {task.requirements}"
            if task.requester
            else ""
        )
        error_text = task.error or "未知错误（可能是 API 超时或网络异常）"
        notification = (
            f"<这是新的必须要回答的内容>\n"
            f"绘图任务失败通知\n"
            f"\n"
            f"任务ID: {task.task_id}\n"
            f"错误原因: {error_text}\n"
            f"原始委托: {requester_info}\n"
            f"\n"
            f"你必须立即先发送消息告知用户绘图失败和失败原因，然后询问用户是否要重试。\n"
            f"不要在未询问用户的情况下自动重新提交绘图。\n"
            f"</这是新的必须要回答的内容>"
        )
        self._logger.info(
            "推送绘图失败通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            error=task.error,
        )
        await self._push_notification(task, notification)

    async def _push_notification(self, task: DrawTask, notification: str) -> None:
        """推送通知到对应管线，若无活跃管线则尝试启动。"""
        if self._notification_hub is not None:
            started = await self._publish_hub_notification(task, notification)
            self._logger.info(
                "绘图通知已交给统一通知中心",
                task_id=task.task_id,
                pipeline_key=task.pipeline_key,
                started_pipeline=started,
            )
            if not started and not task.notified and task.notification_count == 0:
                asyncio.create_task(self._retry_notification(task))
            return

        if self._orchestrator is None:
            self._logger.warning("通知推送失败：orchestrator 为空", task_id=task.task_id)
            return

        pipeline_active = self._orchestrator.is_pipeline_key_active(task.pipeline_key)
        self._logger.info(
            "准备推送绘图通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            pipeline_active=pipeline_active,
            status=task.status,
        )
        if not pipeline_active:
            # 无活跃管线，尝试启动新管线（通知作为新管线的初始消息）
            try:
                result = self._orchestrator.start_background_reply(
                    kind=task.conversation_kind,
                    conversation_id=task.conversation_id,
                    content=notification,
                )
                self._logger.info(
                    "启动后台回复管线",
                    task_id=task.task_id,
                    pipeline_key=task.pipeline_key,
                    success=result is not None,
                )
                if result is not None:
                    # 新管线已启动，通知会作为初始消息处理，不再入队
                    task.notified = True
                    return
            except Exception as exc:
                self._logger.warning(
                    "启动后台回复管线失败",
                    task_id=task.task_id,
                    error=str(exc),
                )

        # 有活跃管线，通知入队等待轮询注入
        queue = self._notification_queues.setdefault(task.pipeline_key, asyncio.Queue())
        await queue.put(notification)
        self._logger.info(
            "绘图通知已入队",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
        )

        if not task.notified and task.notification_count == 0:
            asyncio.create_task(self._retry_notification(task))

    async def _retry_notification(self, task: DrawTask) -> None:
        """通知重试定时器。"""
        max_attempts = self._config.draw_max_retries + 1
        while task.notification_count < max_attempts and not task.notified:
            await asyncio.sleep(self._config.draw_notification_retry_seconds)
            if task.notified:
                return
            task.notification_count += 1
            if task.notification_count >= max_attempts:
                break
            self._logger.info(
                "绘图通知重试",
                task_id=task.task_id,
                attempt=task.notification_count,
                max_attempts=max_attempts,
                status=task.status,
            )
            if task.status == "failed":
                error_text = task.error or "未知错误（可能是 API 超时或网络异常）"
                retry_msg = (
                    f"<这是新的必须要回答的内容>\n"
                    f"绘图任务失败通知（第{task.notification_count}次提醒）\n"
                    f"\n"
                    f"任务ID: {task.task_id}\n"
                    f"错误原因: {error_text}\n"
                    f"\n"
                    f"你必须立即先发送消息告知用户绘图失败和失败原因，然后询问用户是否要重试。\n"
                    f"不要在未询问用户的情况下自动重新提交绘图。\n"
                    f"</这是新的必须要回答的内容>"
                )
            else:
                record_json = _json(task.record_payload) if task.record_payload else "{}"
                image_id_text = task.image_id or "未知"
                retry_msg = (
                    f"<这是新的必须要回答的内容>\n"
                    f"绘图结果通知（第{task.notification_count}次提醒，图片已生成完毕！）\n"
                    f"\n"
                    f"图片ID: {image_id_text}\n"
                    f"来源: tmp（临时图片，可直接发送）\n"
                    f"图片数据: {record_json}\n"
                    f"\n"
                    f"你必须立即处理此绘图结果：\n"
                    f"1. 告知用户绘图已完成\n"
                    f"2. 如需发送图片，使用 image_send__send 工具\n"
                    f"3. 如需加入图库，使用 gallery__add 工具\n"
                    f"\n"
                    f"注意：不要再重新绘图！\n"
                    f"</这是新的必须要回答的内容>"
                )
            if self._notification_hub is not None:
                status = self._notification_hub.get_pipeline_status(task.pipeline_key)
                pending = status.get("background_notifications_by_source", {}).get("drawing", 0)
                if pending:
                    continue
                await self._publish_hub_notification(task, retry_msg)
            else:
                queue = self._notification_queues.setdefault(task.pipeline_key, asyncio.Queue())
                if not queue.empty():
                    continue
                await queue.put(retry_msg)

        if not task.notified:
            task.status = "timeout"
            self._logger.warning(
                "绘图通知超时",
                task_id=task.task_id,
                attempts=task.notification_count,
            )
            if self._notification_hub is not None:
                image_id_text = task.image_id or "未知"
                timeout_msg = (
                    f"<这是新的必须要回答的内容>\n"
                    f"绘图任务超时通知\n"
                    f"\n"
                    f"任务ID: {task.task_id}\n"
                    f"图片ID: {image_id_text}（来源：tmp）\n"
                    f"图片已保存在临时目录。\n"
                    f"\n"
                    f"请告知用户绘图任务已完成但未及时通知，"
                    f"可使用 image_send__send 工具发送图片或 gallery__add 加入图库。\n"
                    f"</这是新的必须要回答的内容>"
                )
                await self._publish_hub_notification(task, timeout_msg)
            elif self._orchestrator is not None:
                if self._orchestrator.is_pipeline_key_active(task.pipeline_key):
                    image_id_text = task.image_id or "未知"
                    timeout_msg = (
                        f"<这是新的必须要回答的内容>\n"
                        f"绘图任务超时通知\n"
                        f"\n"
                        f"任务ID: {task.task_id}\n"
                        f"图片ID: {image_id_text}（来源：tmp）\n"
                        f"图片已保存在临时目录。\n"
                        f"\n"
                        f"请告知用户绘图任务已完成但未及时通知，"
                        f"可使用 image_send__send 工具发送图片或 gallery__add 加入图库。\n"
                        f"</这是新的必须要回答的内容>"
                    )
                    queue = self._notification_queues.setdefault(task.pipeline_key, asyncio.Queue())
                    await queue.put(timeout_msg)

    async def poll_notification(self, pipeline_key: str) -> str | None:
        """轮询指定管线是否有待处理通知。返回通知文本或 None。"""
        if self._notification_hub is not None:
            notification = await self._notification_hub.poll(pipeline_key, source="drawing")
            if notification is None:
                return None
            return notification.content

        queue = self._notification_queues.get(pipeline_key)
        if queue is None or queue.empty():
            return None
        try:
            notification = queue.get_nowait()
            for task in self._tasks.values():
                if task.pipeline_key == pipeline_key and task.status != "drawing":
                    task.notified = True
            self._logger.info(
                "绘图通知已被轮询取出",
                pipeline_key=pipeline_key,
                notification_preview=notification[:120],
            )
            return notification
        except asyncio.QueueEmpty:
            return None

    async def shutdown(self) -> None:
        """取消所有进行中的后台绘图任务。"""
        for task in self._tasks.values():
            if task.status == "drawing":
                task.status = "timeout"
                self.cancel_cooldown(task.pipeline_key)
        self._notification_queues.clear()
        self._logger.info("BackgroundDrawingManager 已关闭")

    def _mark_notified(self, pipeline_key: str) -> None:
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key and task.status != "drawing":
                task.notified = True

    async def _publish_hub_notification(self, task: DrawTask, notification: str) -> bool:
        started = await self._notification_hub.publish(
            source="drawing",
            kind=task.conversation_kind,
            conversation_id=task.conversation_id,
            content=notification,
            manager_name="background_drawing",
            reasons=["drawing task notification"],
            metadata={"task_id": task.task_id, "status": task.status},
            on_consumed=lambda _notification: self._mark_notified(task.pipeline_key),
        )
        return bool(started)


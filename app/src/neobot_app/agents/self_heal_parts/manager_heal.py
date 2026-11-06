"""修复任务执行与两阶段通知。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_chat.schema.types import (
    State,
)

from neobot_app.prompt.assets import raw_text
from neobot_app.statistics.tracker import (
    CURRENT_USAGE_MODULE,
)
from neobot_app.utils.formater import safe_format

from .models import (
    HealTask,
    RESULT_SOURCE,
    START_SOURCE,
    _HEAL_TASK,
)


class SelfHealManagerHealMixin:
    """修复任务执行与两阶段通知。"""

    def _prompt_text(self, key: str) -> str:
        """读取 [self_heal] 的提示词文本(自定义文件优先,缺失时用内置模板)。"""
        return raw_text("self_heal", key, store=getattr(self, "_prompt_store", None))

    async def _publish_start_notification(self, heal: HealTask) -> None:
        """Send the «已开始工作» notification to the admin private chat."""
        if self._notification_hub is None:
            return
        samples = self._build_sample_summary(heal.error_snapshot, max_count=3)
        content = (
            "系统已检测到 Bot 出现持续异常，自修复 Agent 已开始工作。\n"
            f"触发原因：{heal.trigger_reason}\n"
            f"最近累积异常数：{len(heal.error_snapshot)}\n"
            f"样本异常：\n{samples}\n"
            f"样本异常时间范围：{heal.first_error_time} 至 {heal.last_error_time}\n"
            "请稍候。诊断完成后再发送最终报告。如需立即介入，请回复相应指令。"
        )
        try:
            await self._notification_hub.publish(
                source=START_SOURCE,
                kind="private",
                conversation_id=str(heal.admin_account),
                content=content,
                manager_name="self_heal",
                reasons=["self-heal start"],
                metadata={
                    "task_id": heal.task_id,
                    "trigger_reason": heal.trigger_reason,
                    "error_count": len(heal.error_snapshot),
                },
            )
        except Exception as exc:
            self._logger.warning(
                "自修复开始通知发布失败",
                task_id=heal.task_id,
                error=str(exc),
            )

    @staticmethod
    def _build_sample_summary(errors: list[dict[str, Any]], *, max_count: int) -> str:
        lines: list[str] = []
        for e in errors[:max_count]:
            module = str(e.get("module", "")).strip() or "?"
            msg = str(e.get("message", "")).strip().splitlines()
            msg_first = msg[0] if msg else ""
            if len(msg_first) > 200:
                msg_first = msg_first[:200] + "…"
            level = str(e.get("level", "")).strip() or "ERROR"
            lines.append(f"- [{level}] {module}: {msg_first}")
        return "\n".join(lines) if lines else "(无样本)"

    async def _run_heal(self, heal: HealTask) -> None:
        """在后台运行自修复 Agent 调用。"""
        if self._agent is None:
            heal.status = "failed"
            return
        token = None
        token_m = None
        try:
            token = _HEAL_TASK.set(heal)
            token_m = CURRENT_USAGE_MODULE.set("agent:self_heal")
            state: State = {
                "messages": [
                    {
                        "role": "user",
                        "content": self._build_initial_prompt(heal),
                    }
                ],
            }
            result_state = await asyncio.wait_for(
                self._agent._invoke_direct(state),
                timeout=self._config.timeout_seconds,
            )

            # If the agent didn't call submit_resolution, follow-up like
            # problem_solver does.
            if heal.status == "healing":
                self._logger.info(
                    "self_heal agent 未调用 submit_resolution，重新唤起提交结论",
                    task_id=heal.task_id,
                )
                messages = result_state.get("messages", [])
                messages.append(
                    {
                        "role": "user",
                        "content": self._prompt_text("resume_prompt"),
                    }
                )
                retry_state: State = {"messages": messages}
                retry_timeout = max(self._config.timeout_seconds * 0.5, 60)
                await asyncio.wait_for(
                    self._agent._invoke_direct(retry_state),
                    timeout=retry_timeout,
                )

            heal.status = heal.status if heal.status != "healing" else "completed"
            self._logger.info(
                "self_heal 任务完成",
                task_id=heal.task_id,
                status=heal.status,
                repaired=heal.repaired,
                has_debug_file=bool(heal.debug_file),
            )
            await self._publish_result_notification(heal)
        except asyncio.TimeoutError:
            heal.status = "timeout"
            heal.summary = heal.summary or "诊断超时"
            self._logger.warning("self_heal 任务超时", task_id=heal.task_id)
            await self._publish_result_notification(heal)
        except asyncio.CancelledError:
            heal.status = "failed"
            heal.summary = heal.summary or "任务被取消"
            raise
        except Exception as exc:
            heal.status = "failed"
            heal.summary = f"{type(exc).__name__}: {exc}"
            self._logger.warning(
                "self_heal 任务失败",
                task_id=heal.task_id,
                error=str(exc),
            )
            await self._publish_result_notification(heal)
        finally:
            if token is not None:
                _HEAL_TASK.reset(token)
            if token_m is not None:
                CURRENT_USAGE_MODULE.reset(token_m)
            if self._current_heal is heal:
                self._current_heal = None
            if self._running_task is asyncio.current_task():
                self._running_task = None

    async def _publish_result_notification(self, heal: HealTask) -> None:
        if heal.notified_final:
            return
        heal.notified_final = True
        if self._notification_hub is None:
            return

        summary = (heal.summary or "").strip() or "（agent 未提供摘要）"
        root_cause = (heal.root_cause or "").strip()
        debug_file = heal.debug_file
        repaired = "已自行修复" if heal.repaired else "未能自行修复"

        lines = [
            "系统自修复 Agent 已运行完毕。",
            f"触发原因：{heal.trigger_reason}",
            f"诊断摘要：{summary}",
        ]
        if root_cause:
            lines.append(f"根因：{root_cause}")
        lines.append(f"是否已自行修复：{repaired}")
        lines.append(f"调试报告：{debug_file or '未生成'}")
        if debug_file:
            lines.append(
                "调试报告可用 file_storage__read_storage_doc / sandbox_manager__read_file 读取，"
                "再用 image_send__send_image(file_path=...) 或 "
                "sandbox_manager__send_chat_file 发给管理员。"
            )
        content = "\n".join(lines)

        try:
            await self._notification_hub.publish(
                source=RESULT_SOURCE,
                kind="private",
                conversation_id=str(heal.admin_account),
                content=content,
                manager_name="self_heal",
                reasons=["self-heal result"],
                metadata={
                    "task_id": heal.task_id,
                    "status": heal.status,
                    "repaired": heal.repaired,
                    "debug_file": debug_file,
                },
            )
        except Exception as exc:
            self._logger.warning(
                "自修复结果通知发布失败",
                task_id=heal.task_id,
                error=str(exc),
            )

    def _build_initial_prompt(self, heal: HealTask) -> str:
        # 模板经 assets 读取会去掉首尾空白；旧文案末尾带一个换行，补回来逐字一致。
        return (
            safe_format(
                self._prompt_text("initial_prompt"),
                task_id=heal.task_id,
                trigger_reason=heal.trigger_reason,
                error_count=len(heal.error_snapshot),
            )
            + "\n"
        )

    async def shutdown(self) -> None:
        self._closed = True
        running_task = self._running_task
        if running_task is not None and not running_task.done():
            running_task.cancel()
            await asyncio.gather(running_task, return_exceptions=True)
        self._running_task = None
        self._current_heal = None
        self._buffer.clear()
        agent = self._agent
        self._agent = None
        close = getattr(agent, "close", None)
        if callable(close):
            await close()

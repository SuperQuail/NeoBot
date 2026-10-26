"""会话工具后台执行与完成记录（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_app.time_context import monotonic_seconds

from neobot_app.reply.tool_parts.common import _bounded_text


class _SessionRuntimeMixin:
    async def _run_session_tool(
        self,
        name: str,
        args: dict,
        pipeline_key: str,
        conv_kind: str,
        conv_id: str,
        token: Any = None,
    ) -> None:
        """在后台执行会话工具并将结果发布到 NotificationHub。

        timeout_seconds 从 args 读取（默认 300，最大 1800），用于 asyncio.wait_for。
        额外 +10 秒留给 NotificationHub publish 等收尾操作。
        """
        started_at = monotonic_seconds()
        timeout_seconds = self._parse_session_timeout(args.get("timeout_seconds", 300))
        status = "completed"
        result_summary = ""
        notification: str | None = None

        try:
            result = await asyncio.wait_for(
                self._execute_skill(name, args, token),
                timeout=timeout_seconds + 10,
            )
            result_text = _bounded_text(result)
            success, error_msg = self._classify_session_result(result_text)
            if result_text.startswith("工具不可用或已更新 ["):
                success = False
                error_msg = result_text

            if success:
                result_summary = result_text[:200]
                notification = (
                    f"<会话工具结果>\n"
                    f"工具 {name} 已完成：\n"
                    f"{result_text}\n"
                    f"请根据此结果继续处理用户的请求。\n"
                    f"</会话工具结果>"
                )
            else:
                status = "failed"
                result_summary = (error_msg or result_text)[:200]
                notification = (
                    f"<会话工具结果>\n"
                    f"工具 {name} 执行失败：{error_msg or result_text}\n"
                    f"请告知用户操作失败，并根据情况尝试替代方案。\n"
                    f"</会话工具结果>"
                )

            self._logger.info(
                "会话工具任务完成",
                tool=name,
                pipeline_key=pipeline_key,
                success=success,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            result_summary = f"超时（{timeout_seconds}秒）"
            notification = (
                f"<会话工具结果>\n"
                f"工具 {name} 执行超时（{timeout_seconds}秒）。\n"
                f"请告知用户下载超时，建议减小文件或稍后重试。\n"
                f"如需更长时间，可通过 timeout_seconds 参数设置（最长 1800 秒）。\n"
                f"</会话工具结果>"
            )
            self._logger.warning(
                "会话工具任务超时",
                tool=name,
                pipeline_key=pipeline_key,
                timeout_seconds=timeout_seconds,
            )
        except asyncio.CancelledError:
            status = "cancelled"
            result_summary = "任务被取消"
            raise
        except Exception as exc:
            status = "error"
            result_summary = "工具执行异常"
            notification = (
                f"<会话工具结果>\n"
                f"工具 {name} 执行异常。\n"
                f"请告知用户操作失败。\n"
                f"</会话工具结果>"
            )
            self._logger.error(
                "会话工具任务异常",
                tool=name,
                pipeline_key=pipeline_key,
                error_type=type(exc).__name__,
            )
        finally:
            elapsed = monotonic_seconds() - started_at
            self._record_session_completion(
                name, pipeline_key, status, result_summary, elapsed
            )

        if (
            notification is not None
            and self._notification_hub is not None
            and conv_kind
            and conv_id
        ):
            try:
                await self._notification_hub.publish(
                    source="session_tool",
                    kind=conv_kind,
                    conversation_id=conv_id,
                    content=notification,
                    manager_name="session_tool",
                    metadata={"tool_name": name, "pipeline_key": pipeline_key},
                )
            except Exception:
                self._logger.warning(
                    "会话工具通知发布失败",
                    tool=name,
                    pipeline_key=pipeline_key,
                )

    _MAX_COMPLETED_HISTORY = 5

    def _record_session_completion(
        self,
        name: str,
        pipeline_key: str,
        status: str,
        summary: str,
        elapsed: float,
    ) -> None:
        """记录已完成的会话工具，供 check_background_tasks 展示。"""
        if pipeline_key not in self._session_completed:
            self._session_completed[pipeline_key] = []
        history = self._session_completed[pipeline_key]
        history.append(
            {
                "tool": name,
                "status": status,
                "summary": summary,
                "elapsed_seconds": round(elapsed),
                "completed_at": monotonic_seconds(),
            }
        )
        if len(history) > self._MAX_COMPLETED_HISTORY:
            self._session_completed[pipeline_key] = history[
                -self._MAX_COMPLETED_HISTORY :
            ]

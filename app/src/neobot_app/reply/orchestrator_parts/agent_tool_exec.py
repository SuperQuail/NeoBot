"""agent 工具调用的执行、超时处理与结果回填。"""

from __future__ import annotations

from neobot_contracts.ports.speaking import SpeechBlocked

from typing import TYPE_CHECKING, Any

from neobot_app.reply.vision_context import labelled_tool_images
from ._runtime import asyncio
from .tool_text import (
    _MAX_TOOL_LOG_CHARS,
    _TOOL_FAILURE_HINT_AFTER,
    _bounded_tool_text,
    _parse_tool_args,
    _redacted_tool_text,
    _safe_tool_args,
    _scrub_secret_values,
)

if TYPE_CHECKING:
    from neobot_app.reply.event import ReplyEvent


class AgentToolExecMixin:

    async def _agent_execute_tool_calls(
        self,
        *,
        event: ReplyEvent,
        queue_key: str,
        iteration: int,
        tool_calls: list,
        messages: list[dict],
        reply_toolset: Any,
        tool_name_by_call_id: dict[str, str],
        tool_failure_streak: dict[str, int],
        silent_remaining,
        reset_silent_deadline,
    ) -> list[dict]:
        """逐条执行本轮 tool_calls，把工具结果写回 messages，返回图片附件。"""
        image_parts: list[dict] = []
        for tc in tool_calls:
            function = tc.get("function", {}) if isinstance(tc, dict) else {}
            if not isinstance(function, dict):
                function = {}
            name = str(function.get("name", ""))
            args = _parse_tool_args(function.get("arguments"))
            safe_args = _safe_tool_args(args)
            self._logger.info(
                f"工具调用: {name}",
                event_id=event.event_id,
                tool=name,
                args=safe_args,
            )
            self._record_debug(
                "tool_called",
                event,
                queue_key=queue_key,
                iteration=iteration + 1,
                tool_name=name,
                tool_args=safe_args,
            )
            wait_extra_seconds = 0.0
            if name == "wait":
                raw_seconds = args.get("seconds", 20)
                try:
                    parsed_seconds = int(raw_seconds)
                except (ValueError, TypeError):
                    parsed_seconds = 20
                wait_extra_seconds = float(
                    max(1, min(parsed_seconds, self._get_max_wait_seconds()))
                )
            reset_silent_deadline(wait_extra_seconds)
            result: object | None = None
            safe_result: str | None = None
            tool_error: str | None = None
            remaining: float | None = None
            tool_failure_key = self._tool_failure_key(name, args)
            try:
                remaining = silent_remaining()
                tool_timeout = (
                    max(0.1, remaining)
                    if remaining is not None
                    else max(
                        self._get_model_response_timeout_seconds(event),
                        wait_extra_seconds
                        + self._get_dependency_timeout_seconds(),
                    )
                )
                if not reply_toolset.executor.is_tool_authorized(name):
                    result = reply_toolset.executor.authorization_error(name)
                else:
                    before_tool = await self._emit_runtime_event(
                        "tool.call.before",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        tool_name=name,
                        # 保持可变原始参数供 before 钩子注入/改写工具调用
                        tool_args=args,
                        timeout_seconds=tool_timeout,
                    )
                    name = str(before_tool.payload.get("tool_name", name))
                    args = _parse_tool_args(
                        before_tool.payload.get("tool_args", args)
                    )
                    safe_args = _safe_tool_args(args)

                    # A hook may rewrite both tool and arguments. Recompute
                    # wait allowance and authorization from the final call.
                    wait_extra_seconds = 0.0
                    if name == "wait":
                        raw_seconds = args.get("seconds", 20)
                        try:
                            parsed_seconds = int(raw_seconds)
                        except (ValueError, TypeError):
                            parsed_seconds = 20
                        wait_extra_seconds = float(
                            max(
                                1,
                                min(
                                    parsed_seconds,
                                    self._get_max_wait_seconds(),
                                ),
                            )
                        )
                    reset_silent_deadline(wait_extra_seconds)
                    remaining = silent_remaining()
                    tool_timeout = (
                        max(0.1, remaining)
                        if remaining is not None
                        else max(
                            self._get_model_response_timeout_seconds(event),
                            wait_extra_seconds
                            + self._get_dependency_timeout_seconds(),
                        )
                    )
                    tool_failure_key = self._tool_failure_key(name, args)
                    if not reply_toolset.executor.is_tool_authorized(name):
                        result = reply_toolset.executor.authorization_error(
                            name
                        )
                    elif before_tool.consumed:
                        result = before_tool.result
                    else:
                        result = await asyncio.wait_for(
                            reply_toolset.executor.execute(name, args),
                            timeout=tool_timeout,
                        )
                after_tool = await self._emit_runtime_event(
                    "tool.call.after",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    # after 事件不再携带原始参数，使用脱敏后的参数文本
                    tool_args=safe_args,
                    tool_result=result,
                )
                result = after_tool.payload.get("tool_result", result)
                if getattr(self._provider, "native_vision", False) is True:
                    from neobot_app.skills.image_context_skill import ImageContextResult

                    if isinstance(result, ImageContextResult):
                        image_parts.extend(labelled_tool_images(result, tool_call_id=str(tc.get("id", ""))))
                safe_result = _redacted_tool_text(result, _MAX_TOOL_LOG_CHARS)
                result = _bounded_tool_text(result)
            except asyncio.TimeoutError:
                tool_error = (
                    f"工具 {name} 执行超时"
                    f"（已等待 {tool_timeout:.1f} 秒）"
                )
                self._logger.warning(
                    "agent 工具调用超时",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    tool=name,
                    timeout_seconds=tool_timeout,
                )
                await self._emit_runtime_event(
                    "tool.call.after",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=safe_args,
                    tool_error=tool_error,
                    timed_out=True,
                )
            except SpeechBlocked:
                raise
            except Exception as tool_exc:
                # 保留失败原因：只记 error_type 的话，日志与模型都拿不到
                # 真实原因（旧实现连 str(exc) 都没保留）。回给模型的文案
                # 先脱敏，避免异常信息里的密钥进入 LLM 上下文。
                raw_detail = f"{type(tool_exc).__name__}: {tool_exc}".strip()
                detail = _scrub_secret_values(raw_detail)[:300]
                tool_error = f"工具 {name} 执行失败：{detail}"
                self._logger.warning(
                    f"工具调用失败: {name}",
                    event_id=event.event_id,
                    tool=name,
                    error=detail,
                )
                await self._emit_runtime_event(
                    "tool.call.after",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=safe_args,
                    tool_error=tool_error,
                )
            tool_call_id = (
                str(tc.get("id", "")) if isinstance(tc, dict) else ""
            )
            if tool_call_id:
                tool_name_by_call_id[tool_call_id] = name
            if tool_error is not None:
                tool_failure_streak[tool_failure_key] = (
                    tool_failure_streak.get(tool_failure_key, 0) + 1
                )
                failures = tool_failure_streak[tool_failure_key]
                hint = ""
                if failures >= _TOOL_FAILURE_HINT_AFTER:
                    # 软限制：只提示不短路。同工具同参数连续失败说明大概率是
                    # 环境/权限问题，再重试只会把推理链拖长（截断的放大器）；
                    # 但调用依旧真实执行，修复环境后立刻就能继续用。
                    hint = "\n" + self._tool_repeat_failure_hint(name, failures)
                    self._logger.warning(
                        f"工具连续失败，已附加软提示: {name}",
                        event_id=event.event_id,
                        tool=name,
                        failures=failures,
                    )
                    self._record_debug(
                        "tool_repeat_failure_hint",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        tool_name=name,
                        tool_args=safe_args,
                        failures=failures,
                        tool_error=tool_error,
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": f"工具调用失败：{tool_error}{hint}",
                    }
                )
                self._record_debug(
                    "tool_failed",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=safe_args,
                    tool_error=tool_error,
                )
            else:
                tool_failure_streak.pop(tool_failure_key, None)
                self._logger.info(
                    f"工具返回: {name}",
                    event_id=event.event_id,
                    tool=name,
                    result=safe_result,
                )
                self._record_debug(
                    "tool_returned",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=safe_args,
                    tool_result=safe_result,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": str(result),
                    }
                )
        return image_parts

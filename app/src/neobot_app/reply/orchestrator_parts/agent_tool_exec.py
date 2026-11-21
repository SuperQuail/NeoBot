"""agent 工具调用的执行、超时处理与结果回填。"""

from __future__ import annotations

from neobot_contracts.ports.speaking import SpeechBlocked

from typing import TYPE_CHECKING, Any

from neobot_app.bot_accounts import bot_account_for_event
from neobot_app.message.queue import SelfSentToolCall
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
    from neobot_app.message.queue import MessageQueue
    from neobot_app.reply.event import ReplyEvent


#: 会自行写回 full self-sent 历史（含产物参数/索引）的发送工具，这里不再重复记录。
_SEND_TOOLS = frozenset({"send_reply", "speak", "send_long_reply", "send_official_markdown"})


def _tool_call_ok(result: object, error: str | None) -> bool:
    """工具调用是否成功；只用于 compact 历史里的成功/失败标记。"""
    if error is not None:
        return False
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        if result.get("ok") is False:
            return False
        status = str(result.get("status") or "").strip().casefold()
        if status in {"failed", "error"}:
            return False
        return True
    text = str(result or "").strip()
    if not text:
        return True
    if text.startswith("错误") or text.startswith("失败"):
        return False
    lowered = text.casefold()
    return not (lowered.startswith("error:") or lowered.startswith("error ") or lowered.startswith("failed"))


class AgentToolExecMixin:
    async def _agent_execute_tool_calls(
        self,
        *,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
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
            self._logger.debug(
                "开始执行工具",
                event="tool.started",
                chat_flow_id=(f"{event.conversation_ref.kind}:{queue_key}" if event.conversation_ref else queue_key),
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
                wait_extra_seconds = float(max(1, min(parsed_seconds, self._get_max_wait_seconds())))
            reset_silent_deadline(wait_extra_seconds)
            result: object | None = None
            raw_result: object | None = None
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
                        wait_extra_seconds + self._get_dependency_timeout_seconds(),
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
                    args = _parse_tool_args(before_tool.payload.get("tool_args", args))
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
                            wait_extra_seconds + self._get_dependency_timeout_seconds(),
                        )
                    )
                    tool_failure_key = self._tool_failure_key(name, args)
                    if not reply_toolset.executor.is_tool_authorized(name):
                        result = reply_toolset.executor.authorization_error(name)
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
                        image_parts.extend(
                            labelled_tool_images(
                                result,
                                tool_call_id=str(tc.get("id", "")),
                                prompt_store=getattr(self, "_prompt_store", None),
                            )
                        )
                raw_result = result
                safe_result = _redacted_tool_text(result, _MAX_TOOL_LOG_CHARS)
                result = _bounded_tool_text(result)
            except asyncio.TimeoutError:
                tool_error = f"工具 {name} 执行超时（已等待 {tool_timeout:.1f} 秒）"
                self._logger.warning(
                    "工具执行超时",
                    event="tool.failed",
                    chat_flow_id=(
                        f"{event.conversation_ref.kind}:{queue_key}" if event.conversation_ref else queue_key
                    ),
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
                    "工具执行失败",
                    event="tool.failed",
                    chat_flow_id=(
                        f"{event.conversation_ref.kind}:{queue_key}" if event.conversation_ref else queue_key
                    ),
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
            tool_call_id = str(tc.get("id", "")) if isinstance(tc, dict) else ""
            if tool_call_id:
                tool_name_by_call_id[tool_call_id] = name
            if tool_error is not None:
                tool_failure_streak[tool_failure_key] = tool_failure_streak.get(tool_failure_key, 0) + 1
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
                self._logger.debug(
                    "工具执行完成",
                    event="tool.completed",
                    chat_flow_id=(
                        f"{event.conversation_ref.kind}:{queue_key}" if event.conversation_ref else queue_key
                    ),
                    event_id=event.event_id,
                    tool=name,
                    result_chars=len(str(safe_result)),
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
            # 非发送工具也留痕：低权重入队（重置后 compact 重建）+ 异步落库。
            # 发送工具已由 sender 写回 full self-sent 记录，跳过避免重复。
            call_ok = _tool_call_ok(raw_result if raw_result is not None else result, tool_error)
            # 发送工具成功时已有 full self-sent 记录；失败时没有正文记录，补一条
            # compact 失败历史，避免重置后模型以为「从没试过」。
            if name not in _SEND_TOOLS or not call_ok:
                self._record_tool_call_history(
                    event=event,
                    queue=queue,
                    queue_copy=queue_copy,
                    queue_key=queue_key,
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                    result=result,
                    ok=call_ok,
                    error=tool_error,
                    call_id=tool_call_id,
                    compact=True,
                )
        return image_parts

    def _record_tool_call_history(
        self,
        *,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        name: str,
        arguments: dict,
        result: object,
        ok: bool,
        error: str | None,
        call_id: str,
        compact: bool = True,
    ) -> None:
        """记录一次非发送工具调用（compact 显示 + 完整数据落库）。

        入队是为了回复管线重置后仍能看到「刚才调过什么工具」；显示只保留工具名
        与成败，arguments/result 的完整数据仍随条目和 MessageData 保留。
        入队/落库失败只记日志，绝不影响工具执行结果。
        """
        conv_ref = event.conversation_ref
        if conv_ref is None:
            return
        record = SelfSentToolCall(
            name=name,
            arguments=dict(arguments),
            result={"ok": True, "value": result} if ok else {"ok": False, "error": error or ""},
            ok=ok,
            compact=compact,
            call_id=call_id,
        )
        try:
            queue.push_tool_call(queue_key, record)
            if queue_copy is not None and queue_copy is not queue:
                queue_copy.push_tool_call(queue_key, record)
        except Exception as exc:
            self._logger.warning(
                "工具调用未写入会话上下文",
                event="tool.history_queue_failed",
                event_id=event.event_id,
                tool=name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return
        try:
            self._sender.schedule_persist_tool_call(
                conv_ref, record, bot_account=bot_account_for_event(event, self._config)
            )
        except Exception as exc:
            self._logger.warning(
                "工具调用未排入落盘",
                event="tool.history_persist_failed",
                event_id=event.event_id,
                tool=name,
                error_type=type(exc).__name__,
                error=str(exc),
            )

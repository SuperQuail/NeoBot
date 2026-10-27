"""agent 循环的模型调用与调用前后处理。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from neobot_app.reply.event import ReplyState
from neobot_app.reply.vision_context import ReplyVisionContext
from neobot_app.statistics.tracker import get_usage_tracker
from ._runtime import asyncio
from .empty_turn import _extract_finish_reason, _extract_usage_summary

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue
    from neobot_app.reply.event import ReplyEvent


class AgentModelCallMixin:

    async def _agent_pre_model_check(
        self,
        *,
        iteration: int,
        event: ReplyEvent,
        queue_key: str,
        messages: list[dict],
        native_vision_active: bool,
        tools: list[dict],
        reply_toolset: Any,
    ) -> tuple[bool, bool, list[dict]]:
        """模型调用前的待机/视觉能力检查；返回 (是否继续, 原生视觉开关, 工具定义)。"""
        # 待机熔断：进入待机后已启动的管线必须立刻停火，
        # 否则一次风暴期间仍然会把排队中的模型调用全部跑完。
        if self.is_standby():
            self._logger.warning(
                "Bot 已进入待机，回复管线提前结束",
                event_id=event.event_id,
                queue_key=queue_key,
                iteration=iteration + 1,
            )
            try:
                event.transition(ReplyState.CANCELLED)
            except RuntimeError:
                pass
            return False, native_vision_active, tools
        if self._provider is None:
            raise RuntimeError("未配置 chat provider，无法生成回复")

        current_vision = getattr(self._provider, "native_vision", False) is True
        if current_vision != native_vision_active:
            native_vision_active = current_vision
            tools = reply_toolset.executor.definitions()
            messages.append({"role": "user", "content": "[视觉能力变更] 原生视觉已关闭，图片未发送；外部图片解析工具已恢复，请按需重新解析。"})
        return True, native_vision_active, tools

    async def _agent_refresh_default_images(
        self,
        *,
        vision_context: ReplyVisionContext,
        queue_copy: MessageQueue,
        queue_key: str,
        numbering: Any,
        default_image_loader: Any,
        pipeline_key: str,
        silent_remaining: Callable[[], float | None],
    ) -> None:
        """刷新原生视觉的默认图片附件（超时只告警，不打断本轮）。"""
        try:
            await asyncio.wait_for(
                vision_context.refresh_defaults(
                    queue=queue_copy, queue_key=queue_key, numbering=numbering,
                    loader=default_image_loader, pipeline_key=pipeline_key,
                    max_images=self._get_native_vision_default_image_count(),
                ),
                timeout=max(0.1, silent_remaining() or self._get_dependency_timeout_seconds()),
            )
        except asyncio.TimeoutError:
            self._logger.warning("默认原生视觉图片加载超时", queue_key=queue_key)

    async def _agent_call_model(
        self,
        *,
        event: ReplyEvent,
        queue_key: str,
        iteration: int,
        remaining: float | None,
        request_messages: list[dict],
        tools: list[dict],
        reset_silent_deadline: Callable[[float], None],
        cancel_for_silence: Callable[[str], None],
    ) -> tuple[Any, list[dict], list[dict]] | None:
        """发起一次模型调用；返回 (响应, 最终消息列表, 工具定义)，None 表示应结束本轮。"""
        try:
            model_timeout = (
                max(0.1, remaining)
                if remaining is not None
                else self._get_model_response_timeout_seconds(event)
            )
            before_model = await self._emit_runtime_event(
                "model.call.before",
                event,
                queue_key=queue_key,
                iteration=iteration + 1,
                messages=request_messages,
                tools=tools if tools else None,
                timeout_seconds=model_timeout,
            )
            if before_model.consumed and isinstance(before_model.result, dict):
                response = before_model.result
            else:
                request_messages = before_model.payload.get("messages", request_messages)
                tools = before_model.payload.get("tools", tools)
                response = await asyncio.wait_for(
                    self._provider.chat(
                        request_messages, tools=tools if tools else None
                    ),
                    timeout=model_timeout,
                )
            after_model = await self._emit_runtime_event(
                "model.call.after",
                event,
                queue_key=queue_key,
                iteration=iteration + 1,
                messages=request_messages,
                response=response,
            )
            response = after_model.payload.get("response", response)
        except asyncio.TimeoutError:
            if remaining is not None:
                cancel_for_silence("model")
                return None
            event.error = "AI response timed out"
            try:
                event.transition(ReplyState.CANCELLED)
            except RuntimeError:
                pass
            self._logger.warning(
                "agent 模式模型调用超时",
                event_id=event.event_id,
                queue_key=queue_key,
                timeout_seconds=self._get_model_response_timeout_seconds(event),
            )
            return None
        reset_silent_deadline()
        return response, request_messages, tools

    async def _agent_after_model_response(
        self,
        *,
        event: ReplyEvent,
        queue_key: str,
        iteration: int,
        request_messages: list[dict],
        response: Any,
        messages: list[dict],
        tools: list[dict],
        native_vision_active: bool,
        reply_toolset: Any,
    ) -> tuple[bool, list, list[dict], bool]:
        """记录本轮用量/调试信息，并解出 tool_calls 与视觉回退状态。"""
        self._record_cache_request(request_messages, response)

        await self._record_context(
            event,
            request_messages,
            iteration=iteration + 1,
            stage="agent_model_call",
            response=response,
        )

        usage = (response.get("extensions") or {}).get("usage")
        if isinstance(usage, dict) and hasattr(self._provider, "model"):
            try:
                conv_ref = event.conversation_ref
                await get_usage_tracker().record(
                    module="reply_agent",
                    model_name=self._provider.model,
                    registered_key=getattr(self._provider, "registered_key", ""),
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cache_hit_tokens=usage.get("cache_hit_tokens", 0),
                    cache_miss_tokens=usage.get("cache_miss_tokens", 0),
                    conversation_kind=conv_ref.kind if conv_ref else "",
                    conversation_id=conv_ref.id if conv_ref else "",
                )
                if self._balance_checker is not None:
                    await self._balance_checker.check_and_notify()
            except Exception:
                pass

        # 规范化：把「这一轮为什么结束」与「预算用在哪」提升为一级字段，
        # 排查截断时不必再挖 response.extensions 的嵌套结构。
        iteration_counters = _extract_usage_summary(response)
        self._record_debug(
            "agent_iteration",
            event,
            queue_key=queue_key,
            iteration=iteration + 1,
            response=response,
            finish_reason=_extract_finish_reason(response) or None,
            max_tokens=getattr(self._provider, "max_tokens", None),
            output_tokens=iteration_counters["output_tokens"],
            reasoning_tokens=iteration_counters["reasoning_tokens"],
        )
        messages.append(response)

        vision_just_disabled = native_vision_active and (
            getattr(self._provider, "native_vision", False) is not True
        )
        if vision_just_disabled:
            native_vision_active = False
            tools = reply_toolset.executor.definitions()
            self._record_debug(
                "native_vision_fallback", event, queue_key=queue_key,
                degradation=getattr(self._provider, "vision_degradation", None),
            )
        tool_calls = response.get("tool_calls")
        return vision_just_disabled, tool_calls, tools, native_vision_active

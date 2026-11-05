"""调试记录、上下文落盘、聊天流快照与缓存续用判定。"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING
from neobot_contracts.ports.runtime_event import RuntimeEnvelope
from neobot_app.reply.event import ReplyEvent
from ._runtime import asyncio
if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

class ObservabilityMixin:
    def _provider_cache_key(self) -> str:
        if self._provider is not None:
            model = getattr(self._provider, "model", None)
            if model:
                return str(model)
        return "chat"
    def _record_cache_request(self, messages: list[dict], response: dict) -> None:
        """记录一次聊天管线模型调用(构建缓存前缀单元)。

        仅聊天管线接入;记忆总结/子Agent/非聊天模型不调用本方法。
        成本管线关闭时不启用,不占用性能。
        """
        if not self._cost_pipeline_enabled():
            return
        calculator = self._cache_calculator
        if calculator is None:
            return
        try:
            from neobot_app.cache import serialize_messages, serialize_response_text

            calculator.record(
                self._provider_cache_key(),
                serialize_messages(messages),
                serialize_response_text(response),
            )
        except Exception:
            self._logger.debug(
                "缓存计算记录失败(忽略)", exc_info=True,
            )
    def _cache_continue_cheaper_than_restart(
        self,
        messages: list[dict],
        system_prompt: str = "",
        queue: MessageQueue | None = None,
        queue_key: str = "",
        numbering: Any = None,
    ) -> bool:
        """成本续用决策:计算缓存命中后的继续成本是否低于重启管线的输入成本。

        - 继续成本:当前消息列表按缓存命中计价(命中前缀部分按 1/差价)
        - 重启成本:重新构建的 [system + 角色消息] 全量输入按未命中计价
          (即"重启一个聊天管线的输入成本")
        - 存在有效命中时继续更便宜才续用
        """
        if not self._cost_pipeline_enabled():
            return False
        # The character-prefix calculator collapses multimodal blocks to one
        # placeholder. Do not extend a pipeline based on that false cost saving.
        if any(
            isinstance(message.get("content"), list) and any(
                isinstance(part, dict) and part.get("type") in {"image_url", "image", "file"}
                for part in message["content"]
            )
            for message in messages
        ):
            return False
        calculator = self._cache_calculator
        if calculator is None:
            return False
        try:
            from neobot_app.cache import serialize_messages

            continue_text = serialize_messages(messages)
            if not continue_text:
                return False
            continue_estimate = calculator.estimate_cost(
                self._provider_cache_key(), continue_text
            )
            # 前置:必须存在有效缓存命中(否则"继续更便宜"无从谈起,
            # 纯长度比较会受消息渲染差异干扰)
            if not continue_estimate.cheaper_than_full_miss():
                return False
            continue_cost = continue_estimate.cost

            # 重启管线的输入:system + 从队列重新构建的角色消息
            restart_text = continue_text
            if system_prompt and queue is not None and queue_key:
                from neobot_app.prompt.role_messages import build_role_messages

                fresh_roles = build_role_messages(
                    queue,
                    queue_key,
                    numbering=numbering,
                    bot_account=self._get_bot_account(),
                    include_boundary_markers=self._show_boundary_markers(),
                )
                restart_text = serialize_messages(
                    [{"role": "system", "content": system_prompt}] + fresh_roles
                )
            if not restart_text:
                return False
            restart_cost = float(len(restart_text))
            return continue_cost < restart_cost
        except Exception:
            return False
    def _flow_key(self, event: ReplyEvent, queue_key: str) -> str:
        ref = event.conversation_ref
        kind = getattr(ref, "kind", "") if ref is not None else ""
        return f"{kind}:{queue_key}" if kind else ""
    @staticmethod
    def _flow_queue_key(event: ReplyEvent) -> str:
        """从事件推导队列键(common 模式的 _generate_reply 拿不到 queue_key)。"""
        ref = event.conversation_ref
        if ref is None:
            return ""
        return str(getattr(ref, "id", "") or "")
    def _flow_conversation(self, event: ReplyEvent, queue_key: str) -> tuple[str, str]:
        ref = event.conversation_ref
        kind = getattr(ref, "kind", "") if ref is not None else ""
        return str(kind or ""), str(queue_key or "")
    def _current_model_name(self) -> str:
        return str(getattr(self._provider, "model", "") or "")
    def _record_flow_prompt(self, event: ReplyEvent, queue_key: str, prompt: str) -> None:
        """登记本轮 system 提示词;未接入面板时零开销。"""
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        kind, conv_id = self._flow_conversation(event, queue_key)
        try:
            registry.record_prompt(
                key,
                system_prompt=prompt,
                model=self._current_model_name(),
                conversation_kind=kind,
                conversation_id=conv_id,
            )
        except Exception as exc:
            self._logger.warning("面板提示词快照登记失败", chat_flow_id=key, error=str(exc), exc_info=True)

    def _record_flow_request(
        self,
        event: ReplyEvent,
        queue_key: str,
        messages: list[dict],
        *,
        iteration: int = 0,
    ) -> None:
        """登记最近一次模型请求的消息列表。"""
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        try:
            registry.record_request(
                key,
                messages=messages,
                model=self._current_model_name(),
                iteration=iteration,
            )
        except Exception as exc:
            self._logger.warning("面板请求快照登记失败", chat_flow_id=key, error=str(exc), exc_info=True)

    def _set_flow_active(self, event: ReplyEvent, queue_key: str, active: bool) -> None:
        registry = self._flow_registry
        if registry is None:
            return
        key = self._flow_key(event, queue_key)
        if not key:
            return
        try:
            registry.set_active(key, active)
        except Exception as exc:
            self._logger.warning("面板活动状态登记失败", chat_flow_id=key, error=str(exc), exc_info=True)

    def _record_debug(self, stage: str, event: ReplyEvent, **extra: object) -> None:
        self._debug_helper.record(stage, event, **extra)
    async def _record_context(
        self,
        event: ReplyEvent,
        messages: list[dict],
        *,
        iteration: int,
        stage: str,
        response: dict | None = None,
    ) -> None:
        """记录一轮模型调用的完整上下文与输出(滚动保留最近 N 轮,默认 100)。

        用于事后分析 token 构成:每轮迭代/每次模型调用一份,
        内容为发送给模型的完整 messages(含 system prompt)、模型输出(response)
        以及数据包中的 usage/缓存命中率。

        记录器是**纯内存 + 逐份 diff** 的(features/spec(10)):不再落盘,图片 base64
        在写入侧换成 sha256 哈希,因此这仍然走线程池、不阻塞事件循环。
        """
        recorder = self._context_recorder
        if recorder is None:
            return
        try:
            total_chars = 0
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if content is not None:
                    total_chars += len(str(content))

            # 模型输出与 usage(与 usage tracker 同一来源:extensions.usage)
            output_text = ""
            usage: dict | None = None
            if isinstance(response, dict):
                output_content = response.get("content")
                if output_content is not None:
                    output_text = str(output_content)
                extensions = response.get("extensions")
                if isinstance(extensions, dict):
                    candidate = extensions.get("usage")
                    if isinstance(candidate, dict):
                        usage = candidate
            cache_hit_rate: float | None = None
            if usage is not None:
                hit = usage.get("cache_hit_tokens", 0) or 0
                miss = usage.get("cache_miss_tokens", 0) or 0
                total = hit + miss
                if total > 0:
                    cache_hit_rate = round(hit / total, 4)

            conv_ref = event.conversation_ref
            from datetime import datetime, timezone

            conv_kind = getattr(conv_ref, "kind", "") if conv_ref else ""
            conv_id = getattr(conv_ref, "id", "") if conv_ref else ""
            # pipeline_key 让面板能把「提示词历史」按聊天流过滤（spec(3) §4.2）
            payload = {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "event_id": event.event_id,
                "mode": event.mode,
                "conversation_kind": conv_kind,
                "conversation_id": conv_id,
                "pipeline_key": f"{conv_kind}:{conv_id}" if conv_kind else "",
                "iteration": iteration,
                "messages_count": len(messages),
                "total_chars": total_chars,
                "estimated_tokens": self._estimate_tokens(messages),
                "output_chars": len(output_text),
                "output_estimated_tokens": int(len(output_text) / 0.75),
                "usage": usage,
                "cache_hit_tokens": (
                    usage.get("cache_hit_tokens", 0) if usage else None
                ),
                "cache_miss_tokens": (
                    usage.get("cache_miss_tokens", 0) if usage else None
                ),
                "cache_hit_rate": cache_hit_rate,
                "messages": messages,
                "response": response,
            }
            await asyncio.to_thread(recorder.record_context, payload)
        except Exception as exc:
            self._logger.debug(
                "聊天上下文记录失败",
                event_id=event.event_id,
                error=str(exc),
            )
    async def _emit_runtime_event(
        self, stage: str, event: ReplyEvent, **payload: object
    ) -> RuntimeEnvelope:
        return await self._debug_helper.emit_runtime_event(stage, event, **payload)
    async def _handle_runtime_failure(self, event: ReplyEvent, exc: Exception) -> None:
        return await self._debug_helper.handle_runtime_failure(
            event,
            exc,
            provider_error_message=self._provider_error_message,
            send_with_timeout=self._send_with_timeout,
        )

"""模型回复生成与私聊历史压缩。"""
from __future__ import annotations

import json
from typing import Any
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.vision_context import append_image_context, labelled_tool_images, visible_content_length
from neobot_app.statistics.tracker import get_usage_tracker
from ._runtime import asyncio

class GenerateMixin:
    async def _compact_private_history(
        self,
        messages: list[dict],
        *,
        event: Any,
        queue_key: str,
    ) -> bool:
        """私聊超限时把较早历史压成 DSH 风格检查点；失败返回 False。"""
        from neobot_app.runtime.compact import compact_messages

        original = len(messages)
        max_tokens = self._get_private_chat_max_tokens()
        # 一次 compact 后仍可能超限（检查点本身较大）；最多再压两轮。
        for attempt in range(3):
            retain = 8 if attempt == 0 else max(2, 8 // (attempt + 1))
            try:
                result = await compact_messages(
                    self._provider,
                    messages,
                    retain=retain,
                    timeout=max(10.0, self._get_model_response_timeout_seconds(event)),
                )
            except Exception as exc:
                self._logger.warning(
                    "私聊上下文压缩失败",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    error=f"{type(exc).__name__}: {exc}",
                )
                return False
            if not result:
                self._logger.warning(
                    "私聊上下文压缩未产生有效检查点",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    attempt=attempt + 1,
                )
                return False
            messages[:] = result["messages"]
            estimated = self._estimate_tokens(messages)
            self._logger.info(
                "私聊上下文已压缩",
                event_id=event.event_id,
                queue_key=queue_key,
                attempt=attempt + 1,
                removed_messages=result.get("removed", 0),
                messages_before=original,
                messages_after=len(messages),
                estimated_tokens=estimated,
                max_tokens=max_tokens,
            )
            self._record_debug(
                "private_context_compacted",
                event,
                queue_key=queue_key,
                attempt=attempt + 1,
                removed=result.get("removed", 0),
                before=original,
                after=len(messages),
                estimated_tokens=estimated,
                max_tokens=max_tokens,
            )
            if estimated < max_tokens:
                return True
        self._logger.warning(
            "私聊上下文压缩后仍超限",
            event_id=event.event_id,
            queue_key=queue_key,
            estimated_tokens=estimated,
            max_tokens=max_tokens,
        )
        return False
    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        total_chars = sum(
            len(str({key: value for key, value in m.items() if key != "content"}))
            + visible_content_length(m.get("content"))
            for m in messages
        )
        # 中文为主：1 字符 ≈ 1.3-1.5 token；用 /0.75 做偏保守估计
        return int(total_chars / 0.75)
    async def _generate_reply(
        self,
        event: ReplyEvent,
        prompt: str,
        role_messages: list[dict[str, str]] | None = None,
        context_messages: list[dict[str, str]] | None = None,
    ) -> str:
        event.transition(ReplyState.GENERATING)
        if self._provider is None:
            raise RuntimeError("未配置 chat provider，无法生成回复")

        messages: list[dict] = [
            {"role": "system", "content": prompt},
        ]
        if context_messages:
            messages.extend(context_messages)
        if role_messages:
            messages.extend(role_messages)
        common_image_parts: list[dict] = []
        if getattr(self._provider, "native_vision", False) is True:
            from neobot_app.skills.image_context_skill import ImageContextSkill

            loader = ImageContextSkill(adapter=self._adapter)
            loaded = await loader.load_message(
                event.message, max_images=self._get_native_vision_default_image_count(),
            )
            common_image_parts = labelled_tool_images(loaded, tool_call_id="当前消息默认图片", automatic=True)
            if not json.loads(loaded).get("ok"):
                self._logger.warning("原生视觉图片加载失败", result=str(loaded))
                messages.append({"role": "user", "content": f"[图片未加载，不能声称看过图片] {loaded}"})
        if event.background_content:
            messages.append({"role": "user", "content": event.background_content})
            self._record_debug(
                "background_notification_injected_initial",
                event,
                notification=event.background_content[:200],
            )
        # 回复前追加独立的 <当前时间> user 块
        time_block = self._build_current_time_message()
        if time_block is not None:
            messages.append(time_block)
        # 防重复提醒:common 路径只有一次模型调用,追加一次即可(独立于时间块开关)
        avoid_repeat_message = self._build_avoid_repeat_message()
        if avoid_repeat_message is not None:
            messages.append(avoid_repeat_message)
        append_image_context(messages, common_image_parts)
        self._record_flow_request(event, self._flow_queue_key(event), messages)
        timeout = self._get_model_response_timeout_seconds(event)
        before_model = await self._emit_runtime_event(
            "model.call.before", event, messages=messages, timeout_seconds=timeout
        )
        if before_model.consumed and isinstance(before_model.result, dict):
            response = before_model.result
        else:
            messages = before_model.payload.get("messages", messages)
            try:
                response = await asyncio.wait_for(
                    self._provider.chat(messages),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                event.error = f"AI response timed out after {timeout:.0f}s"
                self._logger.warning(
                    "common 模式模型调用超时",
                    event_id=event.event_id,
                    timeout_seconds=timeout,
                )
                raise
        after_model = await self._emit_runtime_event(
            "model.call.after", event, messages=messages, response=response
        )
        response = after_model.payload.get("response", response)

        self._record_cache_request(messages, response)

        await self._record_context(
            event,
            messages,
            iteration=1,
            stage="common_model_call",
            response=response,
        )

        content = response.get("content", "")

        usage = (response.get("extensions") or {}).get("usage")
        if isinstance(usage, dict) and hasattr(self._provider, "model"):
            try:
                conv_ref = event.conversation_ref
                await get_usage_tracker().record(
                    module="reply_common",
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

        text = content.strip() if isinstance(content, str) else str(content)
        event.generated_text = text
        self._record_debug("reply_generated", event, reply_text=text, response=response)
        return text

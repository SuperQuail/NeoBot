"""ReplySender — formats and sends reply messages with cooldown, segmentation, and image support."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.postprocess import process_reply_text
from neobot_app.utils.media_sender import prepare_image_segment, send_image
from neobot_app.time_context import monotonic_seconds
from neobot_app.statistics.tracker import (
    get_usage_tracker,
)


class ReplySender:
    """Formats reply text into message segments and sends them with cooldown pacing.

    Extracted from ReplyOrchestrator to separate the sending concern from
    scheduling, engine logic, and debug recording.
    """

    def __init__(
        self,
        *,
        adapter: Any,
        file_server: Any,
        config: Any = None,
        bot_name: str = "Bot",
        emoji_service: Any = None,
        markdown_image_converter: Any = None,
        debug_helper: DebugHelper | None = None,
        runtime_events: Any = None,
        io_timeout_seconds: float = 30.0,
        sentence_cooldown_seconds: float = 2.0,
        private_chat_sentence_cooldown_seconds: float = 2.0,
        long_reply_max_length: int = 300,
        long_reply_max_sentence_count: int = 12,
        long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
        enable_ai_reply_regenerate: bool = True,
        provider: Any = None,
        balance_checker: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._file_server = file_server
        self._config = config
        self._bot_name = bot_name
        self._emoji_service = emoji_service
        self._markdown_image_converter = markdown_image_converter
        self._debug_helper = debug_helper or DebugHelper()
        self._runtime_events = runtime_events
        self._io_timeout_seconds = io_timeout_seconds
        self._sentence_cooldown = sentence_cooldown_seconds
        self._private_sentence_cooldown = private_chat_sentence_cooldown_seconds
        self._long_reply_max_length = long_reply_max_length
        self._long_reply_max_sentence_count = long_reply_max_sentence_count
        self._long_reply_fallback_template = long_reply_fallback_template
        self._enable_ai_reply_regenerate = enable_ai_reply_regenerate
        self._provider = provider
        self._balance_checker = balance_checker
        self._logger = logger or NullLogger()
        self._last_sentence_time: dict[str, float] = {}

    # ── public API (also used by engine) ────────────────────────

    async def send_with_timeout(self, conversation_ref: ConversationRef, payload: object) -> Any:
        envelope = RuntimeEnvelope(
            kind="reply_lifecycle",
            stage="message.send.before",
            source="app.reply",
            target=f"{conversation_ref.kind}:{conversation_ref.id}",
            payload={"conversation_ref": conversation_ref, "message": payload},
            context={},
        )
        dispatch = getattr(self._runtime_events, "dispatch_envelope", None)
        if callable(dispatch):
            envelope = await dispatch(envelope)
        if envelope.consumed:
            return envelope.result
        send_payload = envelope.payload.get("message", payload)
        result = await asyncio.wait_for(
            self._adapter.send(conversation_ref, send_payload),
            timeout=self._io_timeout_seconds,
        )
        after = RuntimeEnvelope(
            kind="reply_lifecycle",
            stage="message.send.after",
            source="app.reply",
            target=f"{conversation_ref.kind}:{conversation_ref.id}",
            payload={"conversation_ref": conversation_ref, "message": send_payload, "result": result},
            context={},
        )
        if callable(dispatch):
            await dispatch(after)
        return result

    async def call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await asyncio.wait_for(
            self._adapter.call_api(action, params),
            timeout=self._io_timeout_seconds,
        )

    # ── main send flow ─────────────────────────────────────────

    async def send_reply(
        self,
        event: Any,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
        segments: list[str] | None = None,
        send_original: bool = False,
        images: list[int] | None = None,
        merge_text_with_image: bool = False,
    ) -> None:
        before_postprocess = await self._debug_helper.emit_runtime_event(
            "reply.postprocess.before",
            event,
            text=text,
            segments=segments,
            send_original=send_original,
            images=images,
        )
        text = str(before_postprocess.payload.get("text", text))
        segments = before_postprocess.payload.get("segments", segments)
        send_original = bool(before_postprocess.payload.get("send_original", send_original))
        images = before_postprocess.payload.get("images", images)
        before_send = await self._debug_helper.emit_runtime_event(
            "reply.send.before",
            event,
            text=text,
            segments=segments,
            send_original=send_original,
            images=images,
            reply_to_message_id=reply_to_message_id,
            mention_user_ids=mention_user_ids,
        )
        if before_send.consumed:
            event.send_response = before_send.result
            event.transition(getattr(event.__class__, "COMPLETED", None))
            return
        text = str(before_send.payload.get("text", text))
        segments = before_send.payload.get("segments", segments)
        send_original = bool(before_send.payload.get("send_original", send_original))
        images = before_send.payload.get("images", images)
        reply_to_message_id = before_send.payload.get("reply_to_message_id", reply_to_message_id)
        mention_user_ids = before_send.payload.get("mention_user_ids", mention_user_ids)

        from neobot_app.reply.event import ReplyState

        event.transition(ReplyState.SENDING)
        conv_ref = event.conversation_ref
        if conv_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        send_results: list[object] = []
        formatted_messages: list[list[dict]] = []

        # Phase B: text + first image merged
        if images and merge_text_with_image:
            image_entries = self._resolve_image_entries(images)
            if image_entries:
                first_img = image_entries[0]
                merged = self.build_reply_segments(
                    text=text,
                    conversation_kind=conv_ref.kind,
                    reply_to_message_id=reply_to_message_id,
                    mention_user_ids=mention_user_ids,
                )
                merged.append(prepare_image_segment(self._file_server, first_img.file_path))
                formatted_messages.append(merged)
                send_results.append(await self.send_with_timeout(conv_ref, merged))
                if self._emoji_service:
                    await self._emoji_service.record_usage(images[0])
                for i, entry in enumerate(image_entries[1:], start=1):
                    formatted_messages.append([prepare_image_segment(self._file_server, entry.file_path)])
                    send_results.append(await send_image(self._file_server, self._adapter, conv_ref, entry.file_path))
                    if self._emoji_service:
                        await self._emoji_service.record_usage(images[i])
            event.send_response = send_results[0] if len(send_results) == 1 else send_results
            if conv_ref.kind == "private":
                event.transition(ReplyState.GENERATING)
            else:
                event.transition(ReplyState.COMPLETED)
            self._debug_helper.record(
                "reply_sent",
                event,
                formatted=formatted_messages[0] if len(formatted_messages) == 1 else formatted_messages,
                reply_to_message_id=reply_to_message_id,
            )
            return

        # Phase A: send images first (one by one)
        if images:
            for image_number in images:
                if self._emoji_service is None:
                    continue
                entry = self._emoji_service.get_entry(image_number)
                if entry is None:
                    continue
                formatted_messages.append([prepare_image_segment(self._file_server, entry.file_path)])
                send_results.append(await send_image(self._file_server, self._adapter, conv_ref, entry.file_path))
                await self._emoji_service.record_usage(image_number)

        # long reply → markdown image
        if not images and not send_original and not segments and text.strip():
            if self._can_use_markdown_image(text):
                try:
                    image_path = await self._render_long_reply_as_image(text)
                    formatted_messages.append([prepare_image_segment(self._file_server, image_path)])
                    send_results.append(await self.send_with_timeout(conv_ref, formatted_messages[-1]))
                    event.send_response = send_results[0]
                    if conv_ref.kind == "private":
                        event.transition(ReplyState.GENERATING)
                    else:
                        event.transition(ReplyState.COMPLETED)
                    self._debug_helper.record("reply_sent_as_markdown_image", event, text_len=len(text), image_path=str(image_path))
                    return
                except Exception as exc:
                    self._logger.warning("Markdown 图片渲染失败，降级为文本发送", error=str(exc))

        # Phase C: send text (segmented, with cooldown)
        reply_messages = self._build_reply_messages(
            text,
            segments=segments,
            send_original=send_original,
        )
        after_postprocess = await self._debug_helper.emit_runtime_event(
            "reply.postprocess.after",
            event,
            text=text,
            reply_messages=reply_messages,
            segments=segments,
            send_original=send_original,
        )
        reply_messages = list(after_postprocess.payload.get("reply_messages", reply_messages))
        is_group = conv_ref.kind == "group"
        pipeline_key = f"{conv_ref.kind}:{conv_ref.id}"

        for index, message_text in enumerate(reply_messages):
            if index > 0:
                cooldown = self._sentence_cooldown if is_group else self._private_sentence_cooldown
                last_time = self._last_sentence_time.get(pipeline_key, 0.0)
                elapsed = monotonic_seconds() - last_time
                if elapsed < cooldown:
                    await asyncio.sleep(cooldown - elapsed)

            formatted = self.build_reply_segments(
                text=message_text,
                conversation_kind=conv_ref.kind,
                reply_to_message_id=reply_to_message_id if index == 0 else None,
                mention_user_ids=mention_user_ids if index == 0 else None,
            )
            formatted_messages.append(formatted)
            send_results.append(await self.send_with_timeout(conv_ref, formatted))
            self._last_sentence_time[pipeline_key] = monotonic_seconds()

        event.send_response = send_results[0] if len(send_results) == 1 else send_results
        if conv_ref.kind == "private":
            event.transition(ReplyState.GENERATING)
        else:
            event.transition(ReplyState.COMPLETED)
        self._debug_helper.record(
            "reply_sent",
            event,
            formatted=formatted_messages[0] if len(formatted_messages) == 1 else formatted_messages,
            reply_to_message_id=reply_to_message_id,
        )
        await self._debug_helper.emit_runtime_event(
            "reply.send.after",
            event,
            reply_to_message_id=reply_to_message_id,
            formatted_messages=formatted_messages,
            send_results=send_results,
        )

    # ── self-sent message tracking ──────────────────────────────

    def push_self_sent_message(
        self,
        queue: Any,
        queue_copy: Any,
        queue_key: str,
        conv_ref: ConversationRef,
        text: str,
    ) -> None:
        from neobot_adapter.model.basic import PostMessageMessagesender
        from neobot_adapter.model.message import (
            GroupMessage,
            MessageSegment,
            MessageTypeEnum,
            PrivateMessage,
        )

        bot_qq = 0
        if self._config is not None:
            bot_cfg = getattr(self._config, "bot", None)
            if bot_cfg is not None:
                account = getattr(bot_cfg, "account", 0)
                if account:
                    bot_qq = int(account)

        synthetic_msg_id = -int(time.time() * 1_000_000)
        message_segments = [MessageSegment(type="text", data={"text": text})]
        sender = PostMessageMessagesender(user_id=bot_qq, nickname=self._bot_name)

        if conv_ref.kind == "group":
            msg = GroupMessage(
                message_type=MessageTypeEnum.group,
                message_id=synthetic_msg_id,
                user_id=bot_qq,
                message=message_segments,
                raw_message=text,
                group_id=int(conv_ref.id) if conv_ref.id else 0,
                sender=sender,
            )
        else:
            msg = PrivateMessage(
                message_type=MessageTypeEnum.private,
                message_id=synthetic_msg_id,
                user_id=bot_qq,
                message=message_segments,
                raw_message=text,
                sender=sender,
            )

        queue.push(queue_key, msg)
        queue_copy.push(queue_key, msg)

    # ── message building ────────────────────────────────────────

    @staticmethod
    def build_reply_segments(
        *,
        text: str,
        conversation_kind: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
    ) -> list[dict]:
        segments: list[dict] = []
        if mention_user_ids and conversation_kind == "group":
            for qq in mention_user_ids:
                segments.append({
                    "type": "at",
                    "data": {"qq": str(qq)},
                })

        if reply_to_message_id is not None:
            segments.append({"type": "reply", "data": {"id": str(reply_to_message_id)}})

        segments.append({"type": "text", "data": {"text": text}})
        return segments

    # ── internals ───────────────────────────────────────────────

    def _build_reply_messages(
        self,
        text: str,
        *,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> list[str]:
        if send_original:
            return [text.strip()]
        if segments:
            cleaned = [s.strip() for s in segments if s.strip()]
            if cleaned:
                return cleaned
        result = process_reply_text(
            text,
            bot_name=self._bot_name,
            fallback_template=self._long_reply_fallback_template,
            max_length=self._long_reply_max_length,
            max_sentence_count=self._long_reply_max_sentence_count,
        )
        return result.messages

    def _can_use_markdown_image(self, text: str) -> bool:
        if self._markdown_image_converter is None:
            return False
        result = process_reply_text(
            text,
            bot_name=self._bot_name,
            fallback_template=self._long_reply_fallback_template,
            max_length=self._long_reply_max_length,
            max_sentence_count=self._long_reply_max_sentence_count,
        )
        return result.fallback_used

    async def _render_long_reply_as_image(self, text: str) -> Path:
        return await self._markdown_image_converter.convert(text)

    def _resolve_image_entries(self, image_numbers: list[int]) -> list[Any]:
        if self._emoji_service is None:
            return []
        entries: list[Any] = []
        for number in image_numbers:
            entry = self._emoji_service.get_entry(number)
            if entry is not None:
                entries.append(entry)
        return entries

"""ReplySender —— 负责格式化并发送回复消息，支持冷却、分段与图片。"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope
from neobot_contracts.time_context import now_utc

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyState
from neobot_app.reply.output_guard import clean_segments, clean_text, should_drop
from neobot_app.reply.postprocess import process_reply_text
from neobot_app.utils.media_sender import prepare_image_segment, send_image
from neobot_app.time_context import monotonic_seconds

_MARKDOWN_RENDER_TIMEOUT_SECONDS = 60.0

#: Markdown 转图片的队列索引里附带的来源标注长度（字符）。
_MARKDOWN_INDEX_SOURCE_CHARS = 40


@dataclass
class SelfSentSink:
    """Bot 自身发言的入队去处（源队列 + 管线快照 + 队列键）。

    `ReplySender` 的所有真实发送点都用它把「刚才真发出去的东西」写回队列，
    这样回复管线因寿命耗尽 / 挂起恢复 / 软重启而重新组装提示词时，
    assistant 块不会凭空消失（fix(2) 的统一入队通道）。
    """

    queue: Any = None
    snapshot: Any = None
    queue_key: str = ""

    @property
    def usable(self) -> bool:
        return self.queue is not None and bool(self.queue_key)


#: Bot 自身消息落盘用的默认 UoW 工厂（惰性创建；见 _default_self_sent_uow_factory）。
_DEFAULT_SELF_SENT_UOW_FACTORY: Any = None
_DEFAULT_SELF_SENT_UOW_FACTORY_RESOLVED = False


def self_sent_event_id(synthetic_msg_id: int) -> str:
    """Bot 自身消息落库用的 event_id。

    合成消息 id 取负的微秒时间戳（见 push_self_sent_message），天然唯一，
    且与后端返回的真实 message_id 不在同一套标识空间里，因此不会与
    用户消息的 event_id 冲突。
    """
    return f"self:{synthetic_msg_id}"


def _default_self_sent_uow_factory() -> Any:
    """惰性创建写入 Bot 自身消息用的 UoW 工厂。

    ReplySender 由 orchestrator 构建，拿不到 bootstrap 的共享 uow_factory；
    这里按需打开同一份 SQLite 文件（WAL + busy_timeout，与主库同源），
    复用既有 MessageData 表与仓库，不新建表、不引入新依赖。
    解析结果（含失败）只结算一次：失败后不再重试，避免每条回复都付出
    建引擎/建连接的异常成本。
    """
    global _DEFAULT_SELF_SENT_UOW_FACTORY, _DEFAULT_SELF_SENT_UOW_FACTORY_RESOLVED
    if _DEFAULT_SELF_SENT_UOW_FACTORY_RESOLVED:
        return _DEFAULT_SELF_SENT_UOW_FACTORY
    _DEFAULT_SELF_SENT_UOW_FACTORY_RESOLVED = True
    try:
        from neobot_app.assembly.storage import build_storage
        from neobot_app.core import DATA_DIR

        _engine, factory = build_storage(db_path=DATA_DIR / "neobot.db")
    except Exception:
        _DEFAULT_SELF_SENT_UOW_FACTORY = None
        return None
    _DEFAULT_SELF_SENT_UOW_FACTORY = factory
    return factory


class ReplySender:
    """将回复文本格式化为消息分段，并按冷却节奏发送。

    从 ReplyOrchestrator 中抽取而来，以便将发送职责与调度、
    引擎逻辑和调试记录相分离。
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
        self_sent_uow_factory: Any = None,
        image_registrar: Any = None,
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
        #: Bot 自身消息落盘用的 UoW 工厂；None 时惰性回退到默认存储（见模块顶部）。
        self._self_sent_uow_factory = self_sent_uow_factory
        #: 持有未完成的落盘任务引用，避免 asyncio 任务被 GC 提前回收。
        self._self_sent_persist_tasks: set[asyncio.Task[None]] = set()
        #: 把「本地文件 → temp 图库(tmp_xxx)」的最小登记入口（
        #: CreatorImageService.register_local_image）。缺失时索引退化为 file: 路径。
        self._image_registrar = image_registrar
        #: 自身发言合成消息 id 的高水位（严格递减，避免同一微秒内多条撞号）。
        self._last_self_sent_id = 0

    # ── 状态流转 ────────────────────────────────────────────────

    @staticmethod
    def _enter_sending(event: Any) -> None:
        """进入发送态；群聊已 COMPLETED 时允许再次发送。

        模型经常在同一轮里连续调用多次 send_reply。群聊首次发送后事件已经是
        终态 COMPLETED，第二次再 transition(SENDING) 会抛「非法状态转换」，
        结果是第二条消息被吞掉、模型还被告知工具失败，并为了补救再多跑一轮。

        只对 COMPLETED 放开：其它非法前置状态（PENDING/BUILDING_PROMPT）以及
        FAILED/CANCELLED 仍照旧抛错，避免把真正的状态机缺陷一起吞掉。
        """
        if event.state is ReplyState.COMPLETED:
            return
        event.transition(ReplyState.SENDING)

    @staticmethod
    def _leave_sending(event: Any, conversation_kind: str) -> None:
        """发送完成后回到群聊终态 / 私聊继续生成；非 SENDING 时保持不变。"""
        if event.state is not ReplyState.SENDING:
            return
        target = (
            ReplyState.GENERATING
            if conversation_kind == "private"
            else ReplyState.COMPLETED
        )
        try:
            event.transition(target)
        except RuntimeError:
            pass

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
        # 不等 echo 回执：请求写上线即视为发送成功。等待回执会把 agent 循环
        # 卡在上游往返上，而实测发送几乎不会失败（失败由连接状态与心跳发现）。
        result = await asyncio.wait_for(
            self._adapter.send(conversation_ref, send_payload, wait_response=False),
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
        self_sent: SelfSentSink | None = None,
        sender_names: list[str] | None = None,
    ) -> bool:
        """发送一段回复；返回是否真的发出了内容。

        返回 False 只出现在「清洗后什么都不剩」这一种情况：整条都是系统标注残渣
        （或未闭合的思维链），此时宁可不发，也不把空消息/脏前缀发到群里。
        调用方（工具层）据此告诉模型重新生成正文，而不是误报「已发送」。
        """
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
        # 输出兜底清洗：不动 text/segments 之外的东西，且这里的 text 就是
        # self-sent 写回历史的文本（见下方 _emit_self_sent_text），因此正反馈
        # 的源头也在这里被切断（详见 reply/output_guard.py）。
        text, segments = self._sanitize_outgoing(text, segments, sender_names=sender_names)
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
            try:
                event.transition(ReplyState.COMPLETED)
            except RuntimeError:
                pass
            return True
        text = str(before_send.payload.get("text", text))
        segments = before_send.payload.get("segments", segments)
        send_original = bool(before_send.payload.get("send_original", send_original))
        images = before_send.payload.get("images", images)
        reply_to_message_id = before_send.payload.get("reply_to_message_id", reply_to_message_id)
        mention_user_ids = before_send.payload.get("mention_user_ids", mention_user_ids)
        # 插件可能在 reply.send.before 里改写文本，清洗必须在改写之后再做一次，
        # 否则「最后一道兜底」会被插件绕过。清洗幂等，重复调用无副作用。
        text, segments = self._sanitize_outgoing(text, segments, sender_names=sender_names)
        if not (str(text or "").strip() or segments or images):
            self._logger.warning(
                "回复清洗后为空，已丢弃发送",
                conversation=f"{event.conversation_ref.kind}:{event.conversation_ref.id}"
                if event.conversation_ref is not None
                else "",
            )
            self._leave_sending(event, event.conversation_ref.kind if event.conversation_ref else "")
            return False

        self._enter_sending(event)
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
                # 真实发送结果入队：文本与图片分别按真实形态记录（图片为索引）
                self._emit_self_sent_text(self_sent, conv_ref, text)
                await self._emit_self_sent_image(self_sent, conv_ref, first_img.file_path)
                if self._emoji_service:
                    await self._emoji_service.record_usage(images[0])
                for i, entry in enumerate(image_entries[1:], start=1):
                    formatted_messages.append([prepare_image_segment(self._file_server, entry.file_path)])
                    send_results.append(await send_image(
                        self._file_server, self._adapter, conv_ref, entry.file_path,
                        wait_response=False,
                    ))
                    await self._emit_self_sent_image(self_sent, conv_ref, entry.file_path)
                    if self._emoji_service:
                        await self._emoji_service.record_usage(images[i])
            event.send_response = send_results[0] if len(send_results) == 1 else send_results
            self._leave_sending(event, conv_ref.kind)
            self._debug_helper.record(
                "reply_sent",
                event,
                formatted=formatted_messages[0] if len(formatted_messages) == 1 else formatted_messages,
                reply_to_message_id=reply_to_message_id,
            )
            return True

        # Phase A: send images first (one by one)
        if images:
            for image_number in images:
                if self._emoji_service is None:
                    continue
                entry = self._emoji_service.get_entry(image_number)
                if entry is None:
                    continue
                formatted_messages.append([prepare_image_segment(self._file_server, entry.file_path)])
                send_results.append(await send_image(
                    self._file_server, self._adapter, conv_ref, entry.file_path,
                    wait_response=False,
                ))
                await self._emit_self_sent_image(self_sent, conv_ref, entry.file_path)
                await self._emoji_service.record_usage(image_number)

        # long reply → markdown image
        if not images and not send_original and not segments and text.strip():
            if self._can_use_markdown_image(text):
                try:
                    image_path = await asyncio.wait_for(
                        self._render_long_reply_as_image(text),
                        timeout=_MARKDOWN_RENDER_TIMEOUT_SECONDS,
                    )
                    formatted_messages.append([prepare_image_segment(self._file_server, image_path)])
                    send_results.append(await self.send_with_timeout(conv_ref, formatted_messages[-1]))
                    await self._emit_self_sent_image(
                        self_sent, conv_ref, image_path,
                        kind="markdown",
                        source_note=text,
                    )
                    event.send_response = send_results[0]
                    self._leave_sending(event, conv_ref.kind)
                    self._debug_helper.record("reply_sent_as_markdown_image", event, text_len=len(text), image_path=str(image_path))
                    return True
                except Exception as exc:
                    self._logger.warning("Markdown 图片渲染失败，降级为文本发送", error=str(exc))

        # Phase C: send text (segmented, with cooldown)
        # 已经发过图片、且清洗后没有任何文字可发时，直接收尾：
        # 不要为了「走完流程」再发一条空文本消息（审查实测：空 data.text 会真的上线）。
        if images and not str(text or "").strip() and not segments:
            event.send_response = (
                send_results[0] if len(send_results) == 1 else send_results
            )
            self._leave_sending(event, conv_ref.kind)
            self._debug_helper.record(
                "reply_sent",
                event,
                formatted=formatted_messages,
                reply_to_message_id=reply_to_message_id,
            )
            return True
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
        # 插件也能在 reply.postprocess.after 改写逐条内容，而这一步在清洗之后：
        # 再清一遍，保证「最后一道兜底」不被插件绕过（清洗幂等，重复调用无副作用）。
        reply_messages = clean_segments(
            reply_messages, known_sender_names=self._sender_names(sender_names)
        )
        if not reply_messages and not images:
            self._logger.warning(
                "回复清洗后为空，已丢弃发送",
                conversation=f"{conv_ref.kind}:{conv_ref.id}",
            )
            self._leave_sending(event, conv_ref.kind)
            return False
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
            # 逐条按「真正发到 QQ 的那句文本」入队：重建后模型知道自己分几句说了什么
            self._emit_self_sent_text(self_sent, conv_ref, message_text)
            self._last_sentence_time[pipeline_key] = monotonic_seconds()

        event.send_response = send_results[0] if len(send_results) == 1 else send_results
        self._leave_sending(event, conv_ref.kind)
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
        return True

    # ── self-sent message tracking ──────────────────────────────
    #
    # 统一入队通道：所有「真实发出去了」的发送类型都经 _emit_self_sent* 写回队列，
    # 不再由各工具 handler 手工补记（手工补记必然会漏，且拿不到真实发送结果）。

    def push_self_sent_message(
        self,
        queue: Any,
        queue_copy: Any,
        queue_key: str,
        conv_ref: ConversationRef,
        text: str,
    ) -> asyncio.Task[None] | None:
        """（兼容入口）把 Bot 自身的一段文本发言入队并异步落盘。

        新代码统一走 send_reply 的 self_sent 通道；此方法保留给既有调用方与测试。
        """
        return self._emit_self_sent(
            SelfSentSink(queue=queue, snapshot=queue_copy, queue_key=queue_key),
            conv_ref,
            text,
        )

    def record_self_sent_text(
        self, sink: SelfSentSink | None, conv_ref: ConversationRef, text: str
    ) -> asyncio.Task[None] | None:
        """把一段真实发出的文本入队并落盘（供工具 handler 复用统一通道）。"""
        return self._emit_self_sent(sink, conv_ref, text)

    async def record_self_sent_image(
        self,
        sink: SelfSentSink | None,
        conv_ref: ConversationRef,
        file_path: Any,
        *,
        kind: str = "image",
        source_note: str = "",
    ) -> asyncio.Task[None] | None:
        """把一张真实发出的图片按「索引」入队（产物进 temp 图库，队列只留引用）。

        索引里同时写 temp 图库 id（可被 image_context 再次取回查看）与 file: 路径
        （图库清理后仍能定位产物），不写图片内容 ⇒ 不占上下文窗口。
        """
        if sink is None or not sink.usable:
            return None
        index_text = await self._build_image_index_text(
            file_path, kind=kind, source_note=source_note
        )
        return self._emit_self_sent(sink, conv_ref, index_text)

    async def record_self_sent_voice(
        self,
        sink: SelfSentSink | None,
        conv_ref: ConversationRef,
        text: str,
        *,
        file_hint: str = "",
    ) -> asyncio.Task[None] | None:
        """把一条真实发出的语音入队：暂无解析能力 ⇒ 原始文本 + 音频文件索引。"""
        if sink is None or not sink.usable:
            return None
        hint = str(file_hint or "").strip()
        if hint and not hint.startswith("file:"):
            hint = f"file:{hint}"
        head = f"[语音:{hint}]" if hint else "[语音]"
        spoken = str(text or "").strip()
        return self._emit_self_sent(sink, conv_ref, f"{head} {spoken}" if spoken else head)

    def _next_self_sent_message_id(self) -> int:
        """生成严格递减的负数合成消息 id（与后端真实 id 不同源，天然不撞号）。"""
        candidate = -int(time.time() * 1_000_000)
        if candidate >= self._last_self_sent_id:
            candidate = self._last_self_sent_id - 1
        self._last_self_sent_id = candidate
        return candidate

    def _build_self_sent_message(
        self, conv_ref: ConversationRef, text: str, synthetic_msg_id: int
    ) -> Any:
        """把一段 Bot 自身发言构造为可入队的消息对象。"""
        from neobot_adapter.model.basic import PostMessageMessagesender
        from neobot_adapter.model.message import (
            GroupMessage,
            MessageSegment,
            MessageTypeEnum,
            PrivateMessage,
        )

        bot_qq = self._resolve_bot_account()
        message_segments = [MessageSegment(type="text", data={"text": text})]
        sender = PostMessageMessagesender(user_id=bot_qq, nickname=self._bot_name)

        if conv_ref.kind == "group":
            return GroupMessage(
                message_type=MessageTypeEnum.group,
                message_id=synthetic_msg_id,
                user_id=bot_qq,
                message=message_segments,
                raw_message=text,
                group_id=int(conv_ref.id) if conv_ref.id else 0,
                sender=sender,
            )
        return PrivateMessage(
            message_type=MessageTypeEnum.private,
            message_id=synthetic_msg_id,
            user_id=bot_qq,
            message=message_segments,
            raw_message=text,
            sender=sender,
        )

    def _emit_self_sent(
        self, sink: SelfSentSink | None, conv_ref: ConversationRef, text: str
    ) -> asyncio.Task[None] | None:
        """唯一入队点：写回源队列 + 管线快照，并异步落盘一份（无独立历史上限）。"""
        if sink is None or not sink.usable or not str(text or "").strip():
            return None
        synthetic_msg_id = self._next_self_sent_message_id()
        try:
            message = self._build_self_sent_message(conv_ref, text, synthetic_msg_id)
            sink.queue.push(sink.queue_key, message)
            if sink.snapshot is not None and sink.snapshot is not sink.queue:
                sink.snapshot.push(sink.queue_key, message)
        except Exception as exc:
            # 入队失败绝不能反噬发送路径：宁可少一条上下文，也不能让回复发不出去。
            self._logger.warning("Bot 自身发言入队失败（已忽略）", error=str(exc))
            return None
        return self._schedule_self_sent_persist(conv_ref, text, synthetic_msg_id)

    def _emit_self_sent_text(
        self, sink: SelfSentSink | None, conv_ref: ConversationRef, text: str
    ) -> asyncio.Task[None] | None:
        return self._emit_self_sent(sink, conv_ref, text)

    async def _emit_self_sent_image(
        self,
        sink: SelfSentSink | None,
        conv_ref: ConversationRef,
        file_path: Any,
        *,
        kind: str = "image",
        source_note: str = "",
    ) -> asyncio.Task[None] | None:
        return await self.record_self_sent_image(
            sink, conv_ref, file_path, kind=kind, source_note=source_note
        )

    async def _build_image_index_text(
        self, file_path: Any, *, kind: str, source_note: str
    ) -> str:
        label = "Markdown图片" if kind == "markdown" else "图片"
        path = Path(str(file_path))
        image_id = await self._register_temp_image(path)
        ref = f"{image_id} file:{path}" if image_id else f"file:{path}"
        text = f"[{label}:{ref}]"
        note = " ".join(str(source_note or "").split())
        if kind == "markdown" and note:
            text = f"{text} {note[:_MARKDOWN_INDEX_SOURCE_CHARS]}"
        return text

    async def _register_temp_image(self, file_path: Path) -> str | None:
        """把本地图片登记进 temp 图库（TMP_SOURCE → tmp_xxx）。

        失败时返回 None，调用方退化为 file: 索引；绝不影响发送路径。
        """
        registrar = self._image_registrar
        if registrar is None:
            return None
        try:
            if not file_path.is_file():
                return None
            result = registrar(file_path)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            self._logger.warning(
                "Bot 自发图片登记 temp 图库失败（已降级为 file: 索引）", error=str(exc)
            )
            return None
        image_id = getattr(result, "image_id", None)
        if image_id is None and isinstance(result, str):
            image_id = result
        return str(image_id) if image_id else None

    def _resolve_bot_account(self) -> int:
        """读取配置里的机器人 QQ 号（缺失时返回 0）。"""
        if self._config is None:
            return 0
        bot_cfg = getattr(self._config, "bot", None)
        if bot_cfg is None:
            return 0
        account = getattr(bot_cfg, "account", 0)
        return int(account) if account else 0

    def _schedule_self_sent_persist(
        self, conv_ref: ConversationRef, text: str, synthetic_msg_id: int
    ) -> asyncio.Task[None] | None:
        """把落盘调度成后台任务：发送路径绝不等数据库。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        task = loop.create_task(
            self.persist_self_sent_message(
                conv_ref, text, synthetic_msg_id=synthetic_msg_id
            )
        )
        self._self_sent_persist_tasks.add(task)
        task.add_done_callback(self._self_sent_persist_tasks.discard)
        return task

    async def persist_self_sent_message(
        self,
        conv_ref: ConversationRef,
        text: str,
        *,
        synthetic_msg_id: int | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """把 Bot 自己发出的消息写入 MessageData（软重启后据此补齐 assistant 块）。

        复用既有 MessageData 表与仓库，不新建表；event_id 形如 self:<合成消息id>，
        与后端真实 message_id 不冲突。本方法永不抛异常：任何失败（无 UoW、
        无表、写冲突）都只记日志，绝不能反噬发送路径。
        """
        if not text or not text.strip():
            return
        try:
            factory = self._self_sent_uow_factory or _default_self_sent_uow_factory()
            if factory is None:
                return
            message_id = (
                synthetic_msg_id
                if synthetic_msg_id is not None
                else -int(time.time() * 1_000_000)
            )
            async with factory() as uow:
                await uow.messages.save_message(
                    IncomingMessage(
                        event_id=self_sent_event_id(message_id),
                        conversation=conv_ref,
                        sender_id=str(self._resolve_bot_account()),
                        sender_name=self._bot_name,
                        text=text,
                        occurred_at=occurred_at or now_utc(),
                    )
                )
                await uow.commit()
        except Exception as exc:
            self._logger.warning("Bot 自身消息落盘失败（已忽略）", error=str(exc))

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

    def _sanitize_outgoing(
        self,
        text: str,
        segments: list[str] | None,
        *,
        sender_names: list[str] | None = None,
    ) -> tuple[str, list[str] | None]:
        """发送前的统一清洗入口（text 与 segments 两条路径共用同一套规则）。

        `segments` 路径此前完全跳过清洗（只有 text 路径跑 process_reply_text），
        这里把「前缀标注 / <think> 标签」的清洗补齐到两条路径上：同一个模型输出
        不该因为走哪条路径而有不同的清洗结果。

        text 与 segments 都清洗后为空时，text 退化为空串 —— 由调用方跳过发送，
        绝不把一段空消息当作「已回复」发出去。
        """
        names = self._sender_names(sender_names)
        # text 与 segments 一律都清洗：segments 存活时 text 也不能放过 ——
        # send_original=true 会让 _build_reply_messages 选中 text，脏 text 会直通线上。
        cleaned_text = self._clean_text_only(text, names)
        if segments:
            kept = clean_segments(segments, known_sender_names=names)
            if kept:
                return cleaned_text, kept
            if cleaned_text:
                # segments 全是残渣时只保留 text（已清洗），而不是发出空消息
                return cleaned_text, None
            return "", None
        return cleaned_text, segments

    @staticmethod
    def _clean_text_only(text: str, sender_names: list[str]) -> str:
        original = str(text or "")
        cleaned = clean_text(original, known_sender_names=sender_names)
        if should_drop(original, cleaned, known_sender_names=sender_names):
            return ""
        return cleaned

    def _sender_names(self, extra: list[str] | None) -> list[str]:
        """收集「我自己可能长什么样」的名字集合（配置昵称 + 队列里用过的显示名）。"""
        names: list[str] = []
        seen: set[str] = set()
        for value in [self._bot_name, *list(extra or [])]:
            name = str(value or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def _build_reply_messages(
        self,
        text: str,
        *,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> list[str]:
        if send_original:
            # text 被清洗成空时不要返回 [""]（那会发出一条空消息），
            # 退回 segments / 交由调用方判空跳过（见 send_reply 的空判）。
            stripped = text.strip()
            if stripped:
                return [stripped]
            if segments:
                return [s.strip() for s in segments if s.strip()]
            return []
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

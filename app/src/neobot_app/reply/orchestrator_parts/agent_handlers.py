"""agent 工具回调：把模型工具调用转成真实回复动作。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from neobot_app.reply.event import ReplyState
from neobot_app.reply.postprocess import ReplySplitPreview
from neobot_app.utils.media_sender import prepare_image_segment, send_image
from ._runtime import asyncio
from .agent_state import AgentLoopState
from .sending import _segment_file_hint

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.reply.event import ReplyEvent


class AgentHandlersMixin:

    async def _agent_cancel_handler(
        self, state: AgentLoopState, event: ReplyEvent, reason: str | None = None
    ) -> None:
        state.cancelled = True
        event.error = reason or "agent 主动取消回复"
        if not event.is_terminal:
            event.transition(ReplyState.CANCELLED)
        self._logger.debug(
            "Agent主动取消回复",
            event_id=event.event_id,
            reason=reason,
        )

    async def _agent_send_reply_handler(
        self,
        state: AgentLoopState,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering,
        text: str,
        reply_to: int | None = None,
        mention: list[int] | None = None,
        segments: list[str] | None = None,
        send_original: bool = False,
        images: list[int] | None = None,
        split_preview: ReplySplitPreview | None = None,
    ) -> bool:
        """发送回复；返回是否真的发出了内容（False ⇒ 工具层提示模型重新生成）。

        只有真的发出去了才把 round 标记为「已回复」：清洗后为空时不标记，
        这样主循环不会在模型还没说出正文时就退出（否则整轮静默结束）。
        """
        event.generated_text = text
        before_message_id = queue.get_last_message_id(queue_key)
        sink = self._self_sent_sink(queue, queue_copy, queue_key)
        # 发送前清洗只使用当前会话的发送者标签（含快照中的历史标签）。
        sender_names = self._known_sender_names(queue, queue_copy, queue_key=queue_key)
        if reply_to is not None:
            event.reply_to_number = reply_to
            msg_id = numbering.get_message_id(reply_to)
            delivered = await self._send_reply(
                event,
                text,
                reply_to_message_id=msg_id,
                mention_user_ids=mention,
                segments=segments,
                send_original=send_original,
                images=images,
                self_sent=sink,
                sender_names=sender_names,
                **({"split_preview": split_preview} if split_preview is not None else {}),
            )
        else:
            delivered = await self._send_reply(
                event,
                text,
                mention_user_ids=mention,
                segments=segments,
                send_original=send_original,
                images=images,
                self_sent=sink,
                sender_names=sender_names,
                **({"split_preview": split_preview} if split_preview is not None else {}),
            )
        if delivered is not False:
            state.reply_sent = True
            self._record_reply_delivered(
                event, queue, queue_key, before_message_id=before_message_id
            )
        return delivered

    async def _agent_send_emoji_handler(
        self,
        state: AgentLoopState,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        number: int,
    ) -> None:
        if self._emoji_service is None:
            return
        entry = self._emoji_service.get_entry(number)
        if entry is None:
            return
        # 表情包单独作为一条消息发送，不与要说的话合并
        segments = [prepare_image_segment(self._file_server, entry.file_path)]
        emoji_conv = event.conversation_ref
        before_message_id = queue.get_last_message_id(queue_key)
        delivered = await self._send_with_timeout(emoji_conv, segments)
        # 表情包发出去了就算「已回复」：否则 emoji-only 轮次会被判 CANCELLED，
        # 回复冷却与 last_reply_position 都不推进
        if delivered is not False:
            state.reply_sent = True
            event.send_response = delivered
            self._record_reply_delivered(
                event, queue, queue_key, before_message_id=before_message_id
            )
        # 表情包也是「真实发出去了」的图片：按真实形态入队
        if emoji_conv is not None:
            emoji_sink = self._self_sent_sink(queue, queue_copy, queue_key)
            await self._sender.record_self_sent_image(
                emoji_sink, emoji_conv, entry.file_path
            )
        # 记录表情包使用次数
        await self._emoji_service.record_usage(number)

    async def _agent_wait_handler(
        self,
        state: AgentLoopState,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering,
        seconds: int = 20,
    ) -> str:
        max_wait = self._get_max_wait_seconds()
        wait_time = max(1, min(seconds, max_wait))
        await asyncio.sleep(wait_time)
        # 对比基准必须在收集前取：_collect_new_entries 会把新条目灌进快照，
        # 收集后再取会让重名提示的「新发送者」恒出现在 previous 里而不触发
        entries_before_wait = queue_copy.entries(queue_key)
        new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
        if new_entries:
            # 睡眠拦截:睡眠中被@则唤醒并注入唤醒提示词,其余消息忽略
            if self._sleeping():
                if self._entries_have_at_mention(new_entries, queue_key=queue_key):
                    wake_prompt = self._wake_from_sleep() or ""
                    self._logger.info(
                        "睡眠中 wait 工具被@唤醒",
                        queue_key=queue_key,
                    )
                    return (
                        f"等待了 {wait_time} 秒,期间被@叫醒了。"
                        f"{wake_prompt}"
                    )
                self._logger.info(
                    "睡眠中 wait 工具忽略新消息",
                    queue_key=queue_key,
                    count=len(new_entries),
                )
                return (
                    f"等待了 {wait_time} 秒,期间收到新消息,"
                    "但 Bot 正在睡觉,暂不处理。"
                )
            new_text = numbering.apply_new(
                new_entries,
                queue_copy,
                context_entries=queue_copy.entries(queue_key),
                previous_entries=entries_before_wait,
            )
            # 刷新对比基准，下次 wait 的重名提示不基于过期快照
            state.previous_entries = queue_copy.entries(queue_key)
            if new_text:
                if state.is_group:
                    member_block = await self._render_new_member_block(
                        new_entries, state.rendered_user_ids
                    )
                    if member_block:
                        new_text += f"\n\n{member_block}"
                return (
                    f"等待了 {wait_time} 秒，期间收到新消息：\n{new_text}"
                )
        return f"等待了 {wait_time} 秒，期间没有收到新消息。"

    async def _agent_react_emoji_handler(
        self,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering,
        message_number: int,
        emoji_id: int,
    ) -> str:
        from neobot_adapter.request.message import set_msg_emoji_like
        from neobot_app.message.queue import ReactionEntry

        msg_id = numbering.get_message_id(message_number)
        if msg_id is None:
            return f"错误：消息编号 {message_number} 不存在于当前上下文中"

        await asyncio.wait_for(
            set_msg_emoji_like(message_id=msg_id, emoji_id=emoji_id),
            timeout=self._get_io_timeout_seconds(),
        )

        # 获取操作者名称（bot 自身）
        bot_name = (
            getattr(self._config.bot, "nick_name", "Bot") if self._config else "Bot"
        )

        reaction = ReactionEntry(
            target_message_id=msg_id,
            emoji_id=emoji_id,
            operator_user_id=getattr(self._config.bot, "account", 0)
            if self._config
            else 0,
            operator_name=bot_name,
        )
        # 同时推送到源队列和快照队列
        queue.push_reaction(queue_key, reaction)
        queue_copy.push_reaction(queue_key, reaction)

        from neobot_app.emoji.mapping import lookup_emoji

        emoji_info = lookup_emoji(emoji_id)
        emoji_label = emoji_info[0] if emoji_info else f"#{emoji_id}"
        return f"已对消息{message_number}做出表情回应:{emoji_label}"

    def _agent_search_emoji_handler(self, keyword: str) -> str:
        from neobot_app.emoji.mapping import search_emoji

        results = search_emoji(keyword)
        if not results:
            return f"未找到与「{keyword}」相关的QQ表情"
        lines = [f"搜索「{keyword}」的结果："]
        for item in results:
            lines.append(f"  ID {item['id']}: {item['name']} ({item['hint']})")
        return "\n".join(lines)

    async def _agent_speak_handler(
        self,
        state: AgentLoopState,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        text: str,
    ) -> str:
        if self._tts_service is None:
            return "错误：TTS 服务未配置"
        segment = await asyncio.wait_for(
            self._tts_service.synthesize_segment(text),
            timeout=self._get_io_timeout_seconds(),
        )
        speak_conv = event.conversation_ref
        before_message_id = queue.get_last_message_id(queue_key)
        delivered = await self._send_with_timeout(speak_conv, [segment])
        # 与 send_reply 同语义：语音真实发出即视为已回复
        if delivered is not False:
            state.reply_sent = True
            event.send_response = delivered
            self._record_reply_delivered(
                event, queue, queue_key, before_message_id=before_message_id
            )
        # 语音入队：保留发送时的原始文本 + 音频文件索引
        # （暂无语音解析能力，文本原样留着；文件索引供将来取用）
        if speak_conv is not None:
            await self._sender.record_self_sent_voice(
                self._self_sent_sink(queue, queue_copy, queue_key),
                speak_conv,
                text,
                file_hint=_segment_file_hint(segment),
            )
        return f"已发送语音消息，内容：{text[:50]}{'...' if len(text) > 50 else ''}"

    async def _agent_poke_user_handler(
        self, conv_kind: str, conv_id: str, user_id: int
    ) -> str:
        if conv_kind == "group":
            result = await self._call_api_with_timeout(
                "group_poke",
                {
                    "group_id": int(conv_id),
                    "user_id": user_id,
                },
            )
            return (
                f"已在群{conv_id}中戳一戳 QQ:{user_id}"
                if self._api_succeeded(result)
                else f"群戳一戳失败: {result}"
            )
        else:
            result = await self._call_api_with_timeout(
                "friend_poke",
                {
                    "user_id": user_id,
                },
            )
            return (
                f"已戳一戳好友 QQ:{user_id}"
                if self._api_succeeded(result)
                else f"好友戳一戳失败: {result}"
            )

    async def _agent_send_long_reply_handler(
        self,
        state: AgentLoopState,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering,
        image_path: str,
        caption: str = "",
        reply_to: int | None = None,
        mention: list[int] | None = None,
        markdown: str = "",
    ) -> None:
        conv_ref = event.conversation_ref
        before_message_id = queue.get_last_message_id(queue_key)
        # 解析消息编号 -> 实际 message_id
        reply_to_message_id = None
        if reply_to is not None:
            reply_to_message_id = numbering.get_message_id(reply_to)
        long_reply_sink = (
            self._self_sent_sink(queue, queue_copy, queue_key)
            if conv_ref is not None
            else None
        )
        # 发送说明文字（如果有）
        caption_delivered = True
        if caption.strip():
            caption_segs = self._build_reply_segments(
                text=caption.strip(),
                conversation_kind=conv_ref.kind if conv_ref else "",
                reply_to_message_id=reply_to_message_id,
                mention_user_ids=mention,
            )
            caption_delivered = await self._send_with_timeout(conv_ref, caption_segs)
            if conv_ref is not None and caption_delivered is not False:
                self._sender.record_self_sent_text(
                    long_reply_sink, conv_ref, caption.strip()
                )
        # 发送图片（不附带引用，图片单独发送）
        image_delivered = await send_image(
            self._file_server, self._adapter, conv_ref, Path(image_path),
            wait_response=False,
        )
        # 图片入队为「索引」：产物登记进 temp 图库（tmp_xxx）+ file 路径兜底，
        # Markdown 原文只留前 N 字来源标注（全文不再重复注入上下文）。
        if conv_ref is not None:
            await self._sender.record_self_sent_image(
                long_reply_sink,
                conv_ref,
                Path(image_path),
                kind="markdown",
                source_note=markdown,
            )
        if image_delivered is not False or caption_delivered is not False:
            state.reply_sent = True
            event.send_response = (
                image_delivered if image_delivered is not False else caption_delivered
            )
            self._record_reply_delivered(
                event, queue, queue_key, before_message_id=before_message_id
            )

    def _append_current_time_block(
        self, state: AgentLoopState, messages: list[dict]
    ) -> None:
        if state.time_block_full_sent:
            block = self._build_short_time_message()
            if block is None:
                # 短时间戳分区关闭/缺失时回退完整块,保证时间仍在推进
                block = self._build_current_time_message()
        else:
            block = self._build_current_time_message()
            if block is not None:
                state.time_block_full_sent = True
        if block is not None:
            messages.append(block)

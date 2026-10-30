"""回复发送、媒体发送与发送者标签。"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from neobot_contracts.models import ConversationRef
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.postprocess import ReplySplitPreview
from neobot_app.reply.sender import ReplySender, SelfSentSink

class SendingMixin:
    async def _send_with_timeout(
        self, conversation_ref: ConversationRef, payload: object
    ) -> Any:
        return await self._sender.send_with_timeout(conversation_ref, payload)
    async def _call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await self._sender.call_api_with_timeout(action, params)
    @staticmethod
    def _known_sender_names(*queues: Any, queue_key: str | None = None) -> list[str]:
        """收集本会话出现过的全部发送者显示名（昵称 / 群名片）。

        发送前清洗要认出模型从历史里学来的 `编号: 名字: ` 前缀，而前缀里的名字
        **既可能是它自己，也可能是它续写出来的别人**（报告主症状
        `215: 贝拉: 要抱抱` 就是别人），所以这里收全部发送者，不只收 Bot 自己。
        Bot 自己的配置昵称由 sender 侧另行补齐。
        """
        names: list[str] = []
        seen: set[str] = set()
        for queue in queues:
            getter = getattr(queue, "sender_labels", None)
            if not callable(getter):
                continue
            try:
                values = getter() if queue_key is None else getter(queue_key=queue_key)
            except Exception:
                continue
            for value in values or []:
                name = str(value or "").strip()
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        return names
    async def _send_reply(
        self,
        event: ReplyEvent,
        text: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
        segments: list[str] | None = None,
        send_original: bool = False,
        images: list[int] | None = None,
        self_sent: SelfSentSink | None = None,
        sender_names: list[str] | None = None,
        split_preview: ReplySplitPreview | None = None,
    ) -> bool:
        """转发到 ReplySender.send_reply；返回是否真的发出了内容（见 sender 注释）。"""
        if self_sent is not None and self_sent.usable:
            sink = self_sent
            before_message_id = sink.queue.get_last_message_id(sink.queue_key)

            def record_delivery() -> None:
                self._record_reply_delivered(event, sink.queue, sink.queue_key, before_message_id=before_message_id)
                if sink.on_delivered is not None:
                    sink.on_delivered()

            self_sent = replace(sink, on_delivered=record_delivery)
        # post-reply hooks：可对回复文本做后处理
        text = await self._apply_post_reply_hooks(event, text) or text
        # 缺少标签时补配置昵称及当前会话标签，不能混入其他群聊/私聊。
        names = list(sender_names or [])
        if not names:
            bot_cfg = getattr(self._config, "bot", None) if self._config else None
            bot_name = str(getattr(bot_cfg, "nick_name", "") or "")
            if bot_name:
                names.append(bot_name)
            ref = event.conversation_ref
            if ref is not None and ref.kind in {"group", "private"}:
                queue = self._group_queue if ref.kind == "group" else self._friend_queue
                names.extend(self._known_sender_names(queue, queue_key=str(ref.id)))
        return await self._sender.send_reply(
            event,
            text,
            reply_to_message_id=reply_to_message_id,
            mention_user_ids=mention_user_ids,
            segments=segments,
            send_original=send_original,
            images=images,
            self_sent=self_sent,
            sender_names=names,
            **({"split_preview": split_preview} if split_preview is not None else {}),
        )
    @staticmethod
    def _self_sent_sink(
        queue: Any, snapshot: Any, queue_key: str
    ) -> SelfSentSink:
        return SelfSentSink(queue=queue, snapshot=snapshot, queue_key=queue_key)
    @staticmethod
    def _resolve_image_registrar(drawing_manager: Any) -> Any:
        """取「本地文件 → temp 图库(tmp_xxx)」的最小登记入口。

        复用生图服务的既有落盘链路（不新增表、不新增存储层）；不可用时返回 None，
        此时索引退化为 file: 路径。
        """
        if drawing_manager is None:
            return None
        service = getattr(drawing_manager, "image_service", None)
        if service is None:
            service = getattr(drawing_manager, "_service", None)
        registrar = getattr(service, "register_local_image", None)
        return registrar if callable(registrar) else None
    def record_notification(
        self,
        *,
        kind: str,
        conversation_id: str,
        source: str,
        content: str,
    ) -> bool:
        """把一条后台通知写进对应会话的消息队列（低权重，供下一轮 transcript 读取）。

        与通知中枢的既有投递正交：投递照旧（起管线 / 进 hub 队列），这里只是让
        agent 在下一轮「知道刚才发生了什么」。永不抛异常。
        """
        from neobot_app.message.queue import NotificationEntry

        queue = self._group_queue if str(kind) == "group" else self._friend_queue
        if queue is None or not str(conversation_id or ""):
            return False
        try:
            queue.push_notification(
                str(conversation_id),
                NotificationEntry(source=str(source or ""), content=str(content or "")),
            )
        except Exception as exc:
            self._logger.warning("后台通知入队失败（已忽略）", source=source, error=str(exc))
            return False
        return True
    def _can_use_markdown_image(self, text: str) -> bool:
        return self._sender._can_use_markdown_image(text)
    async def _render_long_reply_as_image(self, text: str) -> Path:
        return await self._sender._render_long_reply_as_image(text)
    def _build_reply_messages(
        self,
        text: str,
        *,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> list[str]:
        return self._sender._build_reply_messages(
            text, segments=segments, send_original=send_original
        )
    @staticmethod
    def _build_reply_segments(
        *,
        text: str,
        conversation_kind: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
    ) -> list[dict]:
        return ReplySender.build_reply_segments(
            text=text,
            conversation_kind=conversation_kind,
            reply_to_message_id=reply_to_message_id,
            mention_user_ids=mention_user_ids,
        )
    @staticmethod
    def _api_succeeded(result: Any) -> bool:
        if result is None:
            return False
        if not isinstance(result, dict):
            return True
        status = result.get("status")
        if status is None:
            return True
        return status == "ok"

def _segment_file_hint(segment: Any) -> str:
    """从消息段里取出可供将来取用的文件引用（语音段用）。

    TTS 的 `synthesize_segment` 只返回消息段、不返回本地路径，因此这里就地从
    段数据里取 file/url 引用作为「音频文件索引」；取不到时返回空串。
    """
    data: Any = None
    if isinstance(segment, dict):
        data = segment.get("data")
    else:
        data = getattr(segment, "data", None)
    if not isinstance(data, dict):
        return ""
    for key in ("file", "url", "path"):
        value = data.get(key)
        if value:
            return str(value)
    return ""

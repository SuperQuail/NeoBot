"""条目文本渲染：时间戳、消息/撤回/表情/通知/戳一戳与发送者标签。"""

from __future__ import annotations

from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from neobot_app.time_context import from_epoch_seconds

from .common import (
    NotificationEntry,
    PokeEntry,
    QueueEntry,
    QueueEntryType,
    QueueMessage,
    ReactionEntry,
    RecallNotice,
)
from .helpers import _poke_sub_type_text


class _QueueTextMixin:
    @staticmethod
    def _format_timestamp(timestamp: Optional[int]) -> str:
        if timestamp is None:
            return "未知时间"
        dt = from_epoch_seconds(timestamp)
        return f"{dt.year}-{dt.month}-{dt.day}-{dt.hour}:{dt.minute:02d}"

    def _message_to_text(
        self,
        message: QueueMessage,
        *,
        sender_labels: Optional[Dict[int, str]] = None,
        sender_labels_by_user: Optional[Dict[str, str]] = None,
        replied_messages: Optional[List[QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
        wrap_at_mention: bool = False,
    ) -> str:
        name = self._message_sender_label(
            message,
            sender_labels=sender_labels,
            sender_labels_by_user=sender_labels_by_user,
        )
        content = self._render_message_content(
            message,
            replied_messages=replied_messages,
            reply_number_resolver=reply_number_resolver,
            wrap_at_mention=wrap_at_mention,
        )
        return f"{name}: {content}" if content else f"{name}: [无消息内容]"

    def _recall_to_text(
        self,
        notice: RecallNotice,
        recalled_message: Optional[QueueMessage],
        *,
        sender_labels: Optional[Dict[int, str]] = None,
        sender_labels_by_user: Optional[Dict[str, str]] = None,
    ) -> str:
        if recalled_message is not None:
            return f"消息撤回: {self._message_to_text(recalled_message, sender_labels=sender_labels, sender_labels_by_user=sender_labels_by_user)}"
        message_id = notice.message_id if notice.message_id is not None else "未知"
        return f"消息撤回: [原消息不可用, message_id={message_id}]"

    @staticmethod
    def _reaction_to_text(reaction: ReactionEntry) -> str:
        from neobot_app.emoji.mapping import lookup_emoji

        emoji_info = lookup_emoji(reaction.emoji_id)
        if emoji_info is not None:
            emoji_name = emoji_info[0]
        else:
            emoji_name = f"表情#{reaction.emoji_id}"
        return (
            f"{reaction.operator_name} 回应了消息[msg_id={reaction.target_message_id}]:{emoji_name}"
        )

    @staticmethod
    def _notification_to_text(notification: NotificationEntry) -> str:
        """通知条目的统一渲染形态：`[通知:<source>] <content>`。"""
        source = str(notification.source or "unknown")
        content = " ".join(str(notification.content or "").split())
        return f"[通知:{source}] {content}" if content else f"[通知:{source}]"

    @staticmethod
    def _poke_to_text(poke: PokeEntry, *, poke_index: int = 0) -> str:
        if poke.action_text:
            text = poke.action_text
        else:
            action_desc = _poke_sub_type_text(poke.sub_type)
            sender = poke.sender_name or f"QQ:{poke.user_id}"
            target = poke.target_name or f"QQ:{poke.target_id}"
            text = f"{sender} 对 {target} 使用了{action_desc}"

        if poke_index == 1:
            return f"{text} [这是QQ戳一戳的消息,会让被戳的人手机轻微震动]"
        if poke_index >= 2:
            return f"{text} [戳一戳消息]"
        return text

    def sender_labels(
        self, queue_key: str | None = None, *, include_bot: bool = True
    ) -> list[str]:
        """列出队列里出现过的全部发送者显示名（昵称 / 群名片，去重）。

        用途：发送前清洗要认出模型从历史里学来的 `编号: 名字: ` 前缀。脏前缀里的
        名字**既可能是模型自己的，也可能是它刚续写出来的别人的**（报告里的
        `215: 贝拉: 要抱抱` 就是别人），所以这份集合必须覆盖本会话所有发送者，
        只收 Bot 自己是拦不住主症状的。

        queue_key 指定当前会话；省略时保留汇总所有队列的旧接口。
        同时收集实际渲染标签（含重名消歧后缀）及被回复消息作者。
        include_bot=False 时只返回别人（Bot 自己的名字由配置昵称单独提供）。
        """
        labels: list[str] = []
        seen: set[str] = set()

        def add(value: object) -> None:
            name = str(value or "").strip()
            if name and name not in seen:
                seen.add(name)
                labels.append(name)

        # No key retains the legacy aggregate API; runtime callers supply their key.
        queues = (
            self._queues.values()
            if queue_key is None
            else (self._queues.get(queue_key, ()),)
        )
        for queue in queues:
            entries = list(queue)
            rendered, by_user = self._build_sender_labels(entries)
            for entry in entries:
                messages: list[tuple[QueueMessage, Optional[Dict[int, str]]]] = []
                if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
                    messages.append((entry.message, rendered))
                    # Numbered reply lines resolve independently parsed authors by user id.
                    messages.extend((reply, None) for reply in entry.replied_messages)
                elif entry.kind == QueueEntryType.RECALL and entry.recalled_message is not None:
                    messages.append((entry.recalled_message, rendered))
                for message, by_message in messages:
                    if (
                        not include_bot
                        and self.bot_account is not None
                        and message.user_id == self.bot_account
                    ):
                        continue
                    sender = getattr(message, "sender", None)
                    add(getattr(sender, "nickname", None))
                    add(getattr(sender, "card", None))
                    add(self._message_sender_label(
                        message, sender_labels=by_message, sender_labels_by_user=by_user
                    ))
        return labels

    @staticmethod
    def _message_sender_name(message: QueueMessage) -> str:
        sender = message.sender
        if sender is not None and sender.nickname:
            return str(sender.nickname)
        if sender is not None and sender.card:
            return str(sender.card)
        if message.user_id is not None:
            return f"QQ:{message.user_id}"
        return "未知用户"

    def _message_sender_label(
        self,
        message: QueueMessage,
        *,
        sender_labels: Optional[Dict[int, str]] = None,
        sender_labels_by_user: Optional[Dict[str, str]] = None,
    ) -> str:
        if sender_labels is not None:
            label = sender_labels.get(id(message))
            if label:
                return label
        # 按 user_id 回退:被回复消息/撤回原文常是独立解析出的对象,
        # id() 在"深拷贝快照 + 源对象混合"场景会 miss,user_id 索引不受影响
        if sender_labels_by_user is not None and message.user_id is not None:
            label = sender_labels_by_user.get(str(message.user_id))
            if label:
                return label
        return self._message_sender_name(message)

    def _build_sender_labels(
        self, entries: List[QueueEntry]
    ) -> Tuple[Dict[int, str], Dict[str, str]]:
        """构建发送者标签:返回 (id 索引, user_id 索引) 两份映射。

        重名用户加 QQ 号后缀消歧;user_id 索引供独立解析出的
        (被回复/撤回)消息对象回退使用,保证同一发送者身份恒定。
        """
        messages = [
            entry.message
            for entry in entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        name_to_sender_ids: Dict[str, set[str]] = {}
        for message in messages:
            name = self._message_sender_name(message)
            sender_id = self._message_sender_identity(message)
            name_to_sender_ids.setdefault(name, set()).add(sender_id)

        duplicate_names = {
            name
            for name, sender_ids in name_to_sender_ids.items()
            if len(sender_ids) > 1
        }
        labels: Dict[int, str] = {}
        labels_by_user: Dict[str, str] = {}
        for message in messages:
            name = self._message_sender_name(message)
            if name in duplicate_names and message.user_id is not None:
                label = f"{name}({message.user_id})"
                labels[id(message)] = label
                labels_by_user.setdefault(str(message.user_id), label)
            else:
                labels[id(message)] = name
                if message.user_id is not None:
                    labels_by_user.setdefault(str(message.user_id), name)
        return labels, labels_by_user

    def _build_new_duplicate_notes(
        self,
        *,
        previous_entries: List[QueueEntry],
        new_entries: List[QueueEntry],
        context_entries: List[QueueEntry],
    ) -> List[str]:
        previous_messages = [
            entry.message
            for entry in previous_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        new_messages = [
            entry.message
            for entry in new_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]
        if not previous_messages or not new_messages:
            return []

        previous_by_name: Dict[str, Dict[str, QueueMessage]] = {}
        new_by_name: Dict[str, Dict[str, QueueMessage]] = {}

        for message in previous_messages:
            name = self._message_sender_name(message)
            previous_by_name.setdefault(name, {})[self._message_sender_identity(message)] = message
        for message in new_messages:
            name = self._message_sender_name(message)
            new_by_name.setdefault(name, {})[self._message_sender_identity(message)] = message

        notes: List[str] = []
        for name in sorted(set(previous_by_name) & set(new_by_name)):
            previous_senders = previous_by_name[name]
            new_senders = new_by_name[name]
            if not set(new_senders) - set(previous_senders):
                continue
            for message in previous_senders.values():
                if message.user_id is None:
                    continue
                notes.append(f'之前的"{name}"是QQ号为{message.user_id}的')
        return notes

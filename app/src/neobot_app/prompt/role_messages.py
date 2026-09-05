"""把消息队列条目按角色拆分为真实的 user/assistant 消息。

新提示词架构下,聊天记录不再内嵌在 system 提示词中,而是:
    - 普通用户消息 -> user 角色
    - bot 自己发出的消息 -> assistant 角色(模型会将其视为自己的历史输出,
      避免重复回答同一话题、同一话题前后观点不一致)
    - 时间戳/撤回/表情回应/戳一戳等非消息条目 -> 独立的 user 消息

消息编号(numbering)与 system 提示词中的 <消息编号说明> 共用同一个实例,
保证工具参数(如 reply_to)引用的编号一致;每条消息行首的 [msg_id=xxx]
即真实 OneBot message_id,工具参数需要 message_id 时直接使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.message.queue import QueueEntryType

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


def _user_message(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


def _role_for_message(message: Any, bot_account: int) -> str:
    if bot_account and getattr(message, "user_id", None) == bot_account:
        return "assistant"
    return "user"


def build_role_messages(
    queue: Any,
    queue_key: str,
    *,
    numbering: "MessageNumbering | None" = None,
    bot_account: int = 0,
    include_boundary_markers: bool = False,
    last_reply_message_id: int | None = None,
    all_new: bool = False,
) -> list[dict[str, str]]:
    """为一个队列的所有条目构建角色消息列表(全量)。"""
    return _build_from_entries(
        queue.entries(queue_key),
        queue,
        numbering=numbering,
        bot_account=bot_account,
        include_boundary_markers=include_boundary_markers,
        last_reply_message_id=last_reply_message_id,
        all_new=all_new,
    )


def build_role_messages_from_entries(
    entries: list,
    queue: Any,
    queue_key: str = "",
    *,
    numbering: "MessageNumbering | None" = None,
    bot_account: int = 0,
    include_boundary_markers: bool = False,
    context_entries: list | None = None,
) -> list[dict[str, str]]:
    """为新增的队列条目构建角色消息列表(增量,用于挂起恢复等场景)。

    context_entries:发送者标签的计算上下文(默认取 queue 该键的全量条目)。
    增量构建必须基于全量上下文计算发送者标签,否则重名用户的后缀
    (如"小明(111)")会因窗口不同而时有时无,同一人两种身份。
    """
    if context_entries is None:
        try:
            context_entries = queue.entries(queue_key)
        except Exception:
            context_entries = list(entries)
    return _build_from_entries(
        entries,
        queue,
        numbering=numbering,
        bot_account=bot_account,
        include_boundary_markers=include_boundary_markers,
        last_reply_message_id=None,
        all_new=False,
        label_context_entries=context_entries,
    )


def _build_from_entries(
    entries: list,
    queue: Any,
    *,
    numbering: "MessageNumbering | None",
    bot_account: int,
    include_boundary_markers: bool,
    last_reply_message_id: int | None,
    all_new: bool,
    label_context_entries: list | None = None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    # 发送者标签基于全量上下文计算,保证同一发送者在同一对话中身份恒定
    label_context = entries if label_context_entries is None else label_context_entries
    sender_labels, sender_labels_by_user = queue._build_sender_labels(label_context)

    found_last_reply = False
    if last_reply_message_id is not None:
        found_last_reply = any(
            entry.kind == QueueEntryType.MESSAGE
            and entry.message is not None
            and entry.message.message_id == last_reply_message_id
            for entry in entries
        )
    if all_new or (last_reply_message_id is not None and not found_last_reply):
        if include_boundary_markers:
            messages.append(_user_message("<当前均为新消息，没有上次回复过的内容>"))

    new_section_opened = False
    new_section_content_emitted = False
    poke_count = 0
    for i, entry in enumerate(entries):
        if new_section_opened and i > 0:
            prev_entry = entries[i - 1]
            if (
                prev_entry.kind == QueueEntryType.MESSAGE
                and prev_entry.message is not None
                and prev_entry.message.message_id == last_reply_message_id
            ):
                if include_boundary_markers:
                    messages.append(_user_message("<这是新的可能要回答的内容>"))
                    new_section_content_emitted = True

        if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
            msg = entry.message

            # 被回复消息(引用的原文)先行渲染并分配编号;
            # 发送者标签与主消息一致(重名消歧后缀),避免同一人两种称谓
            for replied in getattr(entry, "replied_messages", []) or []:
                replied_id = getattr(replied, "message_id", None)
                if replied_id is None:
                    continue
                if numbering is not None and numbering.get_number(replied_id) is not None:
                    continue
                number = numbering._assign_number(replied_id) if numbering else None
                sender = queue._message_sender_label(replied, sender_labels=sender_labels, sender_labels_by_user=sender_labels_by_user)
                content = queue._render_message_content(replied)
                prefix = f"{number}: " if number is not None else ""
                messages.append(
                    {
                        "role": _role_for_message(replied, bot_account),
                        "content": (
                            f"[msg_id={replied_id}] {prefix}[被回复消息] {sender}: {content}"
                        ),
                    }
                )

            msg_id = msg.message_id
            # 无 message_id 的消息与 numbering.apply 保持一致:跳过
            # (无法分配编号,也无法被工具引用;被回复消息已在上面渲染)
            if msg_id is None:
                continue

            number = None
            if numbering is not None:
                number = numbering._assign_number(msg_id)
            sender = queue._message_sender_label(msg, sender_labels=sender_labels, sender_labels_by_user=sender_labels_by_user)
            content = queue._render_message_content(
                msg,
                replied_messages=entry.replied_messages,
                reply_number_resolver=numbering._assign_number if numbering else None,
                wrap_at_mention=False,
            )
            prefix = f"{number}: " if number is not None else ""
            messages.append(
                {
                    "role": _role_for_message(msg, bot_account),
                    "content": f"[msg_id={msg_id}] {prefix}{sender}: {content}",
                }
            )
        elif entry.kind == QueueEntryType.TIMESTAMP:
            text = queue._entry_to_text(entry, sender_labels=sender_labels)
            if text:
                messages.append(_user_message(text))
        elif entry.kind == QueueEntryType.RECALL:
            text = queue._entry_to_text(entry, sender_labels=sender_labels)
            if text:
                messages.append(_user_message(text))
        elif entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
            if numbering is not None:
                target_number = numbering.get_number(entry.reaction.target_message_id)
                if target_number is not None:
                    messages.append(
                        _user_message(numbering._format_reaction(entry.reaction, target_number))
                    )
        elif entry.kind == QueueEntryType.POKE and entry.poke is not None:
            poke_count += 1
            text = queue._poke_to_text(entry.poke, poke_index=poke_count)
            if text:
                messages.append(_user_message(text))

        if (
            last_reply_message_id is not None
            and entry.kind == QueueEntryType.MESSAGE
            and entry.message is not None
            and entry.message.message_id == last_reply_message_id
        ):
            if include_boundary_markers:
                messages.append(_user_message("<以上是上次对话回复过的内容>"))
            new_section_opened = True
            continue
    # 仅在确实输出过新区段内容/开标记时才追加闭合标记,避免残缺的
    # "</这是新的可能要回答的内容>" 单独出现(last_reply 位于队尾时)
    if new_section_opened and new_section_content_emitted:
        if include_boundary_markers:
            messages.append(_user_message("</这是新的可能要回答的内容>"))
    return messages

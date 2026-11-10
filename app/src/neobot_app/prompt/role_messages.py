"""把消息队列条目按角色拆分为真实的 user/assistant 消息。

新提示词架构下,聊天记录不再内嵌在 system 提示词中,而是:
    - 普通用户消息 -> user 角色
    - bot 自己发出的消息 -> assistant 的 send_reply 工具调用 + 对应 tool 回执
      (模型看到的是「用工具说话」的历史，避免模仿纯文本输出)
    - 时间戳/撤回/表情回应/戳一戳等非消息条目 -> 独立的 user 消息

消息编号(numbering)与 system 提示词中的 <消息编号说明> 共用同一个实例,
保证工具参数(如 reply_to)引用的编号一致;每条消息行首的 [msg_id=xxx]
即真实 OneBot message_id,工具参数需要 message_id 时直接使用。

**assistant 历史统一改写为 send_reply 工具调用**(见 _as_send_reply_tool_history):
历史里 assistant 只带正文，等于用例子教模型不用工具也能说话；现在每条历史发言换成
assistant.tool_calls(send_reply) + 同 id 的 tool 回执，正文仍在 arguments 里。

**每条 user 消息带粗粒度年龄**(fix(14)):旧消息不再「永远不会过期」。年龄由
occurred_at 相对**本次快照里最新一条消息**计算,不读墙钟——同一队列快照在任意
时刻渲染都逐字节一致,稳定前缀缓存不受影响。assistant 行仍然不加任何标注。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from neobot_app.message.queue import QueueEntryType, is_bot_message
from neobot_app.prompt.assets import text

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering


def _label(key: str, *, prompt_store: Any = None, **values: Any) -> str:
    """读取内部标签：custom 覆盖 / enabled / 内置模板统一走 assets。"""
    return text("label_message_meta", key, store=prompt_store, values=values)


def _replied_prefix(prompt_store: Any = None) -> str:
    """引用前缀 + 一个分隔空格。

    assets 渲染会裁掉模板尾随空白（``replied_prefix`` 在 TOML 里带空格），
    这里统一补回，保证默认输出与自定义覆盖都只有一个分隔空格。
    """
    value = _label("replied_prefix", prompt_store=prompt_store)
    return f"{value.rstrip()} " if value.strip() else ""


def _user_message(content: str) -> dict[str, Any]:
    return {"role": "user", "content": content}


def _role_for_message(message: Any, bot_accounts: set[int]) -> str:
    # 双通道下两个 bot 的发言都算助手；消息级 self_id（自身回显）优先
    if is_bot_message(message, bot_accounts):
        return "assistant"
    return "user"


def _latest_message_epoch(entries: list) -> int | None:
    """本次快照里最新一条消息的时间：消息年龄的唯一参考点（不读墙钟）。"""
    times = [
        entry.occurred_at
        for entry in entries
        if entry.kind == QueueEntryType.MESSAGE and entry.occurred_at is not None
    ]
    return max(times) if times else None


def _format_message_age(
    occurred_at: int | None, reference: int | None, *, prompt_store: Any = None
) -> str:
    """粗粒度年龄（刚刚 / N分钟前 / N小时前 / N天前）；无时间信息时返回空串。"""
    if occurred_at is None or reference is None:
        return ""
    age = max(0, int(reference) - int(occurred_at))
    if age < 60:
        return _label("age_just_now", prompt_store=prompt_store)
    if age < 3600:
        return _label("age_minutes", prompt_store=prompt_store, minutes=age // 60)
    if age < 86400:
        return _label("age_hours", prompt_store=prompt_store, hours=age // 3600)
    return _label("age_days", prompt_store=prompt_store, days=age // 86400)


def _render_role_message(
    *,
    role: str,
    msg_id: int | None,
    number: int | None,
    sender: str,
    content: str,
    replied: bool = False,
    age: str = "",
    prompt_store: Any = None,
) -> dict[str, Any]:
    """按角色渲染一条聊天记录。

    **assistant 角色不渲染 `编号: 发送者:` 前缀**（根因修复）。
    assistant 正文随后由 _as_send_reply_tool_history 改写为 send_reply 工具调用。

    历史里 assistant 消息带着系统生成的标注，等于用例子教模型「你就该这么说话」：
    模型被告知这些是它自己说过的话，于是照抄格式去续写聊天记录（`193: AAA大肥鱼:
    我是一条鱼`），脏输出再经 self-sent 通道写回历史，形成正反馈。

    编号/发送者名字是给模型**指代别人**用的（reply_to / msg_number），对它自己
    的发言没有用处；唯一的效果就是把标注示范成输出格式。`[msg_id=...]` 同理：
    它也是被禁止的行首标注，而且自身发言带的是**负数合成 id**（不是真实 OneBot
    message_id，填进 reply_to 也解析不出东西）。因此 assistant 行只留正文。
    """
    if role == "assistant":
        # 不渲染任何标注（含 [msg_id=...]）：msg_id 参数保留只是为了让两种角色
        # 共用同一个签名，这里刻意不用它。
        body = content
        if replied:
            body = _replied_prefix(prompt_store) + content
        return {"role": role, "content": body, "_history_msg_id": msg_id}
    prefix = f"{number}: " if number is not None else ""
    marker = _replied_prefix(prompt_store) if replied else ""
    age_label = f"[{age}] " if age else ""
    return {
        "role": role,
        "content": _label(
            "line",
            prompt_store=prompt_store,
            msg_id=msg_id,
            prefix=prefix,
            marker=marker,
            age=age_label,
            sender=sender,
            content=content,
        ),
    }


def _as_send_reply_tool_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把历史 assistant 正文改成 send_reply 工具调用，避免模型模仿纯文本发言。

    历史里 assistant 只带正文，等于用例子教模型「不用工具也能说话」。这里把每条
    历史发言改写成 assistant.tool_calls(send_reply) + 对应的 tool 回执；正文仍在
    arguments 里，模型能读到，但看到的输出形式是工具调用。
    """
    converted: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if message.get("role") != "assistant" or message.get("tool_calls"):
            message.pop("_history_msg_id", None)
            converted.append(message)
            continue
        content = str(message.get("content") or "")
        history_id = message.pop("_history_msg_id", None)
        if not content:
            converted.append(message)
            continue
        call_id = f"history_{history_id if history_id is not None else index}"
        converted.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": "send_reply",
                            "arguments": json.dumps({"text": content}, ensure_ascii=False),
                        },
                    }
                ],
            }
        )
        converted.append(
            {
                "role": "tool",
                "tool_call_id": call_id,
                "name": "send_reply",
                "content": json.dumps({"ok": True}, ensure_ascii=False),
            }
        )
    return converted


def build_role_messages(
    queue: Any,
    queue_key: str,
    *,
    numbering: "MessageNumbering | None" = None,
    bot_account: int = 0,
    include_boundary_markers: bool = False,
    last_reply_message_id: int | None = None,
    all_new: bool = False,
    prompt_store: Any = None,
) -> list[dict[str, Any]]:
    """为一个队列的所有条目构建角色消息列表(全量)。"""
    return _build_from_entries(
        queue.entries(queue_key),
        queue,
        numbering=numbering,
        bot_account=bot_account,
        include_boundary_markers=include_boundary_markers,
        last_reply_message_id=last_reply_message_id,
        all_new=all_new,
        prompt_store=prompt_store,
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
    prompt_store: Any = None,
) -> list[dict[str, Any]]:
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
        prompt_store=prompt_store,
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
    prompt_store: Any = None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, str]] = []
    # bot 账号来源：队列登记的全部通道账号 + 调用方传入的当前账号
    bot_accounts = {int(account) for account in (getattr(queue, "bot_accounts", None) or ())}
    if bot_account:
        bot_accounts.add(int(bot_account))
    # 发送者标签基于全量上下文计算,保证同一发送者在同一对话中身份恒定
    label_context = entries if label_context_entries is None else label_context_entries
    sender_labels, sender_labels_by_user = queue._build_sender_labels(label_context)
    # 年龄参考点取上下文里最新的一条消息：同一队列快照无论何时渲染都得到同样的
    # 字节（缓存安全护栏 A1），也不依赖调用时刻的墙钟。
    reference_epoch = _latest_message_epoch(label_context)

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
            messages.append(_user_message(_label("all_new", prompt_store=prompt_store)))

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
                    messages.append(_user_message(_label("new_content_open", prompt_store=prompt_store)))
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
                messages.append(
                    _render_role_message(
                        role=_role_for_message(replied, bot_accounts),
                        msg_id=replied_id,
                        number=number,
                        sender=sender,
                        content=content,
                        replied=True,
                        age=_format_message_age(
                            getattr(replied, "time", None),
                            reference_epoch,
                            prompt_store=prompt_store,
                        ),
                        prompt_store=prompt_store,
                    )
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
            messages.append(
                _render_role_message(
                    role=_role_for_message(msg, bot_accounts),
                    msg_id=msg_id,
                    number=number,
                    sender=sender,
                    content=content,
                    age=_format_message_age(entry.occurred_at, reference_epoch, prompt_store=prompt_store),
                    prompt_store=prompt_store,
                )
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
        elif entry.kind == QueueEntryType.NOTIFICATION and entry.notification is not None:
            # 后台通知（余额预警、定时任务完成、绘图完成…）以独立 user 块进入
            # transcript，让 agent 在下一轮知道「刚才发生了什么」。
            text = queue._entry_to_text(entry, sender_labels=sender_labels)
            if text:
                messages.append(_user_message(text))

        if (
            last_reply_message_id is not None
            and entry.kind == QueueEntryType.MESSAGE
            and entry.message is not None
            and entry.message.message_id == last_reply_message_id
        ):
            if include_boundary_markers:
                messages.append(_user_message(_label("previous_content", prompt_store=prompt_store)))
            new_section_opened = True
            continue
    # 仅在确实输出过新区段内容/开标记时才追加闭合标记,避免残缺的
    # "</这是新的可能要回答的内容>" 单独出现(last_reply 位于队尾时)
    if new_section_opened and new_section_content_emitted:
        if include_boundary_markers:
            messages.append(_user_message(_label("new_content_close", prompt_store=prompt_store)))
    return _as_send_reply_tool_history(
        [
            message
            for message in messages
            if message.get("role") != "user" or message.get("content")
        ]
    )

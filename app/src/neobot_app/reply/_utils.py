"""Reply module internal utilities (fingerprinting, message-id extraction)."""

from __future__ import annotations

from neobot_app.message.queue import QueueEntryType


def msg_id_of(entry) -> int | None:
    """从 QueueEntry 中提取 message_id，不存在则返回 None。"""
    if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
        return entry.message.message_id
    return None


def entry_fingerprint(entry) -> str:
    """为 QueueEntry 生成去重指纹。

    MESSAGE 条目使用 message_id；非 MESSAGE 条目使用类型+内容哈希。
    确保 TIMESTAMP / RECALL / REACTION / POKE 等条目也能正确去重。
    """
    if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
        mid = entry.message.message_id
        if mid is not None:
            return f"msg:{mid}"
        return f"msg:hash:{hash(str(entry.message.model_dump(mode='json')))}"

    if entry.kind == QueueEntryType.TIMESTAMP:
        return f"ts:{entry.occurred_at}"

    if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
        nid = entry.notice.message_id
        uid = getattr(entry.notice, "user_id", "")
        oid = getattr(entry.notice, "operator_id", "")
        return f"recall:{nid}:{uid}:{oid}:{entry.occurred_at}"

    if entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
        r = entry.reaction
        return f"reaction:{r.target_message_id}:{r.emoji_id}:{r.operator_user_id}"

    if entry.kind == QueueEntryType.POKE and entry.poke is not None:
        p = entry.poke
        return f"poke:{p.sender_id}:{p.target_id}:{p.sub_type}:{entry.occurred_at}"

    return f"unknown:{entry.kind.value}:{hash(str(entry))}"

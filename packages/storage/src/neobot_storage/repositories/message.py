"""SqlAlchemy 消息仓库。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models import ConversationRef, IncomingMessage

from neobot_storage.models import MessageData


class SqlAlchemyMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_message(self, message: IncomingMessage) -> None:
        # 工具调用对 storage 是不透明 JSON：形状由上层定义，这里只保证能原样取回。
        tool_call_json = (
            json.dumps(message.tool_call, ensure_ascii=False, default=str) if message.tool_call is not None else None
        )
        row = MessageData(
            event_id=message.event_id,
            conversation_kind=message.conversation.kind,
            conversation_id=message.conversation.id,
            sender_id=message.sender_id,
            sender_name=message.sender_name,
            text=message.text,
            occurred_at=message.occurred_at,
            tool_call_json=tool_call_json,
        )
        self._session.add(row)

    async def get_history(self, conversation: ConversationRef, limit: int = 50) -> list[IncomingMessage]:
        stmt = (
            select(MessageData)
            .where(
                MessageData.conversation_kind == conversation.kind,
                MessageData.conversation_id == conversation.id,
            )
            .order_by(MessageData.occurred_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_message(r) for r in reversed(rows)]

    async def get_recent_by_sender(
        self, conversation: ConversationRef, sender_id: str, limit: int | None = None
    ) -> list[IncomingMessage]:
        """取该会话内某个发送者最近的若干条消息（按时间正序返回）。

        用于软重启/冷启动后从本地记录补齐 Bot 自身发言（assistant 块）：
        只看「最近 N 条消息」不够——那 N 条可能全是用户消息，必须按发送者过滤。

        limit=None 表示不限条数：调用方（启动历史补齐）改用与后端历史相同的
        观察窗口自行约束，不再保留一套独立的「自身发言历史上限」。
        """
        stmt = (
            select(MessageData)
            .where(
                MessageData.conversation_kind == conversation.kind,
                MessageData.conversation_id == conversation.id,
                MessageData.sender_id == sender_id,
            )
            .order_by(MessageData.occurred_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_message(r) for r in reversed(rows)]


def _row_to_message(row: MessageData) -> IncomingMessage:
    """ORM 行 -> 领域消息；坏掉的 tool_call_json 降级为 None，不让历史查询失败。"""
    return IncomingMessage(
        event_id=row.event_id,
        conversation=ConversationRef(kind=row.conversation_kind, id=row.conversation_id),
        sender_id=row.sender_id,
        sender_name=row.sender_name,
        text=row.text,
        occurred_at=row.occurred_at,
        tool_call=_parse_tool_call(row.tool_call_json),
    )


def _parse_tool_call(raw: str | None) -> dict[str, Any] | None:
    """tool_call_json -> dict；NULL/非法 JSON/非对象 JSON 都返回 None。"""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None

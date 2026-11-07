"""跨聊天会话访问端口。

语义：
- 一条 **session** 表示「发起方聊天流 + 目标聊天流」之间的一次跨聊天交互记录；
- 同一对（origin, target）只保留**本进程**写入的最新一条，重启后旧 session 不再显示；
- 记录只用于 agent 观察自己做过哪些跨聊天交互，**不参与投递语义**。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from neobot_contracts.models.cross_chat_session import CrossChatSessionRecord


@runtime_checkable
class CrossChatSessionAccess(Protocol):
    """跨聊天会话的持久化读写。"""

    async def upsert(
        self,
        *,
        origin_kind: str,
        origin_id: str,
        target_kind: str,
        target_id: str,
        task_id: str,
        mode: str,
        notification_mode: str,
        status: str,
        boot_id: str,
    ) -> CrossChatSessionRecord: ...

    async def record_result(
        self,
        *,
        origin_kind: str,
        origin_id: str,
        target_kind: str,
        target_id: str,
        reply: str,
        status: str,
        boot_id: str,
    ) -> CrossChatSessionRecord | None: ...

    async def list_for_chat(
        self,
        *,
        kind: str,
        conversation_id: str,
        boot_id: str,
        limit: int = 20,
    ) -> list[CrossChatSessionRecord]: ...

    async def get(
        self,
        *,
        origin_kind: str,
        origin_id: str,
        target_kind: str,
        target_id: str,
        boot_id: str,
    ) -> CrossChatSessionRecord | None: ...

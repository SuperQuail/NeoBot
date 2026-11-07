"""跨聊天会话仓库 —— 按（发起方, 目标）对保存一次性记录。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_contracts.models.cross_chat_session import CrossChatSessionRecord
from neobot_storage.models import CrossChatSessionData


class SqlAlchemyCrossChatSessionAccess:
    """跨聊天会话的异步数据访问。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain(row: CrossChatSessionData) -> CrossChatSessionRecord:
        return CrossChatSessionRecord(
            origin_kind=row.origin_kind,
            origin_id=row.origin_id,
            target_kind=row.target_kind,
            target_id=row.target_id,
            task_id=row.task_id,
            mode=row.mode,
            notification_mode=row.notification_mode,
            status=row.status,
            reply=row.reply,
            boot_id=row.boot_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

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
        reply: str = "",
    ) -> CrossChatSessionRecord:
        now = datetime.now(timezone.utc)
        stmt = sqlite_insert(CrossChatSessionData).values(
            origin_kind=str(origin_kind),
            origin_id=str(origin_id),
            target_kind=str(target_kind),
            target_id=str(target_id),
            task_id=str(task_id),
            mode=str(mode),
            notification_mode=str(notification_mode),
            status=str(status),
            reply=str(reply),
            boot_id=str(boot_id),
            created_at=now,
            updated_at=now,
        )
        # 唯一键含 boot_id：同一对聊天流在同一进程内复用一行（重置 reply/created_at，
        # 不会把上一次的回复带到这次），不同进程各留自己的行，互不覆盖。
        stmt = stmt.on_conflict_do_update(
            index_elements=["origin_kind", "origin_id", "target_kind", "target_id", "boot_id"],
            set_={
                "task_id": stmt.excluded.task_id,
                "mode": stmt.excluded.mode,
                "notification_mode": stmt.excluded.notification_mode,
                "status": stmt.excluded.status,
                "reply": stmt.excluded.reply,
                "created_at": stmt.excluded.created_at,
                "updated_at": now,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()
        # 每次写入顺带清理过期行（同一事务，代价可忽略）
        await self.prune_older_than(now - timedelta(days=30))
        record = await self.get(
            origin_kind=origin_kind,
            origin_id=origin_id,
            target_kind=target_kind,
            target_id=target_id,
            boot_id=boot_id,
        )
        assert record is not None
        return record

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
        task_id: str | None = None,
    ) -> CrossChatSessionRecord | None:
        row = await self._get_row(
            origin_kind, origin_id, target_kind, target_id, boot_id
        )
        if row is None:
            return None
        # task_id 不匹配说明该行已被同一对的后续投递重置，旧回传不要覆盖新记录。
        if task_id is not None and row.task_id != str(task_id):
            return None
        row.reply = str(reply)
        row.status = str(status)
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return self._to_domain(row)

    async def list_for_chat(
        self,
        *,
        kind: str,
        conversation_id: str,
        boot_id: str,
        limit: int = 20,
    ) -> list[CrossChatSessionRecord]:
        stmt = (
            select(CrossChatSessionData)
            .where(
                CrossChatSessionData.boot_id == str(boot_id),
                (
                    (CrossChatSessionData.origin_kind == str(kind))
                    & (CrossChatSessionData.origin_id == str(conversation_id))
                )
                | (
                    (CrossChatSessionData.target_kind == str(kind))
                    & (CrossChatSessionData.target_id == str(conversation_id))
                ),
            )
            .order_by(CrossChatSessionData.updated_at.desc())
            .limit(max(1, int(limit)))
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(row) for row in result.scalars().all()]

    async def get(
        self,
        *,
        origin_kind: str,
        origin_id: str,
        target_kind: str,
        target_id: str,
        boot_id: str,
    ) -> CrossChatSessionRecord | None:
        row = await self._get_row(
            origin_kind, origin_id, target_kind, target_id, boot_id
        )
        return self._to_domain(row) if row is not None else None

    async def prune_older_than(self, cutoff: datetime) -> int:
        """删除 ``updated_at`` 早于 cutoff 的行，返回删除条数。

        0031 起「每进程每对一行」，不清理会随重启次数无界增长；按时间窗清理
        不会影响仍在运行的其它进程（它们的行是新的）。
        """
        from sqlalchemy import delete

        result = await self._session.execute(
            delete(CrossChatSessionData).where(
                CrossChatSessionData.updated_at < cutoff
            )
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def _get_row(
        self,
        origin_kind: str,
        origin_id: str,
        target_kind: str,
        target_id: str,
        boot_id: str,
    ) -> CrossChatSessionData | None:
        stmt = select(CrossChatSessionData).where(
            CrossChatSessionData.origin_kind == str(origin_kind),
            CrossChatSessionData.origin_id == str(origin_id),
            CrossChatSessionData.target_kind == str(target_kind),
            CrossChatSessionData.target_id == str(target_id),
            CrossChatSessionData.boot_id == str(boot_id),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

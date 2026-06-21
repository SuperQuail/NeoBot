"""BilibiliLink repository — B站-QQ账户关联持久化。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from neobot_storage.models import BilibiliLinkData


class SqlAlchemyBilibiliLinkAccess:
    """B站-QQ账户关联的异步数据访问。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, bilibili_uid: int, qq_number: str) -> None:
        now = datetime.now(timezone.utc)
        link = BilibiliLinkData(
            bilibili_uid=bilibili_uid,
            qq_number=qq_number,
            created_at=now,
            updated_at=now,
        )
        self._session.add(link)
        await self._session.flush()

    async def find_by_uid_and_qq(self, bilibili_uid: int, qq_number: str) -> BilibiliLinkData | None:
        stmt = (
            select(BilibiliLinkData)
            .where(
                BilibiliLinkData.bilibili_uid == bilibili_uid,
                BilibiliLinkData.qq_number == qq_number,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_uid(self, bilibili_uid: int) -> list[dict]:
        stmt = (
            select(BilibiliLinkData)
            .where(BilibiliLinkData.bilibili_uid == bilibili_uid)
        )
        result = await self._session.execute(stmt)
        links = result.scalars().all()
        return [
            {"bilibili_uid": l.bilibili_uid, "qq_number": l.qq_number,
             "created_at": l.created_at.isoformat() if l.created_at else None}
            for l in links
        ]

    async def find_by_qq(self, qq_number: str) -> list[dict]:
        stmt = (
            select(BilibiliLinkData)
            .where(BilibiliLinkData.qq_number == qq_number)
        )
        result = await self._session.execute(stmt)
        links = result.scalars().all()
        return [
            {"bilibili_uid": l.bilibili_uid, "qq_number": l.qq_number,
             "created_at": l.created_at.isoformat() if l.created_at else None}
            for l in links
        ]

    async def delete_one(self, bilibili_uid: int, qq_number: str) -> int:
        stmt = (
            delete(BilibiliLinkData)
            .where(
                BilibiliLinkData.bilibili_uid == bilibili_uid,
                BilibiliLinkData.qq_number == qq_number,
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def delete_all_for_qq(self, qq_number: str) -> int:
        stmt = (
            delete(BilibiliLinkData)
            .where(BilibiliLinkData.qq_number == qq_number)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

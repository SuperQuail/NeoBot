"""SqlAlchemy profile repository (users + groups)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert

from neobot_storage.models import UserData, GroupData


class SqlAlchemyProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_user(self, user_id: str, **fields) -> None:
        stmt = insert(UserData).values(user_id=user_id, **fields)
        stmt = stmt.on_conflict_do_update(index_elements=["user_id"], set_=fields)
        await self._session.execute(stmt)

    async def upsert_group(self, group_id: str, **fields) -> None:
        stmt = insert(GroupData).values(group_id=group_id, **fields)
        stmt = stmt.on_conflict_do_update(index_elements=["group_id"], set_=fields)
        await self._session.execute(stmt)

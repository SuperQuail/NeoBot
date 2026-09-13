"""SqlAlchemy 档案仓库（用户 + 群组）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy import func, select, update

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

    async def user_exists(self, user_id: str) -> bool:
        stmt = select(UserData.user_id).where(UserData.user_id == user_id).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def group_exists(self, group_id: str) -> bool:
        stmt = select(GroupData.group_id).where(GroupData.group_id == group_id).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_user(self, user_id: str) -> UserData | None:
        stmt = select(UserData).where(UserData.user_id == user_id).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_group(self, group_id: str) -> GroupData | None:
        stmt = select(GroupData).where(GroupData.group_id == group_id).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    # ── 头像存储（spec(5) §4.9 / R33–R37）──────────────────────────
    # 头像与用户资料同表：「有 user_data 行 = 认识该用户」，调用方只查这一处。

    async def list_stale_avatars(
        self, cutoff: datetime, *, limit: int = 500
    ) -> list[UserData]:
        """列出「有本地头像且最后成功获取时间早于 cutoff」的用户。

        avatar_fetched_at 同时充当**最后活跃时间的代理**：用户只要再次出现在
        聊天流且超过 refresh_days 就会被刷新，因此活跃用户的 avatar_fetched_at
        最多滞后 refresh_days（默认 7 天）；早于 keep_days（默认 90 天）
        即说明他确实很久没出现过了。
        """
        stmt = (
            select(UserData)
            .where(UserData.avatar_path.is_not(None))
            .where(UserData.avatar_fetched_at.is_not(None))
            .where(UserData.avatar_fetched_at < cutoff)
            .order_by(UserData.avatar_fetched_at.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def bump_avatar_fail_count(self, user_id: str) -> None:
        """把失败次数 +1（原子自增；行不存在则建行）。

        用 INSERT .. ON CONFLICT DO UPDATE 而不是「读 → 改 → 写」：失败可能
        来自并发路径，自增必须由数据库保证，而且失败本身也要留下可诊断的痕迹。
        整个写入**不碰** avatar_path / avatar_fetched_at —— 失败不覆盖旧头像。
        """
        stmt = insert(UserData).values(user_id=user_id, avatar_fail_count=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "avatar_fail_count": func.coalesce(UserData.avatar_fail_count, 0) + 1
            },
        )
        await self._session.execute(stmt)

    async def clear_avatar(self, user_id: str) -> None:
        """清空某个用户的头像三列（保留 user_data 行本身，仍算「认识该用户」）。"""
        stmt = (
            update(UserData)
            .where(UserData.user_id == user_id)
            .values(avatar_path=None, avatar_fetched_at=None, avatar_fail_count=0)
        )
        await self._session.execute(stmt)

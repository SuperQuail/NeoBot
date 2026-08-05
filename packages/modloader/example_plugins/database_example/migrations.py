"""示例插件数据库迁移。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from .models import Base


async def create_initial_schema(connection: AsyncConnection) -> None:
    await connection.run_sync(Base.metadata.create_all)


async def add_user_index(connection: AsyncConnection) -> None:
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_example_users_name ON example_users(name)")
    )

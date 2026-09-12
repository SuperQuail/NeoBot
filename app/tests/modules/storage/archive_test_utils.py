"""档案存储/服务测试的公共工具：内存 SQLite 引擎。

刻意不使用 pytest 的 tmp_path：受限沙箱下对临时目录调用 os.scandir 会被拒，
而 sqlite 内存库 + StaticPool 既不需要任何临时文件，也能让多个 UoW 会话共享
同一个数据库，足够覆盖仓库层的 SQL 行为。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from neobot_storage.models import Base


def create_memory_engine() -> AsyncEngine:
    """创建一个进程内共享的 sqlite 异步引擎（所有会话看同一个内存库）。"""
    return create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


async def create_schema(engine: AsyncEngine) -> None:
    """建表（等价于生产迁移后的最终表结构）。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

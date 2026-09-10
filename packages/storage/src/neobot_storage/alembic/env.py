"""面向异步 SQLAlchemy 的 Alembic 环境。"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from neobot_storage.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_database_url() -> str:
    """解析数据库 URL：优先 ini（由 run_migrations 注入），其次命令行 -x db_url=...。

    不回退到相对路径，避免 alembic CLI 在源码目录生成 neobot.db 这类构建产物。
    """
    url = config.get_main_option("sqlalchemy.url") or ""
    if not url:
        url = context.get_x_argument(as_dictionary=True).get("db_url", "")
    if not url:
        raise RuntimeError(
            "未配置数据库 URL：应用启动时由 run_migrations(db_url) 注入；"
            "命令行请使用 alembic -x db_url=sqlite+aiosqlite:///<绝对路径>/neobot.db upgrade head"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_resolve_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_resolve_database_url())
    async with engine.connect() as conn:
        await conn.run_sync(
            lambda sync_conn: context.configure(
                connection=sync_conn,
                target_metadata=target_metadata,
            )
        )
        async with conn.begin():
            await conn.run_sync(lambda _: context.run_migrations())
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    try:
        asyncio.get_running_loop()
        # 已在 event loop 中（如 app 启动时调用），用新线程跑
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pool.submit(asyncio.run, run_migrations_online()).result()
    except RuntimeError:
        # 没有 event loop（CLI 直接调用）
        asyncio.run(run_migrations_online())

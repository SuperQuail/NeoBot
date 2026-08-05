"""示例插件：独立 SQLite 数据库（事务写入 / 会话查询）。"""

from __future__ import annotations

from sqlalchemy import select

from neobot_modloader import Migration, Plugin, Reply

from .migrations import add_user_index, create_initial_schema
from .models import Base, ExampleUser

plugin = Plugin(
    "example",
    version="1.0.0",
    description="Demo: plugin-owned SQLite database with migrations",
)

database = plugin.sqlite_database(
    "main",
    filename="example.db",
    metadata=Base.metadata,
    migrations=[
        Migration(1, "initial-schema", create_initial_schema),
        Migration(2, "add-user-index", add_user_index),
    ],
)


@plugin.command("example-user <name:rest>")
async def example_user(name: str, reply: Reply) -> None:
    async with database.transaction() as session:
        session.add(ExampleUser(name=name))
        await session.flush()
    await reply.send(f"已创建用户: {name}")


@plugin.command("example-users")
async def example_users(reply: Reply) -> None:
    async with database.session() as session:
        result = await session.execute(select(ExampleUser).order_by(ExampleUser.id))
        users = list(result.scalars())
    await reply.send("\n".join(f"{user.id}: {user.name}" for user in users) or "（暂无用户）")

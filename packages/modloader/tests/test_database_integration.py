from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.runtime import PluginRuntime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXAMPLE_PLUGIN = """\
from __future__ import annotations

from sqlalchemy import String, select, text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from neobot_modloader import Migration, Plugin, Reply


class Base(DeclarativeBase):
    pass


class ExampleUser(Base):
    __tablename__ = "example_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)


async def create_initial_schema(connection: AsyncConnection) -> None:
    await connection.run_sync(Base.metadata.create_all)


async def add_user_index(connection: AsyncConnection) -> None:
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_example_users_name ON example_users(name)")
    )


plugin = Plugin("example", version="1.0.0", description="demo")

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
    await reply.send("\\n".join(f"{user.id}: {user.name}" for user in users) or "（暂无用户）")
"""

EXAMPLE_MANIFEST = """\
name = "example"
version = "1.0.0"
description = "demo"
enabled = true

python_dependencies = ["sqlalchemy>=2.0", "aiosqlite>=0.20.0"]

[config]
page_size = 10
"""

BAD_MIGRATION_PLUGIN = """\
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from neobot_modloader import Migration, Plugin


async def good_migration(connection: AsyncConnection) -> None:
    await connection.execute(text("CREATE TABLE good_t (id INTEGER PRIMARY KEY)"))


async def bad_migration(connection: AsyncConnection) -> None:
    raise RuntimeError("boom-migration")


plugin = Plugin("baddb", version="1.0.0")

database = plugin.sqlite_database(
    "main",
    filename="bad.db",
    migrations=[
        Migration(1, "good", good_migration),
        Migration(2, "bad", bad_migration),
    ],
)
"""

BAD_MIGRATION_MANIFEST = """\
name = "baddb"
version = "1.0.0"
enabled = true
"""


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeLoggerFactory:
    def get_logger(self, name: str) -> Any:
        return FakeLogger()


class DispatchCtx:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class FakeAgentRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    @property
    def names(self) -> list[str]:
        return list(self.agents)

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        return self.agents.pop(name, None)

    async def delegate(self, agent: str, task: str, context: str = "") -> str:
        result = await self.agents[agent].invoke(
            {
                "messages": [{"role": "user", "content": task}],
                "_delegate_context": context,
            }
        )
        return str(result["messages"][-1]["content"])


class DatabaseIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin_dir = Path(self.tmp.name) / "plugins"
        self.data_dir = Path(self.tmp.name) / "data"
        self.plugin_dir.mkdir()
        self.data_dir.mkdir()

        self.mock_adapter = AsyncMock()
        self.hook_bus = PluginHookBus()
        self.agent_registry = FakeAgentRegistry()
        self.runtime = PluginRuntime(
            plugin_dir=self.plugin_dir,
            data_dir=self.data_dir,
            adapter=self.mock_adapter,
            logger_factory=FakeLoggerFactory(),
            hook_bus=self.hook_bus,
            agent_registry=self.agent_registry,
        )

    async def asyncTearDown(self) -> None:
        await self.runtime.stop_all()
        self.tmp.cleanup()

    def _write_pkg(self, name: str, init_py: str, manifest: str | None = None) -> None:
        package = self.plugin_dir / name
        package.mkdir()
        if manifest is not None:
            (package / "plugin.toml").write_text(manifest, encoding="utf-8")
        (package / "__init__.py").write_text(init_py, encoding="utf-8")

    async def _dispatch(self, raw_event: dict[str, Any]) -> DispatchCtx:
        ctx = DispatchCtx(raw_event)
        await self.hook_bus.dispatch(ctx)
        return ctx

    async def _migration_count(self, plugin_name: str, filename: str) -> int:
        path = self.data_dir / plugin_name / "databases" / filename
        engine = create_async_engine(f"sqlite+aiosqlite:///{path.as_posix()}")
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT COUNT(*) FROM _neobot_plugin_migrations")
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    async def _load_and_start(self, name: str) -> None:
        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

    async def test_e2e_database_plugin_commands(self) -> None:
        self._write_pkg("example", textwrap.dedent(EXAMPLE_PLUGIN), EXAMPLE_MANIFEST)
        await self._load_and_start("example")

        db_path = self.data_dir / "example" / "databases" / "example.db"
        self.assertTrue(db_path.is_file())
        self.assertEqual(await self._migration_count("example", "example.db"), 2)

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-user 小明",
            }
        )
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "已创建用户: 小明")

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-users",
            }
        )
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "1: 小明")

    async def test_migration_failure_puts_plugin_in_error(self) -> None:
        self._write_pkg(
            "baddb", textwrap.dedent(BAD_MIGRATION_PLUGIN), BAD_MIGRATION_MANIFEST
        )
        self.runtime.load_all()
        await self.runtime.load_registered()

        record = self.runtime.manager.get_record("baddb")
        self.assertIsNotNone(record)
        self.assertEqual(record.state, PluginState.ERROR)
        message = str(record.error)
        self.assertIn("baddb", message)
        self.assertIn("v2", message)
        self.assertIn("RuntimeError", message)

        await self.runtime.start_all()
        self.assertEqual(record.state, PluginState.ERROR)

    async def test_reload_does_not_reapply_migrations(self) -> None:
        self._write_pkg("example", textwrap.dedent(EXAMPLE_PLUGIN), EXAMPLE_MANIFEST)
        await self._load_and_start("example")

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-user 小明",
            }
        )

        result = await self.runtime.reload_plugin_result("example", start=True)
        self.assertTrue(result.ok)

        self.assertEqual(await self._migration_count("example", "example.db"), 2)

        self.mock_adapter.send.reset_mock()
        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-users",
            }
        )
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "1: 小明")

    async def test_unload_keeps_file_and_closes_database(self) -> None:
        self._write_pkg("example", textwrap.dedent(EXAMPLE_PLUGIN), EXAMPLE_MANIFEST)
        await self._load_and_start("example")

        record = self.runtime.manager.get_record("example")
        database = record.plugin._databases["main"]
        db_path = self.data_dir / "example" / "databases" / "example.db"
        self.assertTrue(db_path.is_file())

        result = await self.runtime.unload_plugin("example")
        self.assertTrue(result.ok)

        self.assertEqual(database.state, "closed")
        self.assertTrue(db_path.is_file())

    async def test_example_plugin_end_to_end(self) -> None:
        import shutil

        source = (
            Path(__file__).resolve().parent.parent
            / "example_plugins"
            / "database_example"
        )
        shutil.copytree(
            source,
            self.plugin_dir / "database_example",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        await self._load_and_start("example")

        db_path = self.data_dir / "example" / "databases" / "example.db"
        self.assertTrue(db_path.is_file())
        self.assertEqual(await self._migration_count("example", "example.db"), 2)

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-user 小明",
            }
        )
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "已创建用户: 小明")

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "/example-users",
            }
        )
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "1: 小明")


if __name__ == "__main__":
    unittest.main()

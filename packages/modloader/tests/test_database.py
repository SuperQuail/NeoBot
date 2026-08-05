from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from neobot_modloader import Plugin
from neobot_modloader.database import (
    Migration,
    PluginDatabase,
    PluginDatabaseClosedError,
    PluginDatabaseError,
    PluginDatabaseNotReadyError,
    PluginMigrationConflictError,
    PluginMigrationError,
    _migration_checksum,
)


async def _migrate_v1_users(connection: AsyncConnection) -> None:
    await connection.execute(
        text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    )


async def _migrate_v2_age(connection: AsyncConnection) -> None:
    await connection.execute(text("ALTER TABLE users ADD COLUMN age INTEGER"))


async def _migrate_v3_email(connection: AsyncConnection) -> None:
    await connection.execute(text("ALTER TABLE users ADD COLUMN email TEXT"))


async def _migrate_v1_alt(connection: AsyncConnection) -> None:
    await connection.execute(
        text("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, extra TEXT)")
    )


async def _migrate_failing(connection: AsyncConnection) -> None:
    await connection.execute(
        text("CREATE TABLE partial_v2 (id INTEGER PRIMARY KEY)")
    )
    raise RuntimeError("migration exploded")


async def _migrate_slow(connection: AsyncConnection) -> None:
    await asyncio.sleep(0.05)
    await connection.execute(text("CREATE TABLE slow_t (id INTEGER PRIMARY KEY)"))


async def _migration_count(db_path: Path) -> int:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM _neobot_plugin_migrations")
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


class FilenameValidationTest(unittest.TestCase):
    def test_rejects_dangerous_filenames(self) -> None:
        bad = [
            "../x.db",
            "C:\\x.db",
            "c:/x.db",
            "\\\\server\\share\\x.db",
            "//server/share/x.db",
            "/abs/x.db",
            "a/b.db",
            "a\\b.db",
            "x:y.db",
            "neobot.db",
            "NEOBOT.DB",
            "",
        ]
        for filename in bad:
            with self.subTest(filename=filename):
                with self.assertRaises(PluginDatabaseError):
                    PluginDatabase("p", "main", filename=filename)

    def test_rejects_windows_normalization_traps(self) -> None:
        # NTFS 会把尾部的点/空格剥离、把设备名当作保留设备，导致
        # "x.db." / "x.db " 与 "x.db" 落在同一个文件上、".. " 变体指向父目录。
        bad = [
            "x.db.",
            "x.db ",
            "x.db. ",
            "...",
            ".. ",
            ". ",
            "con.db",
            "CON",
            "nul.db",
            "com1.db",
            "lpt9.db",
            "aux.sqlite3",
            "prn",
        ]
        for filename in bad:
            with self.subTest(filename=filename):
                with self.assertRaises(PluginDatabaseError):
                    PluginDatabase("p", "main", filename=filename)

    def test_rejects_dot_extended_device_names(self) -> None:
        # Windows 保留设备名按第一个点之前的组件判定：con.txt.db / nul.foo.db
        # 会被当作设备打开（sqlite 连接会挂起或失败），必须与 con.db 一并拒绝。
        for filename in ("con.txt.db", "nul.foo.db", "com1.backup.db", "lpt2.log"):
            with self.subTest(filename=filename):
                with self.assertRaises(PluginDatabaseError):
                    PluginDatabase("p", "main", filename=filename)

    def test_rejects_invalid_windows_characters(self) -> None:
        for filename in ('a<b.db', 'a>b.db', 'a"b.db', "a|b.db", "a?b.db", "a*b.db"):
            with self.subTest(filename=filename):
                with self.assertRaises(PluginDatabaseError):
                    PluginDatabase("p", "main", filename=filename)

    def test_accepts_safe_filenames(self) -> None:
        for filename in ("main.sqlite3", "x.db", "a-b_c.1.db", "convention.db", "x.con.db"):
            database = PluginDatabase("p", "main", filename=filename)
            self.assertEqual(database.filename, filename)

    def test_rejects_invalid_migrations_and_name(self) -> None:
        async def upgrade(connection: AsyncConnection) -> None:
            pass

        for version in (0, -1, "1", True):
            with self.subTest(version=version):
                with self.assertRaises(PluginDatabaseError):
                    PluginDatabase(
                        "p",
                        "main",
                        filename="x.db",
                        migrations=[Migration(version, "m", upgrade)],
                    )
        with self.assertRaises(PluginDatabaseError):
            PluginDatabase(
                "p",
                "main",
                filename="x.db",
                migrations=[
                    Migration(1, "a", upgrade),
                    Migration(1, "b", upgrade),
                ],
            )
        with self.assertRaises(PluginDatabaseError):
            PluginDatabase("p", "", filename="x.db")


class DatabaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.databases_dir = Path(self.tmp.name) / "databases"
        self.databases_dir.mkdir()
        self.other_dir = Path(self.tmp.name) / "outside"
        self.other_dir.mkdir()
        self.db_path = self.databases_dir / "test.db"
        self._dbs: list[PluginDatabase] = []

    async def asyncTearDown(self) -> None:
        for database in self._dbs:
            await database.close()
        for database in self._dbs:
            if database.path is None:
                continue
            for suffix in ("", "-wal", "-shm"):
                target = Path(f"{database.path}{suffix}")
                for _ in range(40):
                    try:
                        target.unlink(missing_ok=True)
                        break
                    except PermissionError:
                        await asyncio.sleep(0.05)
        self.tmp.cleanup()

    def _database(
        self,
        *,
        filename: str = "test.db",
        migrations: tuple[Migration, ...] = (
            Migration(1, "users", _migrate_v1_users),
            Migration(2, "age", _migrate_v2_age),
        ),
        pragmas: dict[str, str] | None = None,
    ) -> PluginDatabase:
        database = PluginDatabase(
            "demo",
            "main",
            filename=filename,
            migrations=migrations,
            pragmas=pragmas,
        )
        self._dbs.append(database)
        return database

    async def test_bind_executes_migrations_in_order_and_is_idempotent(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)

        self.assertEqual(database.state, "ready")
        self.assertIsNotNone(database.engine)
        self.assertTrue(database.url.startswith("sqlite+aiosqlite:///"))
        self.assertTrue(self.db_path.is_file())

        rows = await self._applied_versions(database)
        self.assertEqual([version for version, _ in rows], [1, 2])
        self.assertTrue(all(applied_at for _, applied_at in rows))

        async with database.session() as session:
            result = await session.execute(text("PRAGMA table_info(users)"))
            columns = [row[1] for row in result]
        self.assertEqual(columns, ["id", "name", "age"])

        await database.bind(self.databases_dir)
        self.assertEqual(database.state, "ready")

    async def test_migrate_is_idempotent(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)
        rows = await self._applied_versions(database)
        self.assertEqual(len(rows), 2)
        await database.migrate()
        rows = await self._applied_versions(database)
        self.assertEqual(len(rows), 2)

    async def test_failed_migration_rolls_back_and_blocks_startup(self) -> None:
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(2, "failing", _migrate_failing),
            )
        )
        for attempt in range(2):
            with self.assertRaises(PluginMigrationError) as ctx:
                await database.bind(self.databases_dir)
            message = str(ctx.exception)
            self.assertIn("demo", message)
            self.assertIn("main", message)
            self.assertIn("v2", message)
            self.assertIn("failing", message)
            self.assertIn("RuntimeError", message)
            self.assertEqual(database.state, "unbound")

        self.assertEqual(await _migration_count(self.db_path), 1)
        engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path.as_posix()}")
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='partial_v2'")
                )
                self.assertIsNone(result.first())
        finally:
            await engine.dispose()

    async def test_checksum_conflict_detected(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)

        conflicting = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(Migration(1, "users", _migrate_v1_alt),),
        )
        self._dbs.append(conflicting)
        with self.assertRaises(PluginMigrationConflictError):
            await conflicting.bind(self.databases_dir)

    async def test_removed_or_reordered_migration_rejected(self) -> None:
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(3, "age", _migrate_v2_age),
            )
        )
        await database.bind(self.databases_dir)

        reordered = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(2, "age", _migrate_v2_age),
            ),
        )
        self._dbs.append(reordered)
        with self.assertRaises(PluginMigrationError):
            await reordered.bind(self.databases_dir)

    async def test_removed_highest_applied_migration_rejected(self) -> None:
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(2, "age", _migrate_v2_age),
            )
        )
        await database.bind(self.databases_dir)

        truncated = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(Migration(1, "users", _migrate_v1_users),),
        )
        self._dbs.append(truncated)
        with self.assertRaises(PluginMigrationError) as ctx:
            await truncated.bind(self.databases_dir)
        message = str(ctx.exception)
        self.assertIn("demo", message)
        self.assertIn("main", message)
        self.assertIn("2", message)

    async def test_removed_middle_applied_migration_rejected(self) -> None:
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(2, "age", _migrate_v2_age),
                Migration(3, "email", _migrate_v3_email),
            )
        )
        await database.bind(self.databases_dir)
        rows = await self._applied_versions(database)
        self.assertEqual([version for version, _ in rows], [1, 2, 3])

        truncated = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(3, "email", _migrate_v3_email),
            ),
        )
        self._dbs.append(truncated)
        with self.assertRaises(PluginMigrationError) as ctx:
            await truncated.bind(self.databases_dir)
        message = str(ctx.exception)
        self.assertIn("demo", message)
        self.assertIn("main", message)
        self.assertIn("2", message)

    async def test_inserted_migration_below_max_applied_rejected_accurately(self) -> None:
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(3, "email", _migrate_v3_email),
            )
        )
        await database.bind(self.databases_dir)

        reinserted = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(2, "age", _migrate_v2_age),
                Migration(3, "email", _migrate_v3_email),
            ),
        )
        self._dbs.append(reinserted)
        with self.assertRaises(PluginMigrationError) as ctx:
            await reinserted.bind(self.databases_dir)
        message = str(ctx.exception)
        self.assertIn("demo", message)
        self.assertIn("main", message)
        self.assertIn("2", message)
        # 版本 2 从未应用过：错误不能把它描述成"已应用的迁移被删除"
        self.assertNotIn("删除", message)

    async def test_multi_violation_reports_insertion_not_removal(self) -> None:
        # 同一迁移列表同时插入低于最高已应用版本的迁移（v2）并删除已应用迁移（v1），
        # 应报告插入式重排而非把 v2 误报为"已应用的迁移被删除"。
        database = self._database(
            migrations=(
                Migration(1, "users", _migrate_v1_users),
                Migration(3, "email", _migrate_v3_email),
            )
        )
        await database.bind(self.databases_dir)

        violated = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(
                Migration(2, "age", _migrate_v2_age),
                Migration(3, "email", _migrate_v3_email),
            ),
        )
        self._dbs.append(violated)
        with self.assertRaises(PluginMigrationError) as ctx:
            await violated.bind(self.databases_dir)
        message = str(ctx.exception)
        self.assertIn("2", message)
        self.assertNotIn("删除", message)

    async def test_conflict_takes_priority_over_removed_migration(self) -> None:
        # 同一次迁移列表既有校验和冲突（v2）又删除了已应用迁移（v1），
        # 应优先报告校验和冲突且信息指向 v2。
        database = self._database()
        await database.bind(self.databases_dir)

        async def _migrate_v2_age_alt(connection: AsyncConnection) -> None:
            await connection.execute(text("ALTER TABLE users ADD COLUMN age TEXT"))

        conflicting = PluginDatabase(
            "demo",
            "main",
            filename="test.db",
            migrations=(Migration(2, "age", _migrate_v2_age_alt),),
        )
        self._dbs.append(conflicting)
        with self.assertRaises(PluginMigrationConflictError) as ctx:
            await conflicting.bind(self.databases_dir)
        message = str(ctx.exception)
        self.assertIn("v2", message)
        self.assertIn("age", message)

    async def test_migrate_failure_then_success_reuses_connection(self) -> None:
        # 迁移失败回滚后，同一引擎的连接归还池并被后续迁移复用：
        # 复用路径上不得出现重复 BEGIN（"cannot start a transaction within a transaction"）。
        database = self._database(
            migrations=(Migration(1, "users", _migrate_v1_users),)
        )
        await database.bind(self.databases_dir)
        database._migrations = (
            Migration(1, "users", _migrate_v1_users),
            Migration(2, "failing", _migrate_failing),
        )
        with self.assertRaises(PluginMigrationError):
            await database.migrate()
        database._migrations = (
            Migration(1, "users", _migrate_v1_users),
            Migration(2, "age", _migrate_v2_age),
        )
        await database.migrate()
        rows = await self._applied_versions(database)
        self.assertEqual([version for version, _ in rows], [1, 2])

    async def test_concurrent_migrate_applies_only_once(self) -> None:
        database = PluginDatabase("demo", "main", filename="test.db")
        self._dbs.append(database)
        await database.bind(self.databases_dir)
        database._migrations = (Migration(1, "slow", _migrate_slow),)
        await asyncio.gather(database.migrate(), database.migrate())
        self.assertEqual(await _migration_count(self.db_path), 1)

    async def test_session_does_not_autocommit(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)

        async with database.session() as session:
            await session.execute(text("INSERT INTO users (id, name) VALUES (1, '小明')"))
        async with database.session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            self.assertEqual(int(result.scalar_one()), 0)

    async def test_transaction_commits_and_rolls_back(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)

        async with database.transaction() as session:
            await session.execute(text("INSERT INTO users (id, name) VALUES (1, '小明')"))
        async with database.session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            self.assertEqual(int(result.scalar_one()), 1)

        with self.assertRaises(RuntimeError):
            async with database.transaction() as session:
                await session.execute(text("INSERT INTO users (id, name) VALUES (2, '小红')"))
                raise RuntimeError("boom")
        async with database.session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            self.assertEqual(int(result.scalar_one()), 1)

    async def test_close_idempotent_and_retryable(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)

        await database.close()
        self.assertEqual(database.state, "closed")
        await database.close()
        self.assertEqual(database.state, "closed")

        revived = self._database()
        await revived.bind(self.databases_dir)
        real_dispose = AsyncEngine.dispose
        calls = {"n": 0}

        async def flaky_dispose(engine: AsyncEngine) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("dispose failed")
            await real_dispose(engine)

        with patch.object(AsyncEngine, "dispose", flaky_dispose):
            with self.assertRaises(RuntimeError):
                await revived.close()
        self.assertEqual(revived.state, "ready")
        self.assertIsInstance(revived._close_error, RuntimeError)

        await revived.close()
        self.assertEqual(revived.state, "closed")
        self.assertIsNone(revived._close_error)

    async def test_close_unbound_marks_closed(self) -> None:
        database = self._database()
        await database.close()
        self.assertEqual(database.state, "closed")

    async def test_usage_before_bind_and_after_close(self) -> None:
        database = self._database()
        with self.assertRaises(PluginDatabaseNotReadyError):
            await database.session().__aenter__()
        with self.assertRaises(PluginDatabaseNotReadyError):
            await database.transaction().__aenter__()
        with self.assertRaises(PluginDatabaseNotReadyError):
            await database.migrate()

        await database.bind(self.databases_dir)
        await database.close()
        with self.assertRaises(PluginDatabaseClosedError):
            await database.session().__aenter__()
        with self.assertRaises(PluginDatabaseClosedError):
            await database.transaction().__aenter__()

    async def test_host_pragmas_forced_and_plugin_pragmas_applied(self) -> None:
        database = self._database(
            pragmas={"cache_size": 100, "journal_mode": "DELETE", "foreign_keys": "OFF"}
        )
        await database.bind(self.databases_dir)

        async with database.session() as session:
            result = await session.execute(text("PRAGMA foreign_keys"))
            self.assertEqual(int(result.scalar_one()), 1)
            result = await session.execute(text("PRAGMA journal_mode"))
            self.assertEqual(str(result.scalar_one()).lower(), "wal")
            result = await session.execute(text("PRAGMA busy_timeout"))
            self.assertEqual(int(result.scalar_one()), 5000)
            result = await session.execute(text("PRAGMA cache_size"))
            self.assertEqual(int(result.scalar_one()), 100)

    async def test_file_symlink_escape_rejected(self) -> None:
        escape_target = self.other_dir / "evil.db"
        escape_target.write_text("not a db", encoding="utf-8")
        link = self.databases_dir / "test.db"
        try:
            link.symlink_to(escape_target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink 不可用: {exc}")

        database = self._database()
        with self.assertRaises(PluginDatabaseError):
            await database.bind(self.databases_dir)

    async def test_directory_symlink_or_junction_escape_rejected(self) -> None:
        dir_link = self.databases_dir / "dir.db"
        try:
            dir_link.symlink_to(self.other_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            import subprocess

            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(dir_link), str(self.other_dir)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not dir_link.is_dir():
                self.skipTest("目录 symlink/junction 不可用")
        database = self._database(filename="dir.db")
        self._dbs.append(database)
        with self.assertRaises(PluginDatabaseError):
            await database.bind(self.databases_dir)

    async def test_cross_plugin_isolation(self) -> None:
        dir_a = self.databases_dir / "plugin_a"
        dir_b = self.databases_dir / "plugin_b"
        db_a = PluginDatabase("plugin_a", "main", filename="shared.db")
        db_b = PluginDatabase("plugin_b", "main", filename="shared.db")
        self._dbs.extend([db_a, db_b])
        await db_a.bind(dir_a)
        await db_b.bind(dir_b)

        self.assertEqual(db_a.path.parent, dir_a.resolve())
        self.assertEqual(db_b.path.parent, dir_b.resolve())
        self.assertNotEqual(db_a.path, db_b.path)
        self.assertTrue(db_a.path.is_file())
        self.assertTrue(db_b.path.is_file())
        self.assertFalse(db_a.path.parent == db_b.path.parent)

    async def test_in_flight_query_survives_close(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)
        entered = asyncio.Event()

        async def slow_query() -> str:
            async with database.session() as session:
                # 先执行一次查询强制借出连接：保证 close 时连接在途、归还发生在
                # dispose 之后。晚归还连接必须被真正关闭，否则 Windows 上文件
                # 会被永久锁住（旧实现下该时序依赖 sleep 竞态，偶发失败）。
                await session.execute(text("SELECT 1"))
                entered.set()
                await asyncio.sleep(0.05)
                result = await session.execute(text("SELECT sqlite_version()"))
                return str(result.scalar_one())

        task = asyncio.create_task(slow_query())
        await entered.wait()
        await database.close()
        result = await task
        self.assertTrue(result)
        self.assertEqual(database.state, "closed")

    async def test_plugin_sqlite_database_registration(self) -> None:
        plugin = Plugin("demo_plugin")
        first = plugin.sqlite_database("main", filename="a.db")
        self.assertEqual(first.plugin_name, "demo_plugin")
        self.assertEqual(first.filename, "a.db")
        with self.assertRaises(ValueError):
            plugin.sqlite_database("main", filename="b.db")
        defaulted = plugin.sqlite_database("cache")
        self.assertEqual(defaulted.filename, "cache.sqlite3")
        self.assertEqual(set(plugin._databases), {"main", "cache"})

    async def test_bind_failure_preserves_migration_error_when_dispose_also_fails(self) -> None:
        database = self._database(
            migrations=(Migration(1, "failing", _migrate_failing),)
        )
        real_dispose = AsyncEngine.dispose

        async def broken_dispose(engine: AsyncEngine) -> None:
            await real_dispose(engine)
            raise RuntimeError("dispose boom")

        with patch.object(AsyncEngine, "dispose", broken_dispose):
            with self.assertRaises(PluginMigrationError) as ctx:
                await database.bind(self.databases_dir)
        self.assertIn("RuntimeError", str(ctx.exception))
        self.assertNotIn("dispose boom", str(ctx.exception))
        self.assertEqual(database.state, "unbound")
        self.assertIsNone(database.engine)
        self.assertIsNone(database.path)

    async def test_bind_after_close_reopens_same_file(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)
        async with database.transaction() as session:
            await session.execute(text("INSERT INTO users (id, name) VALUES (1, '小明')"))
        await database.close()
        self.assertEqual(database.state, "closed")

        await database.bind(self.databases_dir)
        self.assertEqual(database.state, "ready")
        async with database.session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            self.assertEqual(int(result.scalar_one()), 1)
            result = await session.execute(text("PRAGMA journal_mode"))
            self.assertEqual(str(result.scalar_one()).lower(), "wal")
        rows = await self._applied_versions(database)
        self.assertEqual([version for version, _ in rows], [1, 2])

    async def test_rebind_after_close_disposes_old_engine_connections(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)
        old_engine = database.engine
        await database.close()
        # 已关闭的旧引擎池仍可用（dispose 后按需重建连接），
        # 这会产生一条存活连接；重新 bind 时旧引擎不能遗留它。
        await database.migrate()
        self.assertEqual(old_engine.sync_engine.pool.checkedin(), 1)

        await database.bind(self.databases_dir)
        self.assertIsNot(database.engine, old_engine)
        await database.close()

        pool = old_engine.sync_engine.pool
        self.assertEqual(pool.checkedin(), 0)
        # Windows 上文件锁依赖连接真正释放
        for _ in range(40):
            try:
                self.db_path.unlink()
                break
            except PermissionError:
                await asyncio.sleep(0.05)
        else:
            self.fail("数据库文件在关闭后仍被旧引擎连接锁住")

    async def test_pool_reuse_does_not_duplicate_begin(self) -> None:
        database = self._database()
        await database.bind(self.databases_dir)
        # 未提交会话归还连接后复用同一连接，不应出现重复 BEGIN
        async with database.session() as session:
            await session.execute(text("INSERT INTO users (id, name) VALUES (1, 'a')"))
        async with database.session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM users"))
            self.assertEqual(int(result.scalar_one()), 0)
        await database.migrate()
        # 关闭时有 in-flight 会话；连接晚归还后继续复用
        entered = asyncio.Event()

        async def slow_query() -> int:
            async with database.session() as session:
                # 先借出连接再进入等待：确保 close 时该连接在途（晚归还），
                # 使文件解锁不依赖 sleep 与 close 的时序竞态。
                await session.execute(text("SELECT 1"))
                entered.set()
                await asyncio.sleep(0.05)
                result = await session.execute(text("SELECT 1"))
                return int(result.scalar_one())

        task = asyncio.create_task(slow_query())
        await entered.wait()
        await database.close()
        self.assertEqual(await task, 1)
        await database.migrate()

    async def test_sqlite_database_rejects_duplicate_filename(self) -> None:
        plugin = Plugin("dup_filename")
        plugin.sqlite_database("main", filename="a.db")
        with self.assertRaises(ValueError):
            plugin.sqlite_database("cache", filename="a.db")
        with self.assertRaises(ValueError):
            plugin.sqlite_database("cache2", filename="A.DB")
        plugin.sqlite_database("cache3", filename="b.db")

    async def test_bind_databases_partial_failure_rolls_back_and_retries(self) -> None:
        plugin = Plugin("rollback_db")
        good = plugin.sqlite_database("good", filename="good.db")
        calls = {"n": 0}

        async def flaky_upgrade(connection: AsyncConnection) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("flaky boom")
            await _migrate_v1_users(connection)

        bad = plugin.sqlite_database(
            "bad", filename="bad.db", migrations=(Migration(1, "flaky", flaky_upgrade),)
        )
        self._dbs.extend([good, bad])
        plugin._context = SimpleNamespace(data_dir=Path(self.tmp.name))

        with self.assertRaises(PluginMigrationError):
            await plugin._bind_databases()
        self.assertEqual(good.state, "closed")
        self.assertEqual(bad.state, "unbound")

        await plugin._bind_databases()
        self.assertEqual(good.state, "ready")
        self.assertEqual(bad.state, "ready")
        good_path = Path(self.tmp.name) / "databases" / "good.db"
        self.assertTrue(good_path.is_file())

    async def test_checksum_fallback_distinguishes_dynamic_functions(self) -> None:
        first = eval("lambda c: None")
        second = eval("lambda c: c.execute('SELECT 1')")
        a = _migration_checksum(Migration(1, "a", first))
        b = _migration_checksum(Migration(1, "a", second))
        self.assertNotEqual(a, b)

    async def _applied_versions(self, database: PluginDatabase) -> list[tuple[int, str]]:
        async with database.session() as session:
            result = await session.execute(
                text("SELECT version, applied_at FROM _neobot_plugin_migrations ORDER BY version")
            )
            return [(int(row[0]), str(row[1])) for row in result]


if __name__ == "__main__":
    unittest.main()

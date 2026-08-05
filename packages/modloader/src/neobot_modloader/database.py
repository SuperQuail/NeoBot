"""插件独立 SQLite 数据库（SQLAlchemy Async + aiosqlite）。

插件在模块加载时通过 ``Plugin.sqlite_database(...)`` 声明数据库；真正的初始化
（引擎创建、PRAGMA、migration）发生在插件 ``_load`` 阶段（``PluginDatabase.bind``）。
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import MetaData, event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

_MIGRATION_TABLE = "_neobot_plugin_migrations"
_CREATE_MIGRATION_TABLE = (
    f"CREATE TABLE IF NOT EXISTS {_MIGRATION_TABLE} "
    "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
    "checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
)
_HOST_PRAGMAS = {"journal_mode", "foreign_keys", "busy_timeout", "synchronous"}
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_WINDOWS_RESERVED_NAMES = {"con", "prn", "aux", "nul"} | {
    f"com{i}" for i in range(1, 10)
} | {f"lpt{i}" for i in range(1, 10)}


@dataclass(frozen=True)
class Migration:
    """数据库迁移：按 version 升序在独立事务中执行。"""

    version: int
    name: str
    upgrade: Callable[[AsyncConnection], Awaitable[None]]


class PluginDatabaseError(RuntimeError):
    pass


class PluginDatabaseNotReadyError(PluginDatabaseError):
    pass


class PluginDatabaseClosedError(PluginDatabaseError):
    pass


class PluginMigrationError(PluginDatabaseError):
    pass


class PluginMigrationConflictError(PluginMigrationError):
    pass


def _migration_checksum(migration: Migration) -> str:
    try:
        source = inspect.getsource(migration.upgrade)
    except (OSError, TypeError):
        code = migration.upgrade.__code__
        source = (
            f"{migration.upgrade.__module__}.{migration.upgrade.__qualname__}"
            f"|{code.co_filename}:{code.co_firstlineno}|{code.co_code.hex()}"
        )
    return hashlib.sha256(
        f"{migration.version}|{migration.name}|{source}".encode()
    ).hexdigest()


class PluginDatabase:
    """插件声明式 SQLite 数据库。状态机: unbound -> ready -> closed。"""

    def __init__(
        self,
        plugin_name: str,
        name: str,
        *,
        filename: str,
        metadata: MetaData | None = None,
        migrations: Sequence[Migration] = (),
        pragmas: Mapping[str, str] | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._name = name
        self._metadata = metadata
        self._pragmas = dict(pragmas or {})
        self._validate_name()
        self._migrations = tuple(migrations)
        self._validate_migrations()
        self._validate_filename(filename)
        self._filename = filename
        self._state = "unbound"
        self._migration_lock: asyncio.Lock | None = None
        self._close_error: Exception | None = None
        self.path: Path | None = None
        self.url: str = ""
        self.engine: AsyncEngine | None = None

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def state(self) -> str:
        return self._state

    @property
    def migrations(self) -> tuple[Migration, ...]:
        return self._migrations

    def _validate_name(self) -> None:
        if not isinstance(self._name, str) or not self._name.strip():
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库名不能为空"
            )

    def _validate_migrations(self) -> None:
        seen: set[int] = set()
        for migration in self._migrations:
            version = migration.version
            if isinstance(version, bool) or not isinstance(version, int) or version <= 0:
                raise PluginDatabaseError(
                    f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 的迁移版本必须为正整数: {version!r}"
                )
            if version in seen:
                raise PluginDatabaseError(
                    f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 存在重复的迁移版本: {version}"
                )
            seen.add(version)

    def _validate_filename(self, filename: str) -> None:
        if not isinstance(filename, str) or not filename:
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能为空"
            )
        separators = ("/", "\\", os.sep, os.altsep)
        if any(separator is not None and separator in filename for separator in separators):
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能包含路径分隔符: {filename!r}"
            )
        if filename.startswith(("\\\\", "//")):
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能是 UNC 路径: {filename!r}"
            )
        if _DRIVE_RE.match(filename):
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能是绝对路径: {filename!r}"
            )
        if ":" in filename:
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能包含冒号: {filename!r}"
            )
        if any(char in filename for char in '<>"|?*'):
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名包含 Windows 非法字符: {filename!r}"
            )
        if ".." in Path(filename).parts:
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能包含父目录引用: {filename!r}"
            )
        if filename != filename.rstrip(" ."):
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能以空格或点结尾: {filename!r}"
            )
        # Windows 保留设备名按第一个点之前的组件判定（"con.txt.db" 会被当作设备打开）。
        if filename.partition(".")[0].lower() in _WINDOWS_RESERVED_NAMES:
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名不能使用 Windows 保留设备名: {filename!r}"
            )
        if filename.lower() == "neobot.db":
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 文件名 {filename!r} 为宿主保留名"
            )

    @staticmethod
    async def _dispose_engine(engine: AsyncEngine) -> None:
        """Dispose 引擎并确保在途连接归还后真正关闭。

        ``QueuePool.dispose`` 只关闭归还时已在池中的连接；dispose 之后才归还的
        借用连接会被旧池静默保留、永不关闭（Windows 上会永久锁住数据库文件）。
        这里在归还（checkin）时直接关闭连接，保证 close/重开时仍持有连接的
        查询结束后文件能立即解锁。
        """

        pool = engine.sync_engine.pool

        @event.listens_for(pool, "checkin")
        def _close_late_returns(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            if connection_record.dbapi_connection is not None:
                connection_record.close()

        await engine.dispose()

    async def bind(self, databases_dir: Path) -> None:
        if self._state == "ready":
            return
        if self.engine is not None:
            # 重开（stop→load 同对象重载或 close 后二次 bind）时丢弃旧引擎：
            # 其池中可能仍有晚归还的存活连接（Windows 上会锁住文件），best-effort 释放。
            try:
                await self._dispose_engine(self.engine)
            except BaseException:
                pass
        resolved_dir = Path(databases_dir).resolve()
        path = (resolved_dir / self._filename).resolve()
        if path.parent != resolved_dir:
            raise PluginDatabaseError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 路径越界: {path}"
            )
        self.path = path
        self.url = f"sqlite+aiosqlite:///{path.as_posix()}"
        resolved_dir.mkdir(parents=True, exist_ok=True)
        engine = create_async_engine(
            self.url,
            connect_args={"timeout": 5},
        )
        self.engine = engine
        self._install_pragmas(engine)
        self._migration_lock = asyncio.Lock()
        try:
            await self.migrate()
        except BaseException:
            try:
                await self._dispose_engine(engine)
            except BaseException:
                pass
            self.engine = None
            self.path = None
            self.url = ""
            self._migration_lock = None
            self._state = "unbound"
            raise
        self._state = "ready"

    def _install_pragmas(self, engine: AsyncEngine) -> None:
        plugin_name = self._plugin_name
        database_name = self._name
        pragmas = dict(self._pragmas)

        @event.listens_for(engine.sync_engine, "connect")
        def _set_pragmas(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                row = cursor.fetchone()
                if row is None or str(row[0]).lower() != "wal":
                    raise PluginDatabaseError(
                        f"插件 {plugin_name!r} 的数据库 {database_name!r} 无法启用 WAL 日志模式: "
                        f"journal_mode={row[0] if row is not None else 'unknown'}"
                    )
            except Exception as exc:
                if isinstance(exc, PluginDatabaseError):
                    raise
                raise PluginDatabaseError(
                    f"插件 {plugin_name!r} 的数据库 {database_name!r} 启用 WAL 日志模式失败: "
                    f"{type(exc).__name__}"
                ) from exc
            finally:
                cursor.close()
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                for key, value in pragmas.items():
                    if key.lower() in _HOST_PRAGMAS:
                        continue
                    cursor.execute(f"PRAGMA {key}={value}")
            finally:
                cursor.close()

        # pysqlite 方言依赖 DBAPI 隐式事务，DDL 会被自动提交而无法回滚；
        # 显式 BEGIN 让 CREATE/ALTER 等 DDL 参与事务，保证迁移失败可回滚。
        @event.listens_for(engine.sync_engine, "begin")
        def _emit_begin(connection) -> None:  # type: ignore[no-untyped-def]
            connection.exec_driver_sql("BEGIN")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        self._ensure_usable()
        async with AsyncSession(self.engine) as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        self._ensure_usable()
        async with AsyncSession(self.engine) as session:
            async with session.begin():
                yield session

    def _ensure_usable(self) -> None:
        if self._state == "unbound":
            raise PluginDatabaseNotReadyError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 尚未初始化，不能使用"
            )
        if self._state == "closed":
            raise PluginDatabaseClosedError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 已关闭，不能使用"
            )

    async def migrate(self) -> None:
        if self.engine is None:
            raise PluginDatabaseNotReadyError(
                f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 尚未初始化，不能迁移"
            )
        lock = self._migration_lock
        if lock is None:
            lock = asyncio.Lock()
            self._migration_lock = lock
        async with lock:
            applied = await self._load_applied_versions()
            max_applied = max(applied) if applied else 0
            local = {
                migration.version: _migration_checksum(migration)
                for migration in self._migrations
            }
            for version in sorted(local):
                if version <= max_applied and version not in applied:
                    raise PluginMigrationError(
                        f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 的迁移列表"
                        f"插入了低于或等于最高已应用版本 {max_applied} 的迁移版本 {version}"
                        f"（不允许插入式重排）"
                    )
                if version in applied and applied[version] != local[version]:
                    migration = self._migration_by_version(version)
                    raise PluginMigrationConflictError(
                        f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 的迁移 "
                        f"v{version} {migration.name!r} 校验和与已应用记录不一致"
                    )
            missing = sorted(applied.keys() - local.keys())
            if missing:
                raise PluginMigrationError(
                    f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 的迁移列表"
                    f"删除了已应用的迁移版本: {missing}"
                )
            pending = sorted(
                (migration for migration in self._migrations if migration.version not in applied),
                key=lambda item: item.version,
            )
            for migration in pending:
                checksum = local[migration.version]
                applied_at = datetime.now(timezone.utc).isoformat()
                try:
                    async with self.engine.begin() as connection:
                        await migration.upgrade(connection)
                        await connection.execute(
                            text(
                                f"INSERT INTO {_MIGRATION_TABLE} "
                                "(version, name, checksum, applied_at) VALUES (:version, :name, :checksum, :applied_at)"
                            ),
                            {
                                "version": migration.version,
                                "name": migration.name,
                                "checksum": checksum,
                                "applied_at": applied_at,
                            },
                        )
                except Exception as exc:
                    raise PluginMigrationError(
                        f"插件 {self._plugin_name!r} 的数据库 {self._name!r} 的迁移 "
                        f"v{migration.version} {migration.name!r} 执行失败: {type(exc).__name__}"
                    ) from exc

    def _migration_by_version(self, version: int) -> Migration:
        for migration in self._migrations:
            if migration.version == version:
                return migration
        raise KeyError(version)

    async def _load_applied_versions(self) -> dict[int, str]:
        assert self.engine is not None
        async with self.engine.begin() as connection:
            await connection.execute(text(_CREATE_MIGRATION_TABLE))
            result = await connection.execute(
                text(
                    f"SELECT version, checksum FROM {_MIGRATION_TABLE} "
                    "ORDER BY version"
                )
            )
            return {int(row[0]): str(row[1]) for row in result}

    async def close(self) -> None:
        if self._state == "closed":
            if self.engine is not None:
                await self._dispose_engine(self.engine)
            return
        if self.engine is None:
            self._state = "closed"
            return
        try:
            await self._dispose_engine(self.engine)
        except Exception as exc:
            self._close_error = exc
            raise
        self._close_error = None
        self._state = "closed"

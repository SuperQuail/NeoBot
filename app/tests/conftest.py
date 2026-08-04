"""NeoBot 测试共享 fixtures — 全局约定见 bug_tracker/docs/TESTING_GUIDE.md。

新增 fixture 时请遵循:
- 命名小写下划线, 尽量 scoped 到最窄 (function > module > session)
- 需要临时目录/数据库的 fixture 一律基于 pytest 内置 tmp_path_factory / tmp_path
- 异步 fixture 在 asyncio_mode=auto 下直接 async def 即可
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio


# ── 事件循环 ──

@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ── 临时目录 / 数据库 ──

@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """模拟 app.data 数据目录 (browser/tmp/sandbox 等子目录由各测试自行创建)。"""
    return tmp_path / "data"


@pytest_asyncio.fixture(scope="session")
async def sqlite_db_path(tmp_path_factory: pytest.TempPathFactory) -> AsyncIterator[Path]:
    """session 级临时 SQLite 数据库路径 (供 storage/ 模块测试共用)。"""
    path = tmp_path_factory.mktemp("db") / "test.db"
    yield path


@pytest_asyncio.fixture(scope="session")
async def storage_engine(sqlite_db_path: Path):
    """neobot_storage 引擎 (WAL + busy_timeout, 与生产一致), 自动 dispose。"""
    from neobot_storage.engine import create_engine

    engine = await create_engine(f"sqlite+aiosqlite:///{sqlite_db_path}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def storage_uow_factory(storage_engine):
    """会话级 UoW 工厂 (每个用例可并发使用, 每用例独立 session)。"""
    from neobot_storage.uow import make_uow_factory

    factory = make_uow_factory(storage_engine)
    yield factory


# ── 沙箱 ──

@pytest.fixture()
def make_sandbox(tmp_data_dir: Path):
    """工厂 fixture: 创建独立的 SandboxService (沙箱根 = tmp_data_dir/sandbox)。"""
    from neobot_app.runtime.sandbox_service import SandboxService

    def _make(**kwargs) -> SandboxService:
        root = tmp_data_dir / "sandbox"
        root.mkdir(parents=True, exist_ok=True)
        return SandboxService(sandbox_root=root, **kwargs)

    return _make


# ── BugStore (bug_tracker 数据层, 供 test_runner GUI 相关的测试) ──

@pytest.fixture()
def make_bug_store(tmp_path: Path):
    """工厂 fixture: 在临时目录创建 BugStore。"""
    from bugstore import BugStore

    def _make() -> BugStore:
        return BugStore(tmp_path)

    return _make

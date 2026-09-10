"""NeoBot 测试共享 fixtures — 全局约定见 bug_tracker/docs/TESTING_GUIDE.md。

新增 fixture 时请遵循:
- 命名小写下划线, 尽量 scoped 到最窄 (function > module > session)
- 需要临时目录/数据库的 fixture 一律基于 pytest 内置 tmp_path_factory / tmp_path
- 异步 fixture 在 asyncio_mode=auto 下直接 async def 即可
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio


# ── 进程级状态隔离 ──

@pytest.fixture(autouse=True)
def _isolate_process_state() -> Iterator[None]:
    """隔离跨用例的全局副作用：os.environ 与模型注册表。

    配置加载路径会直接写 ``os.environ``（``load_env``）并调用
    ``register_models``，这些副作用不受 ``monkeypatch`` 追踪；漏到后续用例会
    造成与顺序相关的假失败（例如面板用例断言「未配置 APIKey」时，却拿到了
    前一个模块写进环境的密钥）。
    """
    environ_snapshot = dict(os.environ)

    registry = None
    registry_snapshot: tuple = ()
    try:
        from neobot_chat import get_model_registry

        registry = get_model_registry()
        registry_snapshot = registry.items()
    except Exception:
        registry = None

    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ_snapshot)
        if registry is not None:
            registry.clear()
            for _name, model in registry_snapshot:
                registry.register(model, replace=True)


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


# ── httpx 客户端构造加速 ──

@pytest.fixture(scope="session", autouse=True)
def _cache_httpx_ssl_context() -> Iterator[None]:
    """测试进程内缓存 httpx 的默认 SSL 上下文。

    httpx 每构造一个客户端都会重新加载 CA 证书（本机实测约 0.8s/次；开启系统代理
    时约 2.4s/次），而测试会创建大量客户端，累计可达一分钟以上。SSLContext 可安全
    复用，因此这里只加载一次。

    只影响默认路径（verify=True 且未显式传 cert）；显式 verify/cert 的调用照旧。
    """
    from httpx import _config
    from httpx._transports import default as _transports_default

    originals = {
        _config: _config.create_ssl_context,
        _transports_default: _transports_default.create_ssl_context,
    }
    cache: dict[bool, object] = {}

    def _cached(verify: object = True, cert: object = None, trust_env: bool = True):
        if verify is not True or cert is not None:
            return originals[_config](verify=verify, cert=cert, trust_env=trust_env)
        if trust_env not in cache:
            cache[trust_env] = originals[_config](
                verify=verify, cert=cert, trust_env=trust_env
            )
        return cache[trust_env]

    _config.create_ssl_context = _cached
    _transports_default.create_ssl_context = _cached
    try:
        yield
    finally:
        for module, original in originals.items():
            module.create_ssl_context = original

# ── BugStore (bug_tracker 数据层, 供 test_runner GUI 相关的测试) ──

@pytest.fixture()
def make_bug_store(tmp_path: Path):
    """工厂 fixture: 在临时目录创建 BugStore。"""
    from bugstore import BugStore

    def _make() -> BugStore:
        return BugStore(tmp_path)

    return _make

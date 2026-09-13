"""AvatarStore 本体能力的单测（spec(5) §4.9 / A36 的可单测部分）。

所有网络调用一律 mock（构造时注入 fetcher），测试绝不真联网：
fetcher 就是唯一的取源注入点，默认实现才走 qlogo。
"""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from neobot_app.config.schemas.bot import AvatarsConfig
from neobot_app.runtime import avatar_store as avatar_store_module
from neobot_app.runtime.avatar_store import AvatarStore
from neobot_contracts.time_context import to_utc
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory

PNG_HEADER = b"\x89PNG\r\n\x1a\n"

#: 失败注入时用到的哨兵异常
class FetchError(RuntimeError):
    pass


def png(marker: bytes = b"A", size: int = 64) -> bytes:
    """构造一段「像 PNG」的字节（魔数正确 + marker 用于区分版本）。"""
    body = PNG_HEADER + marker
    return body + b"\x00" * max(0, size - len(body))


class FakeClock:
    """可控墙钟 + 单调钟：让 7 天过期与 600 秒冷却都能单测。"""

    def __init__(self) -> None:
        self.now = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
        self.mono = 10_000.0

    def advance(self, *, wall_only: bool = False, **kwargs: float) -> None:
        """推进墙钟（过期判定）；wall_only=False 时同时推进单调钟（冷却 / 清理节流）。"""
        delta = timedelta(**kwargs)
        self.now = self.now + delta
        if not wall_only:
            self.mono += delta.total_seconds()


class _StatementRecorder:
    """记录引擎上执行的 SQL，用来断言「零写库」。"""

    def __init__(self, engine) -> None:
        self.statements: list[str] = []
        self._handler = self._on_statement
        event.listen(engine.sync_engine, "before_cursor_execute", self._handler)

    def _on_statement(self, conn, cursor, statement, parameters, context, executemany):
        self.statements.append(statement)

    def reset(self) -> None:
        self.statements.clear()

    @property
    def writes(self) -> list[str]:
        return [
            statement
            for statement in self.statements
            if statement.lstrip()[:6].upper() in {"INSERT", "UPDATE", "DELETE"}
        ]


@pytest_asyncio.fixture
async def db(tmp_path):
    """独立的内存 sqlite（StaticPool：多个 UoW 会话共享同一份数据）。"""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    recorder = _StatementRecorder(engine)
    yield SimpleNamespace(
        engine=engine,
        uow_factory=make_uow_factory(engine),
        recorder=recorder,
    )
    event.remove(engine.sync_engine, "before_cursor_execute", recorder._handler)
    await engine.dispose()


def make_store(db, tmp_path, fetcher, *, clock: FakeClock | None = None, **kwargs):
    clock = clock or FakeClock()
    store = AvatarStore(
        uow_factory=db.uow_factory,
        directory=tmp_path / "avatars",
        fetcher=fetcher,
        clock=lambda: clock.now,
        monotonic=lambda: clock.mono,
        **kwargs,
    )
    return store, clock


async def read_avatar(db, user_id: str):
    async with db.uow_factory() as uow:
        row = await uow.profiles.get_user(user_id)
        if row is None:
            return None
        return (
            row.avatar_path,
            to_utc(row.avatar_fetched_at) if row.avatar_fetched_at else None,
            int(row.avatar_fail_count or 0),
        )


def temp_files(directory) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(path.name for path in directory.iterdir() if path.name.startswith(".tmp-"))


class CountingFetcher:
    def __init__(self, *results: object) -> None:
        self.calls: list[str] = []
        self._results = list(results)

    async def __call__(self, user_id: str) -> bytes:
        self.calls.append(user_id)
        result = self._results[min(len(self.calls) - 1, len(self._results) - 1)]
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, bytes)
        return result


# ── 目录与首次获取 ───────────────────────────────────────────────


async def test_avatar_dir_is_created_automatically(db, tmp_path):
    target = tmp_path / "avatars"
    assert not target.exists()

    make_store(db, tmp_path, CountingFetcher(png()))

    assert target.is_dir(), "<DATA_DIR>/avatars/ 必须自动创建"


async def test_first_appearance_fetches_and_records(db, tmp_path):
    fetcher = CountingFetcher(png(b"first"))
    store, clock = make_store(db, tmp_path, fetcher)

    assert store.get_path("10001") is None
    assert store.get_data_uri("10001") is None

    assert await store.maybe_refresh("10001") is True
    await store.drain()

    path = tmp_path / "avatars" / "10001.png"
    assert path.is_file()
    assert path.read_bytes() == png(b"first")
    row = await read_avatar(db, "10001")
    assert row is not None
    avatar_path, fetched_at, fail_count = row
    assert avatar_path == str(path)
    assert fetched_at == clock.now
    assert fail_count == 0
    assert fetcher.calls == ["10001"]
    assert store.get_path("10001") == path

    uri = store.get_data_uri("10001")
    assert uri is not None and uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == png(b"first")


async def test_avatar_path_is_inside_configured_directory(db, tmp_path):
    fetcher = CountingFetcher(png())
    store, _ = make_store(db, tmp_path, fetcher)

    await store.maybe_refresh("10001")
    await store.drain()

    row = await read_avatar(db, "10001")
    assert row is not None
    assert str(row[0]) == str(tmp_path / "avatars" / "10001.png")


# ── 惰性刷新语义 ─────────────────────────────────────────────────


async def test_fresh_avatar_second_message_is_zero_network_and_zero_write(db, tmp_path):
    fetcher = CountingFetcher(png(b"first"))
    store, _ = make_store(db, tmp_path, fetcher)
    await store.maybe_refresh("10002")
    await store.drain()
    assert len(fetcher.calls) == 1

    db.recorder.reset()
    # 未过期：再出现 5 次都不该有网络、也不该写库
    for _ in range(5):
        assert await store.maybe_refresh("10002") is False
    await store.drain()

    assert len(fetcher.calls) == 1, "未过期不得再联网"
    assert db.recorder.writes == [], "未过期不得写库"
    assert store.stats()["skipped_fresh"] == 5


async def test_expired_avatar_is_refreshed_when_user_appears_again(db, tmp_path):
    fetcher = CountingFetcher(png(b"old"), png(b"new"))
    store, clock = make_store(db, tmp_path, fetcher)
    await store.maybe_refresh("10003")
    await store.drain()
    before = await read_avatar(db, "10003")

    clock.advance(days=8)  # 超过默认 7 天
    assert await store.maybe_refresh("10003") is True
    await store.drain()

    assert len(fetcher.calls) == 2
    assert (tmp_path / "avatars" / "10003.png").read_bytes() == png(b"new")
    after = await read_avatar(db, "10003")
    assert after is not None and before is not None
    assert after[1] == clock.now and after[1] != before[1]
    assert store.stats()["refreshed"] == 1


async def test_avatar_older_than_refresh_days_not_refreshed_before_boundary(db, tmp_path):
    fetcher = CountingFetcher(png(b"old"), png(b"new"))
    store, clock = make_store(db, tmp_path, fetcher)
    await store.maybe_refresh("10004")
    await store.drain()

    clock.advance(days=6, hours=23)
    assert await store.maybe_refresh("10004") is False
    await store.drain()
    assert len(fetcher.calls) == 1


# ── 失败语义 ─────────────────────────────────────────────────────


async def test_failure_keeps_old_avatar_and_bumps_fail_count(db, tmp_path):
    fetcher = CountingFetcher(png(b"good"), FetchError("boom"))
    store, clock = make_store(db, tmp_path, fetcher)
    await store.maybe_refresh("10005")
    await store.drain()
    before = await read_avatar(db, "10005")

    clock.advance(days=8)
    assert await store.maybe_refresh("10005") is True
    await store.drain()

    path = tmp_path / "avatars" / "10005.png"
    assert path.read_bytes() == png(b"good"), "失败不得覆盖旧头像"
    after = await read_avatar(db, "10005")
    assert before is not None and after is not None
    assert after[0] == before[0], "失败不得改写 avatar_path"
    assert after[1] == before[1], "失败不得改写 avatar_fetched_at"
    assert after[2] == before[2] + 1, "失败必须累加 fail_count"
    assert temp_files(tmp_path / "avatars") == [], "失败不得留下半截文件"
    assert store.stats()["failed"] == 1


async def test_failure_cooldown_blocks_repeated_attempts(db, tmp_path):
    fetcher = CountingFetcher(FetchError("boom"))
    store, clock = make_store(db, tmp_path, fetcher)

    assert await store.maybe_refresh("10006") is True
    await store.drain()
    for _ in range(10):
        assert await store.maybe_refresh("10006") is False
    await store.drain()

    assert len(fetcher.calls) == 1, "冷却期内只允许尝试 1 次"
    assert store.stats()["skipped_cooldown"] >= 10
    row = await read_avatar(db, "10006")
    assert row is not None and row[2] == 1

    clock.advance(seconds=601)
    assert await store.maybe_refresh("10006") is True
    await store.drain()
    assert len(fetcher.calls) == 2


async def test_oversize_image_is_not_written(db, tmp_path):
    fetcher = CountingFetcher(png(b"big", size=4096))
    store, _ = make_store(db, tmp_path, fetcher, max_bytes=64)

    assert await store.maybe_refresh("10007") is True
    await store.drain()

    assert not (tmp_path / "avatars" / "10007.png").exists()
    assert temp_files(tmp_path / "avatars") == []
    row = await read_avatar(db, "10007")
    assert row is not None
    assert row[0] is None and row[1] is None
    assert row[2] == 1
    assert store.stats()["failed"] == 1


async def test_non_image_response_is_rejected(db, tmp_path):
    fetcher = CountingFetcher(b"<html>nope</html>")
    store, _ = make_store(db, tmp_path, fetcher)

    await store.maybe_refresh("10008")
    await store.drain()

    assert not (tmp_path / "avatars" / "10008.png").exists()
    row = await read_avatar(db, "10008")
    assert row is not None and row[2] == 1


# ── 不阻塞消息处理 ───────────────────────────────────────────────


async def test_slow_download_does_not_block_the_message_path(db, tmp_path):
    release = asyncio.Event()

    async def gated_fetch(user_id: str) -> bytes:
        await release.wait()
        return png(user_id.encode())

    store, _ = make_store(db, tmp_path, gated_fetch)
    # 预热：先派发一次慢下载，把 aiosqlite 建连 / 语句编译的成本移出计时区间
    assert await store.maybe_refresh("20001") is True

    loop = asyncio.get_running_loop()
    started = loop.time()
    triggered = await store.maybe_refresh("20002")
    elapsed = loop.time() - started

    assert triggered is True
    assert elapsed < 0.05, f"消息路径不得等下载（实测 {elapsed * 1000:.1f}ms）"
    # 结构断言（比计时更稳）：触发即返回，下载仍在后台进行
    assert store.stats()["inflight"] == 2

    release.set()
    await store.drain()
    assert (tmp_path / "avatars" / "20001.png").is_file()
    assert (tmp_path / "avatars" / "20002.png").is_file()


async def test_single_flight_per_user(db, tmp_path):
    release = asyncio.Event()

    async def gated_fetch(user_id: str) -> bytes:
        await release.wait()
        return png(b"x")

    store, _ = make_store(db, tmp_path, gated_fetch)
    assert await store.maybe_refresh("30001") is True
    assert await store.maybe_refresh("30001") is False
    assert store.stats()["inflight"] == 1
    assert store.stats()["skipped_inflight"] == 1

    release.set()
    await store.drain()


async def test_global_concurrency_limit_drops_extra_triggers(db, tmp_path):
    release = asyncio.Event()
    started: list[str] = []

    async def gated_fetch(user_id: str) -> bytes:
        started.append(user_id)
        await release.wait()
        return png(user_id.encode())

    store, _ = make_store(db, tmp_path, gated_fetch, max_concurrent=2)
    results = [await store.maybe_refresh(f"4000{i}") for i in range(5)]

    assert results == [True, True, False, False, False]
    assert store.stats()["inflight"] == 2
    assert store.stats()["dropped_concurrency"] == 3

    release.set()
    await store.drain()
    assert sorted(started) == ["40000", "40001"]

    # 超限被丢弃的触发不做排队：该用户下次出现时自然重试（此处并发已空出）
    assert await store.maybe_refresh("40002") is True
    await store.drain()
    assert (tmp_path / "avatars" / "40002.png").is_file()


# ── 容量治理 ─────────────────────────────────────────────────────


async def test_keep_days_cleanup_removes_files_and_clears_columns(db, tmp_path):
    fetcher = CountingFetcher(png())
    store, clock = make_store(db, tmp_path, fetcher)

    await store.maybe_refresh("50001")
    await store.drain()
    # 只推进墙钟：让 50001 超过 keep_days，同时不触发「随流量顺带清理」
    clock.advance(days=91, wall_only=True)
    # 活跃用户：在 91 天后重新出现 → 刷新把时间戳拉回当下，不该被清理
    await store.maybe_refresh("50002")
    await store.drain()

    removed = await store.cleanup_expired()

    assert removed == 1
    assert not (tmp_path / "avatars" / "50001.png").exists()
    assert (tmp_path / "avatars" / "50002.png").is_file()
    cleaned = await read_avatar(db, "50001")
    assert cleaned == (None, None, 0)
    assert store.get_data_uri("50001") is None
    assert store.stats()["cleaned"] == 1


async def test_keep_days_cleanup_runs_opportunistically_with_traffic(db, tmp_path):
    """不做定时全量扫描：清理随头像刷新流量触发（最多每 24 小时一次）。"""
    fetcher = CountingFetcher(png())
    store, clock = make_store(db, tmp_path, fetcher)

    await store.maybe_refresh("50011")
    await store.drain()
    clock.advance(days=91)  # 墙钟与单调钟一起推进（超过 24 小时清理节流）

    await store.maybe_refresh("50012")  # 新用户出现，顺带触发一次清理
    await store.drain()

    assert not (tmp_path / "avatars" / "50011.png").exists()
    assert (tmp_path / "avatars" / "50012.png").is_file()
    assert store.stats()["cleaned"] == 1
    assert await read_avatar(db, "50011") == (None, None, 0)


async def test_cleanup_keeps_fresh_avatars(db, tmp_path):
    fetcher = CountingFetcher(png())
    store, _ = make_store(db, tmp_path, fetcher)
    await store.maybe_refresh("50003")
    await store.drain()

    assert await store.cleanup_expired() == 0
    assert (tmp_path / "avatars" / "50003.png").is_file()


# ── 取数接口与缓存 ───────────────────────────────────────────────


async def test_get_data_uri_returns_none_when_not_ready(db, tmp_path):
    store, _ = make_store(db, tmp_path, CountingFetcher(png()))
    assert store.get_path("60001") is None
    assert store.get_data_uri("60001") is None


async def test_data_uri_cache_is_lru_bounded(db, tmp_path):
    store, _ = make_store(db, tmp_path, CountingFetcher(png()))
    directory = tmp_path / "avatars"
    directory.mkdir(parents=True, exist_ok=True)
    limit = avatar_store_module.DATA_URI_CACHE_SIZE
    for index in range(limit + 2):
        (directory / f"{80000 + index}.png").write_bytes(png(str(index).encode()))

    for index in range(limit + 2):
        assert store.get_data_uri(str(80000 + index)) is not None

    assert store.stats()["data_uri_cached"] == limit
    # 被淘汰的仍可再次读取（LRU 只是缓存，不是真相来源）
    assert store.get_data_uri("80000") is not None
    assert store.stats()["data_uri_cached"] == limit


# ── 配置与开关 ───────────────────────────────────────────────────


async def test_config_section_drives_defaults(db, tmp_path):
    config = SimpleNamespace(
        avatars=AvatarsConfig(refresh_days=1, max_concurrent=3, keep_days=30)
    )
    store, clock = make_store(
        db, tmp_path, CountingFetcher(png(b"old"), png(b"new")), config=config
    )
    stats = store.stats()
    assert stats["refresh_days"] == 1 and stats["max_concurrent"] == 3
    assert stats["keep_days"] == 30

    await store.maybe_refresh("70001")
    await store.drain()
    clock.advance(days=2)
    assert await store.maybe_refresh("70001") is True
    await store.drain()
    assert (tmp_path / "avatars" / "70001.png").read_bytes() == png(b"new")


async def test_disabled_store_does_nothing(db, tmp_path):
    fetcher = CountingFetcher(png())
    store, _ = make_store(db, tmp_path, fetcher, enabled=False)

    assert await store.maybe_refresh("70002") is False
    db.recorder.reset()
    assert await store.maybe_refresh("70002") is False
    await store.drain()

    assert fetcher.calls == []
    assert db.recorder.writes == []
    assert store.stats()["started"] == 0
    assert store.stats()["tasks"] == 0
    assert not (tmp_path / "avatars" / "70002.png").exists()


async def test_maybe_refresh_never_raises_when_db_is_broken(tmp_path):
    class BrokenUow:
        def __call__(self):
            raise RuntimeError("db down")

    store = AvatarStore(
        uow_factory=BrokenUow(),
        directory=tmp_path / "avatars",
        fetcher=CountingFetcher(png()),
    )

    assert await store.maybe_refresh("70003") is False


# ── 宿主服务 ─────────────────────────────────────────────────────


async def test_avatar_store_is_available_as_host_service(db, tmp_path):
    from neobot_contracts.ports.logging import NullLogger

    from neobot_app.bootstrap._pipeline import build_plugin_host, register_host_services

    class _LoggerFactory:
        def get_logger(self, _name: str) -> NullLogger:
            return NullLogger()

    store, _ = make_store(db, tmp_path, CountingFetcher(png()))
    host = build_plugin_host(logger_factory=_LoggerFactory())
    register_host_services(
        host["host_facade"],
        {"avatar_store": (store, "用户头像本地存储与惰性刷新")},
    )

    assert host["host_facade"].services.get("avatar_store") is store


def test_bootstrap_registers_avatar_host_service() -> None:
    """接线断言：组合根必须把 AvatarStore 登记为宿主服务（否则面板/插件取不到）。"""
    import inspect

    from neobot_app import bootstrap

    source = inspect.getsource(bootstrap.create_application)
    assert '"avatar_store": (' in source
    assert 'avatar_store=avatar_store' in source


@pytest.mark.parametrize("user_id", ["", None])
async def test_blank_user_id_is_ignored(db, tmp_path, user_id):
    fetcher = CountingFetcher(png())
    store, _ = make_store(db, tmp_path, fetcher)
    assert await store.maybe_refresh(user_id) is False
    assert fetcher.calls == []


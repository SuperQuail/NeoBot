"""好感度增量：真实 SQLite、独立 session 的并发和事务失败回归。"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import pytest_asyncio

from neobot_app import user_profiles
from neobot_app.skills.favorability import FavorabilitySkill
from neobot_app.user_profiles import UserProfileService
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import UserData
from neobot_storage.repositories.profile import SqlAlchemyProfileRepository
from neobot_storage.uow import SqlAlchemyUnitOfWork, make_uow_factory


@pytest_asyncio.fixture
async def profiles(tmp_path):
    engine = create_engine(sqlite_url(tmp_path / "profiles.sqlite3"))
    async with engine.begin() as connection:
        await connection.run_sync(UserData.__table__.create)
    factory = make_uow_factory(engine)
    service = UserProfileService(SimpleNamespace(), factory, SimpleNamespace())
    try:
        yield service, factory
    finally:
        await engine.dispose()


def _synchronize_first_reads(monkeypatch):
    """强制两个独立事务都先读到同一旧值，而不是依赖偶然调度。"""
    original = SqlAlchemyProfileRepository.get_user
    barrier = asyncio.Barrier(2)
    reads = []

    async def get_user(self, user_id):
        record = await original(self, user_id)
        if len(reads) < 2:
            reads.append(self._session)
            await barrier.wait()
        return record

    monkeypatch.setattr(SqlAlchemyProfileRepository, "get_user", get_user)
    return reads


@pytest.mark.parametrize("existing", [True, False])
async def test_two_concurrent_increments_are_not_lost(profiles, monkeypatch, existing):
    service, _ = profiles
    if existing:
        await service.update_user_favorability("123", 0)
    reads = _synchronize_first_reads(monkeypatch)

    results = await asyncio.wait_for(asyncio.gather(
        service.update_favorability("123", 5),
        service.update_favorability("123", 5),
    ), timeout=10)

    assert len(reads) == 2 and reads[0] is not reads[1]
    assert (await service.get_user("123")).favorability == 10
    assert sorted((r["before"], r["after"], r["change"]) for r in results) == [
        (0, 5, 5), (5, 10, 5),
    ]


async def test_concurrent_mixed_changes_preserve_every_increment(profiles):
    service, _ = profiles
    await service.update_user_favorability("123", 20)
    deltas = [5, -3] * 8
    results = await asyncio.wait_for(asyncio.gather(*(
        service.update_favorability("123", delta) for delta in deltas
    )), timeout=15)
    assert sum(r["change"] for r in results) == sum(deltas)
    assert (await service.get_user("123")).favorability == 20 + sum(deltas)


@pytest.mark.parametrize("before,change,after,effective", [
    (0, 999, 5, 5), (100, -999, 95, -5),
    (998, 5, 1000, 2), (1000, 5, 1000, 0),
    (-998, -5, -1000, -2), (-1000, -5, -1000, 0),
])
async def test_limits_report_actual_committed_change(profiles, before, change, after, effective):
    service, _ = profiles
    await service.update_user_favorability("123", before)
    result = await service.update_favorability("123", change, reason="互动", max_change=5)
    assert result["before"] == before
    assert result["after"] == after
    assert result["change"] == effective
    assert result["reason"] == "互动"
    assert (await service.get_user("123")).favorability == after


async def test_custom_range_and_disabled_change_limit(profiles):
    service, _ = profiles
    result = await service.update_favorability("123", 9, max_change=10, min_value=-2, max_value=2)
    assert (result["after"], result["change"]) == (2, 2)
    result = await service.update_favorability("123", -9, max_change=0)
    assert (result["after"], result["change"]) == (2, 0)


async def test_cas_does_not_overwrite_existing_user_or_other_fields(profiles):
    service, factory = profiles
    async with factory() as uow:
        await uow.profiles.upsert_user("123", favorability=10, nick_name="原昵称", avatar_path="avatar.png")
        await uow.commit()
    async with factory() as uow:
        assert not await uow.profiles.compare_and_set_user_favorability("123", expected=None, value=5)
        assert not await uow.profiles.compare_and_set_user_favorability("123", expected=0, value=5)
        await uow.commit()
    await service.update_favorability("123", 3)
    record = await service.get_user("123")
    assert (record.favorability, record.nick_name, record.avatar_path) == (13, "原昵称", "avatar.png")


async def test_commit_lock_conflict_replays_whole_transaction(profiles, monkeypatch):
    service, _ = profiles
    await service.update_user_favorability("123", 10)
    commit = SqlAlchemyUnitOfWork.commit
    sessions = []

    async def fail_once(self):
        sessions.append(self._session)
        if len(sessions) == 1:
            raise RuntimeError("database is locked")
        await commit(self)

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", fail_once)
    result = await service.update_favorability("123", 5)
    assert len(sessions) == 2 and sessions[0] is not sessions[1]
    assert (result["before"], result["after"], result["change"]) == (10, 15, 5)
    assert (await service.get_user("123")).favorability == 15


async def test_post_commit_close_failure_does_not_replay_increment(profiles, monkeypatch):
    service, _ = profiles
    await service.update_user_favorability("123", 10)
    close = SqlAlchemyUnitOfWork.__aexit__
    calls = []

    async def broken_close(self, *exc):
        await close(self, *exc)
        calls.append(self)
        if len(calls) == 1:
            raise RuntimeError("database is locked while closing session")

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "__aexit__", broken_close)
    with pytest.raises(RuntimeError, match="closing session"):
        await service.update_favorability("123", 5)
    assert len(calls) == 1
    assert (await service.get_user("123")).favorability == 15


@pytest.mark.parametrize("lock_error", [False, True])
async def test_failed_commit_never_reports_success(profiles, monkeypatch, lock_error):
    service, _ = profiles
    await service.update_user_favorability("123", 10)
    calls = []
    logs = []
    service._logger = SimpleNamespace(info=lambda *a, **kw: logs.append(kw))
    monkeypatch.setattr(user_profiles, "_FAVORABILITY_UPDATE_ATTEMPTS", 2)

    async def broken_commit(self):
        calls.append(self._session)
        raise RuntimeError("database is locked" if lock_error else "disk failure")

    monkeypatch.setattr(SqlAlchemyUnitOfWork, "commit", broken_commit)
    with pytest.raises(RuntimeError, match="并发冲突" if lock_error else "disk failure"):
        await service.update_favorability("123", 5)
    assert len(calls) == (2 if lock_error else 1)
    assert not logs
    assert (await service.get_user("123")).favorability == 10


async def test_cas_exhaustion_is_bounded_and_skill_reports_failure(profiles, monkeypatch):
    service, _ = profiles
    calls = []
    monkeypatch.setattr(user_profiles, "_FAVORABILITY_UPDATE_ATTEMPTS", 2)

    async def always_conflicts(self, *args, **kwargs):
        calls.append(self._session)
        return False

    monkeypatch.setattr(SqlAlchemyProfileRepository, "compare_and_set_user_favorability", always_conflicts)
    result = json.loads(await FavorabilitySkill(profile_service=service).execute(
        "update_favorability", {"user_id": "123", "change": 5},
    ))
    assert result["ok"] is False
    assert "并发冲突" in result["error"]
    assert len(calls) == 2 and calls[0] is not calls[1]
    assert await service.get_user("123") is None


async def test_skill_uses_increment_contract(profiles):
    service, _ = profiles
    result = json.loads(await FavorabilitySkill(profile_service=service).execute(
        "update_favorability", {"user_id": "123", "change": 4, "reason": "开心"},
    ))
    assert result["ok"] is True
    assert result["result"] == {
        "user_id": "123", "before": 0, "after": 4, "change": 4,
        "label": "普通网友", "reason": "开心",
    }


@pytest.mark.parametrize("change", ["abc", None, float("inf")])
async def test_skill_bad_change_returns_error_without_writing(profiles, change):
    service, _ = profiles
    result = json.loads(await FavorabilitySkill(profile_service=service).execute(
        "update_favorability", {"user_id": "123", "change": change},
    ))
    assert result["ok"] is False
    assert await service.get_user("123") is None

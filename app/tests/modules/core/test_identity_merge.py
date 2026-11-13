"""身份合并：openid 为主键，QQ号/群号档案并入且排在前面。"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from neobot_contracts.models.memory import ArchiveMemory
from neobot_contracts.ports.logging import NullLogger

from neobot_app.identity_merge import IdentityMergeService
from neobot_memory.archive_service import ArchiveMemoryService

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class _Archive:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], ArchiveMemory] = {}

    async def get(self, table_name: str, key: str) -> ArchiveMemory | None:
        return self.items.get((table_name, key))

    async def set(self, table_name: str, key: str, value: str, tags: list[str]) -> ArchiveMemory:
        item = ArchiveMemory(1, table_name, key, value, list(tags), NOW, NOW, 1)
        self.items[(table_name, key)] = item
        return item

    async def delete(self, table_name: str, key: str) -> bool:
        return self.items.pop((table_name, key), None) is not None


def _profile_row(**fields):
    values = {
        "nick_name": None,
        "relation_ship": None,
        "profile": None,
        "known_gender": None,
        "birthday": None,
        "sex": None,
        "city": None,
        "country": None,
        "labs": None,
        "remark": None,
        "avatar_analysis": None,
        "long_nick": None,
        "favorability": 0,
        "age": None,
        "fetched_at": None,
        "avatar_path": None,
        "avatar_fetched_at": None,
        "avatar_fail_count": 0,
    }
    values.update(fields)
    return SimpleNamespace(**values)


class _Profiles:
    def __init__(self) -> None:
        self.users: dict[str, object] = {}
        self.groups: dict[str, object] = {}

    async def get_user(self, user_id):
        return self.users.get(user_id)

    async def upsert_user(self, user_id, **fields):
        row = self.users.get(user_id) or _profile_row()
        for name, value in fields.items():
            setattr(row, name, value)
        self.users[user_id] = row

    async def delete_user(self, user_id):
        self.users.pop(user_id, None)

    async def get_group(self, group_id):
        return self.groups.get(group_id)

    async def upsert_group(self, group_id, **fields):
        row = self.groups.get(group_id) or SimpleNamespace(
            group_name=None, profile=None, is_quite=False
        )
        for name, value in fields.items():
            setattr(row, name, value)
        self.groups[group_id] = row

    async def delete_group(self, group_id):
        self.groups.pop(group_id, None)


class _Uow:
    def __init__(self, archive: _Archive, profiles: _Profiles) -> None:
        self.archive = archive
        self.profiles = profiles

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def commit(self) -> None:
        pass


@pytest.fixture
def storage():
    archive, profiles = _Archive(), _Profiles()

    def factory():
        return _Uow(archive, profiles)

    return archive, profiles, factory


async def test_merge_user_prepends_qq_content_and_removes_source(storage):
    archive, profiles, factory = storage
    await archive.set("user_profile", "123", "QQ档案", ["qq"])
    await archive.set("user_profile", "OPENID", "openid档案", ["openid"])
    await archive.set("user_summary", "123", "QQ摘要", [])
    profiles.users["123"] = _profile_row(
        profile="QQ资料", nick_name="QQ昵称", favorability=5
    )
    profiles.users["OPENID"] = _profile_row(
        profile="openid资料", nick_name="openid昵称", favorability=2
    )
    service = IdentityMergeService(uow_factory=factory, logger=NullLogger())

    result = await service.merge_user(openid="OPENID", qq=123)

    assert result["merged"] is True
    assert archive.items[("user_profile", "OPENID")].value == "QQ档案\n\nopenid档案"
    assert ("user_profile", "123") not in archive.items
    assert archive.items[("user_summary", "OPENID")].value == "QQ摘要"
    row = profiles.users["OPENID"]
    assert row.profile == "QQ资料\n\nopenid资料"
    assert row.nick_name == "openid昵称"
    assert row.favorability == 5
    assert "123" not in profiles.users


async def test_merge_group_prepends_number_content(storage):
    archive, profiles, factory = storage
    await archive.set("group_profile", "987", "群QQ档案", [])
    await archive.set("group_profile", "GOPENID", "群openid档案", [])
    profiles.groups["987"] = SimpleNamespace(
        group_name="QQ群名", profile="QQ群资料", is_quite=False
    )
    profiles.groups["GOPENID"] = SimpleNamespace(
        group_name="openid群名", profile="openid群资料", is_quite=True
    )
    service = IdentityMergeService(uow_factory=factory, logger=NullLogger())

    result = await service.merge_group(openid="GOPENID", number=987)

    assert result["merged"] is True
    assert archive.items[("group_profile", "GOPENID")].value == "群QQ档案\n\n群openid档案"
    row = profiles.groups["GOPENID"]
    assert row.group_name == "openid群名"
    assert row.profile == "QQ群资料\n\nopenid群资料"
    assert "987" not in profiles.groups


async def test_merge_without_source_is_noop(storage):
    archive, profiles, factory = storage
    service = IdentityMergeService(uow_factory=factory, logger=NullLogger())

    result = await service.merge_user(openid="OPENID", qq=123)

    assert result["merged"] is False
    assert archive.items == {}
    assert profiles.users == {}


async def test_archive_key_mapper_canonicalizes_reads_and_writes(storage):
    archive, _profiles, factory = storage
    service = ArchiveMemoryService(
        uow_factory=factory,
        logger=NullLogger(),
        key_mapper=lambda table, key: "OPENID" if key == "123" else key,
    )

    await service.set("user_profile", "123", "档案", [])

    assert ("user_profile", "OPENID") in archive.items
    assert ("user_profile", "123") not in archive.items
    item = await service.get("user_profile", "123")
    assert item is not None and item.value == "档案"


async def test_profile_service_writes_mapped_qq_into_openid(tmp_path, storage):
    from types import SimpleNamespace

    from neobot_app.user_identity import bind_user_identity, link_user_qq
    from neobot_app.user_profiles import UserProfileService

    _archive, profiles, factory = storage

    class _Adapter:
        async def get_stranger_info(self, user_id):
            return SimpleNamespace(data=None)

    bind_user_identity(tmp_path)
    try:
        assert link_user_qq("OPENID", 123456789, trusted=True)[0]
        service = UserProfileService(
            adapter=_Adapter(),
            uow_factory=factory,
            config=SimpleNamespace(),
        )
        await service.ensure_user_profile("123456789")
        assert "OPENID" in profiles.users
        assert "123456789" not in profiles.users
    finally:
        bind_user_identity(None)


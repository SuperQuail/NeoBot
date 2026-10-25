"""BilibiliLinkSkill 测试：关联创建、档案合并、查询、取消关联。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.bilibili_link import BilibiliLinkSkill


class FakeRepo:
    def __init__(self) -> None:
        self.links: list[dict] = []
        self.created: list[tuple[int, str]] = []
        self.deleted: list[tuple] = []
        self.commits = 0

    async def find_by_uid_and_qq(self, uid, qq):
        for link in self.links:
            if link["bilibili_uid"] == uid and link["qq_number"] == qq:
                return link
        return None

    async def create(self, uid, qq):
        self.created.append((uid, qq))
        self.links.append({"bilibili_uid": uid, "qq_number": qq})

    async def find_by_uid(self, uid):
        return [link for link in self.links if link["bilibili_uid"] == uid]

    async def find_by_qq(self, qq):
        return [link for link in self.links if link["qq_number"] == qq]

    async def delete_one(self, uid, qq):
        before = len(self.links)
        self.links = [
            link
            for link in self.links
            if not (link["bilibili_uid"] == uid and link["qq_number"] == qq)
        ]
        self.deleted.append(("one", uid, qq))
        return before - len(self.links)

    async def delete_all_for_qq(self, qq):
        before = len(self.links)
        self.links = [link for link in self.links if link["qq_number"] != qq]
        self.deleted.append(("all", qq))
        return before - len(self.links)


class FakeUow:
    def __init__(self, repo: FakeRepo) -> None:
        self.bilibili_links = repo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def commit(self):
        self.bilibili_links.commits += 1


class FakeArchive:
    def __init__(
        self,
        entries=None,
        *,
        error: Exception | None = None,
        tags: dict[tuple[str, str], list[str]] | None = None,
    ) -> None:
        self.entries = dict(entries or {})
        self.tags = dict(tags or {})
        self.error = error
        self.writes: list[tuple] = []

    async def get(self, table, key):
        if self.error is not None:
            raise self.error
        value = self.entries.get((table, key))
        if value is None:
            return None
        return SimpleNamespace(value=value, tags=list(self.tags.get((table, key), [])))

    async def set(self, table, key, value, tags):
        self.writes.append((table, key, value, tags))
        self.entries[(table, key)] = value
        self.tags[(table, key)] = list(tags)


def _factory(repo: FakeRepo):
    def make():
        return FakeUow(repo)

    return make


def _skill(repo=None, archive=None) -> BilibiliLinkSkill:
    return BilibiliLinkSkill(
        uow_factory=_factory(repo or FakeRepo()), archive_service=archive
    )


def test_no_uow_means_no_tools() -> None:
    assert BilibiliLinkSkill().get_tools() == []


async def test_link_account_creates_and_merges_archive() -> None:
    repo = FakeRepo()
    archive = FakeArchive({("bilibili_user", "77"): "B站上聊过游戏"})
    skill = _skill(repo, archive)

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["ok"] is True
    assert result["merged"] is True
    assert repo.created == [(77, "10001")]
    assert repo.commits == 1
    merged = archive.entries[("user_profile", "10001")]
    assert "[B站UID:77]" in merged
    assert "B站上聊过游戏" in merged


async def test_link_account_duplicate_does_not_create_again() -> None:
    repo = FakeRepo()
    repo.links.append({"bilibili_uid": 77, "qq_number": "10001"})
    skill = _skill(repo, FakeArchive())

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["ok"] is True
    assert result["merged"] is False
    assert repo.created == []


async def test_link_account_merge_is_idempotent() -> None:
    repo = FakeRepo()
    archive = FakeArchive(
        {
            ("bilibili_user", "77"): "B站记忆",
            ("user_profile", "10001"): "[B站UID:77]\nB站记忆",
        }
    )
    skill = _skill(repo, archive)

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["ok"] is True
    assert "已合并过" in result["message"]
    assert archive.writes == []


async def test_link_account_merge_failure_does_not_fail_link() -> None:
    repo = FakeRepo()
    archive = FakeArchive({("bilibili_user", "77"): "B站记忆"}, error=RuntimeError("db"))
    skill = _skill(repo, archive)

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["ok"] is True
    assert repo.created == [(77, "10001")]
    assert "已中止记忆合并" in result["message"]
    assert archive.writes == []


async def test_link_account_validation() -> None:
    skill = _skill()

    assert json.loads(
        await skill.execute("link_account", {"bilibili_uid": 0, "qq_number": ""})
    )["ok"] is False


async def test_get_link_by_uid_and_qq() -> None:
    repo = FakeRepo()
    repo.links.append({"bilibili_uid": 77, "qq_number": "10001"})
    skill = _skill(repo)

    by_uid = json.loads(await skill.execute("get_link", {"bilibili_uid": 77}))
    by_qq = json.loads(await skill.execute("get_link", {"qq_number": "10001"}))
    missing = json.loads(await skill.execute("get_link", {}))

    assert by_uid["links"][0]["qq_number"] == "10001"
    assert by_qq["links"][0]["bilibili_uid"] == 77
    assert missing["ok"] is False


async def test_unlink_one_and_all() -> None:
    repo = FakeRepo()
    repo.links.extend(
        [
            {"bilibili_uid": 77, "qq_number": "10001"},
            {"bilibili_uid": 88, "qq_number": "10001"},
        ]
    )
    skill = _skill(repo)

    one = json.loads(
        await skill.execute(
            "unlink_account", {"qq_number": "10001", "bilibili_uid": 77}
        )
    )
    assert one["removed"] == 1
    assert repo.deleted[-1] == ("one", 77, "10001")

    rest = json.loads(await skill.execute("unlink_account", {"qq_number": "10001"}))
    assert rest["removed"] == 1
    assert repo.deleted[-1] == ("all", "10001")


async def test_unknown_tool() -> None:
    result = json.loads(await _skill().execute("nope", {}))
    assert result["ok"] is False


async def test_link_account_validates_uid_and_qq() -> None:
    repo = FakeRepo()
    skill = _skill(repo)

    for args in (
        {"bilibili_uid": "abc", "qq_number": "10001"},
        {"bilibili_uid": -1, "qq_number": "10001"},
        {"bilibili_uid": True, "qq_number": "10001"},
        {"bilibili_uid": 77, "qq_number": "abc"},
        {"bilibili_uid": 77, "qq_number": "1234"},
        {"bilibili_uid": 77, "qq_number": "1234567890123"},
    ):
        result = json.loads(await skill.execute("link_account", args))
        assert result["ok"] is False, args
    assert repo.created == []

    # 字符串形式的 UID 也接受，落库统一成 int。
    ok = json.loads(
        await skill.execute("link_account", {"bilibili_uid": "77", "qq_number": "10001"})
    )
    assert ok["ok"] is True
    assert repo.created == [(77, "10001")]


async def test_link_account_rejects_conflicting_bindings() -> None:
    repo = FakeRepo()
    repo.links.append({"bilibili_uid": 77, "qq_number": "20002"})
    skill = _skill(repo)

    by_uid = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )
    assert by_uid["ok"] is False
    assert "已关联其他QQ" in by_uid["error"]
    assert "unlink_account" in by_uid["error"]
    assert repo.created == []

    other = FakeRepo()
    other.links.append({"bilibili_uid": 88, "qq_number": "10001"})
    by_qq = json.loads(
        await _skill(other).execute(
            "link_account", {"bilibili_uid": 77, "qq_number": "10001"}
        )
    )
    assert by_qq["ok"] is False
    assert "已关联其他B站UID" in by_qq["error"]
    assert other.created == []


async def test_link_account_merge_keeps_profile_tags() -> None:
    repo = FakeRepo()
    archive = FakeArchive(
        {("bilibili_user", "77"): "B站记忆", ("user_profile", "10001"): "老档案"},
        tags={("user_profile", "10001"): ["老用户"]},
    )
    skill = _skill(repo, archive)

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["merged"] is True
    table, key, value, written_tags = archive.writes[-1]
    assert (table, key) == ("user_profile", "10001")
    assert written_tags == ["老用户"]
    assert "老档案" in value and "[B站UID:77]" in value


async def test_link_account_duplicate_retries_failed_merge() -> None:
    repo = FakeRepo()
    repo.links.append({"bilibili_uid": 77, "qq_number": "10001"})
    archive = FakeArchive({("bilibili_user", "77"): "B站记忆"})
    skill = _skill(repo, archive)

    result = json.loads(
        await skill.execute("link_account", {"bilibili_uid": 77, "qq_number": "10001"})
    )

    assert result["ok"] is True
    assert result["created"] is False
    assert result["merged"] is True
    assert "已存在" in result["message"]
    assert archive.writes[-1][0] == "user_profile"


async def test_unlink_and_get_link_validate_arguments() -> None:
    skill = _skill()

    bad_qq = json.loads(await skill.execute("unlink_account", {"qq_number": "abc"}))
    assert bad_qq["ok"] is False
    assert "qq_number" in bad_qq["error"]

    missing_qq = json.loads(await skill.execute("unlink_account", {}))
    assert missing_qq["ok"] is False

    bad_uid = json.loads(
        await skill.execute(
            "unlink_account", {"qq_number": "10001", "bilibili_uid": "abc"}
        )
    )
    assert bad_uid["ok"] is False
    assert "bilibili_uid" in bad_uid["error"]

    bad_query = json.loads(await skill.execute("get_link", {"qq_number": "12"}))
    assert bad_query["ok"] is False

    bad_query_uid = json.loads(await skill.execute("get_link", {"bilibili_uid": -1}))
    assert bad_query_uid["ok"] is False

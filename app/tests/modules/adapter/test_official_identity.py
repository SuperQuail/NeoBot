"""官方身份映射测试。

覆盖：openid ↔ 13 位合成号的两段分配、持久化与重启恢复、损坏文件兜底，
以及官方消息 id ↔ OneBot 合成 int 的稳定映射与 LRU 淘汰。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neobot_adapter.official.identity import IdentityMap, MessageIdMap

_USER_MIN = 9_000_000_000_000
_USER_MAX = 9_500_000_000_000
_GROUP_MIN = 9_500_000_000_000
_GROUP_MAX = 10_000_000_000_000


def _identities_path(work_dir: Path) -> Path:
    return work_dir / "qqbot" / "identities.json"


def test_identity_map_allocates_13_digit_segments(tmp_path: Path) -> None:
    identities = IdentityMap(tmp_path)
    user = identities.user_id("user-openid")
    group = identities.group_id("group-openid")

    assert _USER_MIN <= user < _USER_MAX
    assert _GROUP_MIN <= group < _GROUP_MAX
    assert len(str(user)) == len(str(group)) == 13
    # 同一 openid 稳定；反向映射可用；用户/群两段互不串。
    assert identities.user_id("user-openid") == user
    assert identities.openid(user, "private") == "user-openid"
    assert identities.openid(group, "group") == "group-openid"
    assert identities.openid(user, "group") is None
    assert identities.openid(group, "private") is None


def test_identity_map_persists_and_recovers_after_restart(tmp_path: Path) -> None:
    first = IdentityMap(tmp_path)
    user = first.user_id("u1")
    group = first.group_id("g1")

    payload = json.loads(_identities_path(tmp_path).read_text(encoding="utf-8"))
    assert payload == {"users": {"u1": user}, "groups": {"g1": group}}

    restarted = IdentityMap(tmp_path)
    assert restarted.user_id("u1") == user
    assert restarted.group_id("g1") == group
    assert restarted.openid(user, "private") == "u1"
    # 新 openid 接着历史最大值递增，不复用旧号。
    assert restarted.user_id("u2") == user + 1


def test_identity_map_keeps_corrupt_file_as_backup(tmp_path: Path) -> None:
    path = _identities_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    identities = IdentityMap(tmp_path)
    assert identities.user_id("u1") == _USER_MIN
    assert path.with_name(path.name + ".corrupt").read_text(encoding="utf-8") == "{not json"


def test_identity_map_rejects_empty_openid(tmp_path: Path) -> None:
    identities = IdentityMap(tmp_path)
    with pytest.raises(ValueError):
        identities.user_id("  ")
    with pytest.raises(ValueError):
        identities.group_id("")


def test_identity_map_ignores_invalid_persisted_entries(tmp_path: Path) -> None:
    path = _identities_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"users": {"a": 0, "b": True, "c": "x", "d": 5}, "groups": "bad"}),
        encoding="utf-8",
    )

    identities = IdentityMap(tmp_path)
    assert identities.openid(5, "private") == "d"
    # 非法/越界的历史值不参与下一次分配。
    assert identities.user_id("e") == _USER_MIN


def test_message_id_map_is_stable_and_lru_bounded() -> None:
    mapping = MessageIdMap(max_size=2)
    first = mapping.next("official-1")
    assert mapping.next("official-1") == first
    second = mapping.next("official-2")
    third = mapping.next("official-3")

    assert mapping.official(first) is None
    assert mapping.official(second) == "official-2"
    assert mapping.official(third) == "official-3"

    # 命中会刷新 LRU：second 变成最近使用，随后淘汰 third。
    assert mapping.official(second) == "official-2"
    fourth = mapping.next("official-4")
    assert mapping.official(third) is None
    assert mapping.official(fourth) == "official-4"


def test_message_id_map_rejects_empty_official_id() -> None:
    with pytest.raises(ValueError):
        MessageIdMap().next("")

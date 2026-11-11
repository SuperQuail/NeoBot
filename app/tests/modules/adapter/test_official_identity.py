"""官方身份映射测试。

覆盖：openid ↔ 13 位合成号的两段分配、持久化与重启恢复、损坏文件兜底，
以及官方消息 id ↔ OneBot 合成 int 的稳定映射、上下文/引用索引与 LRU 淘汰。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from neobot_adapter.official.identity import IdentityMap, MessageIdMap

_USER_MIN = 9_000_000_000_000
_USER_MAX = 9_500_000_000_000
_GROUP_MIN = 9_500_000_000_000
_GROUP_MAX = 10_000_000_000_000


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _identities_path(work_dir: Path) -> Path:
    return work_dir / "qqbot" / "identities.json"


def test_identity_map_allocates_13_digit_segments(workdir: Path) -> None:
    identities = IdentityMap(workdir)
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


def test_identity_map_persists_and_recovers_after_restart(workdir: Path) -> None:
    first = IdentityMap(workdir)
    user = first.user_id("u1")
    group = first.group_id("g1")

    payload = json.loads(_identities_path(workdir).read_text(encoding="utf-8"))
    assert payload == {"users": {"u1": user}, "groups": {"g1": group}}

    restarted = IdentityMap(workdir)
    assert restarted.user_id("u1") == user
    assert restarted.group_id("g1") == group
    assert restarted.openid(user, "private") == "u1"
    # 新 openid 由 (app_id, 场景, openid) 确定性派生，不按消息顺序分配。
    assert restarted.user_id("u2") == first.user_id("u2")


def test_identity_map_keeps_corrupt_file_as_backup(workdir: Path) -> None:
    path = _identities_path(workdir)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    identities = IdentityMap(workdir)
    assert _USER_MIN <= identities.user_id("u1") < _USER_MAX
    assert path.with_name(path.name + ".corrupt").read_text(encoding="utf-8") == "{not json"


def test_identity_map_rejects_empty_openid(workdir: Path) -> None:
    identities = IdentityMap(workdir)
    with pytest.raises(ValueError):
        identities.user_id("  ")
    with pytest.raises(ValueError):
        identities.group_id("")


def test_identity_map_ignores_invalid_persisted_entries(workdir: Path) -> None:
    path = _identities_path(workdir)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"users": {"a": 0, "b": True, "c": "x", "d": 5}, "groups": "bad"}),
        encoding="utf-8",
    )

    identities = IdentityMap(workdir)
    assert identities.openid(5, "private") == "d"
    # 非法/越界的历史值不参与下一次分配；新 openid 落在合法用户段。
    assert _USER_MIN <= identities.user_id("e") < _USER_MAX


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


def test_message_id_map_stores_context_and_reference() -> None:
    mapping = MessageIdMap()
    synthetic = mapping.next(
        "official-1",
        context={"kind": "group", "openid": "group-openid", "at": 123.0},
    )

    assert mapping.context(synthetic) == {
        "kind": "group",
        "openid": "group-openid",
        "at": 123.0,
    }
    mapping.remember_reference(synthetic, "REFIDX_1==")
    assert mapping.reference(synthetic) == "REFIDX_1=="
    # 重复登记同一官方 id 时补齐上下文。
    assert mapping.next("official-1", context={"kind": "private"}) == synthetic
    assert mapping.context(synthetic) == {"kind": "private"}
    # 未登记过引用索引的消息返回 None。
    other = mapping.next("official-2")
    assert mapping.reference(other) is None


def test_message_id_map_evicts_context_and_reference_with_lru() -> None:
    mapping = MessageIdMap(max_size=1)
    first = mapping.next("official-1", context={"kind": "private"})
    mapping.remember_reference(first, "REFIDX_1==")
    mapping.next("official-2")

    assert mapping.official(first) is None
    assert mapping.context(first) is None
    assert mapping.reference(first) is None


def test_message_id_map_rejects_empty_official_id() -> None:
    with pytest.raises(ValueError):
        MessageIdMap().next("")


def test_identity_map_is_deterministic_without_persistence(workdir: Path) -> None:
    first = IdentityMap(workdir)
    user = first.user_id("same-openid")
    group = first.group_id("same-group")
    # 模拟 identities.json 丢失后的全新实例：同一 openid 仍得到同一合成号。
    shutil.rmtree(workdir / "qqbot", ignore_errors=True)
    restarted = IdentityMap(workdir)
    assert restarted.user_id("same-openid") == user
    assert restarted.group_id("same-group") == group


def test_identity_map_namespace_changes_derived_ids(workdir: Path) -> None:
    one = IdentityMap(workdir / "one", namespace="app-1")
    two = IdentityMap(workdir / "two", namespace="app-2")
    assert one.user_id("same-openid") != two.user_id("same-openid")


def test_identity_encode_decode_roundtrip(workdir: Path) -> None:
    identities = IdentityMap(workdir, namespace="app")
    user = identities.encode("openid-user", kind="user")
    group = identities.encode("openid-group", kind="group")

    assert identities.decode(user, kind="user") == "openid-user"
    assert identities.decode(group, kind="group") == "openid-group"
    assert identities.decode(user, kind="group") is None
    assert identities.decode(group, kind="user") is None
    assert identities.encode("openid-user", kind="user") == user

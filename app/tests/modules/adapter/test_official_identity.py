"""官方身份迁移表（只读）与消息 id 映射测试。

合成号已退出运行时：身份 ID 直接就是 openid；IdentityMap 只剩「旧
identities.json 合成号 → openid」的只读反查，供迁移期残留数据使用。
MessageIdMap（官方 msg_id ↔ OneBot int）不变，仍然覆盖稳定映射、上下文/引用与 LRU。
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

from neobot_adapter.official.identity import (
    IdentityMap,
    MessageIdMap,
    is_legacy_synthetic_id,
    resolve_openid,
)


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


def _write_identities(work_dir: Path, payload: dict) -> None:
    path = _identities_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_identity_map_is_legacy_read_only(workdir: Path) -> None:
    identities = IdentityMap(workdir, namespace="app", logger=None)

    assert identities.legacy is True
    # 运行时不再分配：旧的分配入口已移除。
    assert not hasattr(identities, "user_id")
    assert not hasattr(identities, "group_id")
    assert not hasattr(identities, "encode")
    assert not _identities_path(workdir).exists()


def test_identity_map_loads_legacy_mapping(workdir: Path) -> None:
    _write_identities(
        workdir,
        {"users": {"user-openid": 9_000_000_000_123}, "groups": {"group-openid": 9_500_000_000_123}},
    )

    identities = IdentityMap(workdir)
    assert identities.openid(9_000_000_000_123, "private") == "user-openid"
    assert identities.openid(9_000_000_000_123, "user") == "user-openid"
    assert identities.decode(9_500_000_000_123, kind="group") == "group-openid"
    assert identities.openid(9_500_000_000_123, "private") is None
    assert identities.openid("not-a-number", "user") is None


def test_identity_map_missing_or_corrupt_file_is_empty(workdir: Path) -> None:
    assert IdentityMap(workdir).openid(9_000_000_000_001) is None

    path = _identities_path(workdir)
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    identities = IdentityMap(workdir)
    assert identities.openid(9_000_000_000_001) is None
    # 只读迁移表不修改/备份历史文件（避免迁移期产生写放大）。
    assert path.read_text(encoding="utf-8") == "{not json"


def test_identity_map_ignores_invalid_persisted_entries(workdir: Path) -> None:
    _write_identities(
        workdir,
        {"users": {"a": 0, "b": True, "c": "x", "d": 9_000_000_000_005, "": 9_000_000_000_006}, "groups": "bad"},
    )

    identities = IdentityMap(workdir)
    assert identities.openid(9_000_000_000_005) == "d"
    assert identities.openid(9_000_000_000_006) is None
    assert IdentityMap(workdir / "missing").openid(9_000_000_000_005) is None


def test_is_legacy_synthetic_id_detects_13_digit_legacy_ids() -> None:
    assert is_legacy_synthetic_id(9_000_000_000_123)
    assert is_legacy_synthetic_id("9000000000123")
    assert not is_legacy_synthetic_id("12345678901")  # 真实 QQ 号 11 位
    assert not is_legacy_synthetic_id("123456789012")  # 真实群号 12 位
    assert not is_legacy_synthetic_id("openid-abc")
    assert not is_legacy_synthetic_id(None)


def test_resolve_openid_passthrough_and_legacy(workdir: Path) -> None:
    _write_identities(workdir, {"users": {"member-openid": 9_000_000_000_123}, "groups": {}})
    identities = IdentityMap(workdir)

    # openid 直通：非纯数字字符串原样返回。
    assert resolve_openid(identities, "user-openid", "user") == "user-openid"
    assert resolve_openid(None, "group-openid", "group") == "group-openid"
    # 旧 13 位合成号按只读映射反查。
    assert resolve_openid(identities, 9_000_000_000_123, "user") == "member-openid"
    assert resolve_openid(identities, "9000000000123", "user") == "member-openid"
    # 纯数字查不到映射时按 openid 原样透传（int 没有字符串形态，返回 None）。
    assert resolve_openid(identities, "1234567890123", "user") == "1234567890123"
    assert resolve_openid(identities, 1234567890123, "user") is None
    assert resolve_openid(identities, None, "user") is None
    assert resolve_openid(identities, "", "user") is None


def test_local_id_union_preserves_types() -> None:
    """model 层 LocalId：openid 字符串与数字字符串都不被转 int；OneBot int 保持 int。"""
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_adapter.model.response import GetSignalMsgData
    from neobot_adapter.utils.parse import safe_parse_model

    private = safe_parse_model(
        {"message_type": "private", "user_id": "openid-abc", "message_id": 7, "self_id": 1020304},
        PrivateMessage,
    )
    assert private.user_id == "openid-abc" and isinstance(private.user_id, str)
    assert private.message_id == 7 and isinstance(private.message_id, int)
    assert private.self_id == 1020304 and isinstance(private.self_id, int)

    numeric = safe_parse_model({"message_type": "private", "user_id": "123456", "message_id": 8}, PrivateMessage)
    assert numeric.user_id == "123456" and isinstance(numeric.user_id, str)
    as_int = safe_parse_model({"message_type": "private", "user_id": 123456, "message_id": 9}, PrivateMessage)
    assert as_int.user_id == 123456 and isinstance(as_int.user_id, int)

    group = safe_parse_model(
        {"message_type": "group", "group_id": "group-openid", "user_id": "member-openid", "message_id": 10},
        GroupMessage,
    )
    assert group.group_id == "group-openid" and group.user_id == "member-openid"

    signal = safe_parse_model({"self_id": 1, "user_id": "u", "group_id": 2, "message_id": 3}, GetSignalMsgData)
    assert signal.self_id == 1 and isinstance(signal.self_id, int)
    assert signal.user_id == "u" and signal.group_id == 2 and signal.message_id == 3


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
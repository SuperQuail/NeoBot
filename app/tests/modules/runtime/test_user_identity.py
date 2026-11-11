"""user_identity: 官方合成 ID ↔ QQ 号/群号人工映射。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from neobot_app.commands.model import PERM_SUB_ADMIN
from neobot_app.commands.permissions import PermissionManager
from neobot_app.user_identity import (
    bind_user_identity,
    display_group_id,
    display_user_id,
    group_label,
    group_number_for,
    id_label,
    link_group_number,
    link_user_qq,
    profile_identity,
    synthetic_for_group,
    qq_for_user,
    trusted_group_number_for,
    trusted_qq_for_user,
    unlink_group_number,
    unlink_user_qq,
)

RESERVED = 9000000000001
SYNTHETIC = 9000000000002
SYNTHETIC_GROUP = 8000000000002
REAL_QQ = 123456789
REAL_GROUP = 987654321


@pytest.fixture(autouse=True)
def _bind(tmp_path):
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


def test_link_and_display_synthetic_id_as_qq():
    ok, message = link_user_qq(SYNTHETIC, REAL_QQ)
    assert ok and "已映射" in message
    assert qq_for_user(SYNTHETIC) == REAL_QQ
    assert qq_for_user(SYNTHETIC, "official") == REAL_QQ
    assert display_user_id(SYNTHETIC) == f"QQ:{REAL_QQ}"
    assert id_label(SYNTHETIC) == "QQ"
    # agent 写入的映射不参与权限判定
    assert trusted_qq_for_user(SYNTHETIC) is None


def test_unmapped_synthetic_id_stays_id():
    assert qq_for_user(SYNTHETIC) is None
    assert display_user_id(SYNTHETIC) == f"ID:{SYNTHETIC}"
    assert id_label(SYNTHETIC) == "ID"


def test_mapping_persists_across_rebind(tmp_path):
    assert link_user_qq(SYNTHETIC, REAL_QQ, trusted=True)[0]
    bind_user_identity(tmp_path)
    assert qq_for_user(SYNTHETIC) == REAL_QQ
    assert trusted_qq_for_user(SYNTHETIC) == REAL_QQ


def test_agent_mapping_does_not_become_trusted():
    assert link_user_qq(SYNTHETIC, REAL_QQ)[0]
    assert qq_for_user(SYNTHETIC) == REAL_QQ
    assert trusted_qq_for_user(SYNTHETIC) is None


def test_link_validates_qq_and_user_id():
    assert link_user_qq(SYNTHETIC, "abc")[0] is False
    assert link_user_qq(SYNTHETIC, 123)[0] is False  # 太短，不是真实 QQ
    assert link_user_qq(0, REAL_QQ)[0] is False
    assert qq_for_user(SYNTHETIC) is None


def test_same_id_needs_no_mapping():
    ok, message = link_user_qq(REAL_QQ, REAL_QQ)
    assert ok and "无需映射" in message
    assert qq_for_user(REAL_QQ) is None


def test_unlink_removes_mapping():
    assert link_user_qq(SYNTHETIC, REAL_QQ)[0]
    ok, _ = unlink_user_qq(SYNTHETIC)
    assert ok
    assert qq_for_user(SYNTHETIC) is None
    assert unlink_user_qq(SYNTHETIC)[0] is False


def test_legacy_v1_mapping_is_readable_but_untrusted(tmp_path):
    (tmp_path / "user_qq_map.json").write_text(
        json.dumps({"aliases": {f"official:{SYNTHETIC}": REAL_QQ}}),
        encoding="utf-8",
    )
    bind_user_identity(tmp_path)

    assert qq_for_user(SYNTHETIC) == REAL_QQ
    assert trusted_qq_for_user(SYNTHETIC) is None


def test_group_mapping_and_display():
    ok, message = link_group_number(SYNTHETIC_GROUP, REAL_GROUP)
    assert ok and "已映射群" in message
    assert group_number_for(SYNTHETIC_GROUP) == REAL_GROUP
    assert display_group_id(SYNTHETIC_GROUP) == f"群号:{REAL_GROUP}"
    assert group_label(SYNTHETIC_GROUP) == "群号"
    # agent 写入的群映射只影响展示，不参与 ACL 判定
    assert trusted_group_number_for(SYNTHETIC_GROUP) is None
    assert display_group_id(8000000000003) == "群 ID:8000000000003"
    assert group_label(8000000000003) == "群 ID"
    # 12 位真实群号仍是群号（群号上限 12 位，比 QQ 号多一位）
    assert display_group_id(123456789012) == "群号:123456789012"
    assert group_label(123456789012) == "群号"
    assert unlink_group_number(SYNTHETIC_GROUP)[0]
    assert group_number_for(SYNTHETIC_GROUP) is None


def test_profile_identity_keeps_qq_and_id_labels():
    """档案身份展示：真实 QQ 号用 QQ号，合成 ID 用 QQ ID，映射后两者都给。"""
    assert profile_identity(REAL_QQ) == f"QQ号:{REAL_QQ}"
    assert profile_identity(SYNTHETIC) == f"QQ ID:{SYNTHETIC}"
    assert profile_identity("") == ""

    assert link_user_qq(SYNTHETIC, REAL_QQ, trusted=True)[0]
    assert profile_identity(SYNTHETIC) == f"QQ:{REAL_QQ}（QQ ID:{SYNTHETIC}）"


def test_group_mapping_validates_group_number():
    assert link_group_number(SYNTHETIC_GROUP, "abc")[0] is False
    assert link_group_number(SYNTHETIC_GROUP, 123)[0] is False
    assert link_group_number(0, REAL_GROUP)[0] is False


def test_agent_cannot_tamper_trusted_mapping():
    config = SimpleNamespace(chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[]))
    permissions = PermissionManager(config)
    assert link_user_qq(SYNTHETIC, REAL_QQ, trusted=True)[0]

    ok, message = link_user_qq(SYNTHETIC, 555555555)
    assert ok is False and "管理员命令" in message
    assert qq_for_user(SYNTHETIC) == REAL_QQ
    assert unlink_user_qq(SYNTHETIC)[0] is False
    assert trusted_qq_for_user(SYNTHETIC) == REAL_QQ
    assert permissions.can(SYNTHETIC, PERM_SUB_ADMIN) is False  # 配置里没有该 QQ


def test_permission_manager_uses_trusted_mapping_only():
    config = SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=[REAL_QQ], sub_admin_accounts=[REAL_QQ])
    )
    permissions = PermissionManager(config)

    assert link_user_qq(SYNTHETIC, REAL_QQ)[0]
    assert permissions.can(SYNTHETIC, PERM_SUB_ADMIN) is False

    assert link_user_qq(SYNTHETIC, REAL_QQ, trusted=True)[0]
    assert permissions.can(SYNTHETIC, PERM_SUB_ADMIN) is True
    assert permissions.is_super_admin(SYNTHETIC) is True


def test_developer_id_is_super_admin_only_when_in_config():
    """9000000000001 是 chat.admin_accounts 的默认值，不再由权限代码硬编码。"""
    without = PermissionManager(
        SimpleNamespace(chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[]))
    )
    assert without.is_super_admin(RESERVED) is False

    configured = PermissionManager(
        SimpleNamespace(chat=SimpleNamespace(admin_accounts=[RESERVED], sub_admin_accounts=[]))
    )
    assert configured.is_super_admin(RESERVED) is True
    assert configured.can(RESERVED, PERM_SUB_ADMIN) is True
    assert configured.is_super_admin(9000000000009) is False


def test_synthetic_for_group_reverse_lookup():
    assert link_group_number(SYNTHETIC_GROUP, REAL_GROUP, channel="official", trusted=True)[0]
    assert synthetic_for_group(REAL_GROUP, "official") == SYNTHETIC_GROUP
    assert synthetic_for_group(REAL_GROUP, "onebot") is None

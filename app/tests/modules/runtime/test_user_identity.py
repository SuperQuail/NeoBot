"""user_identity: 官方合成 ID ↔ QQ 号人工映射。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.commands.model import PERM_SUB_ADMIN
from neobot_app.commands.permissions import PermissionManager
from neobot_app.user_identity import (
    bind_user_identity,
    display_user_id,
    id_label,
    link_user_qq,
    qq_for_user,
    unlink_user_qq,
)

SYNTHETIC = 9000000000001
REAL_QQ = 123456789


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


def test_unmapped_synthetic_id_stays_id():
    assert qq_for_user(SYNTHETIC) is None
    assert display_user_id(SYNTHETIC) == f"ID:{SYNTHETIC}"
    assert id_label(SYNTHETIC) == "ID"


def test_mapping_persists_across_rebind(tmp_path):
    assert link_user_qq(SYNTHETIC, REAL_QQ)[0]
    bind_user_identity(tmp_path)
    assert qq_for_user(SYNTHETIC) == REAL_QQ


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


def test_permission_manager_resolves_mapped_qq():
    config = SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=[REAL_QQ], sub_admin_accounts=[REAL_QQ])
    )
    assert link_user_qq(SYNTHETIC, REAL_QQ)[0]
    permissions = PermissionManager(config)
    assert permissions.can(SYNTHETIC, PERM_SUB_ADMIN) is True
    assert permissions.is_super_admin(SYNTHETIC) is True
    assert permissions.can(9000000000002, PERM_SUB_ADMIN) is False

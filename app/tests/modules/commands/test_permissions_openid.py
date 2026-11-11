"""管理员配置支持 openid（本地 ID 统一按字符串比较）。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.model import PERM_SUB_ADMIN, PERM_SUPER_ADMIN
from neobot_app.commands.permissions import PermissionManager

OPENID = "OPENID-ADMIN-abc123"
OPENID_SUB = "OPENID-SUB-def456"


def _manager(admins=(), subs=()):
    config = SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=list(admins), sub_admin_accounts=list(subs))
    )
    return PermissionManager(config)


def test_openid_in_admin_accounts_is_super_admin() -> None:
    manager = _manager([OPENID])
    assert manager.super_admins == {OPENID}
    assert manager.is_super_admin(OPENID) is True
    assert manager.can(OPENID, PERM_SUPER_ADMIN) is True


def test_numeric_qq_in_admin_accounts_still_works() -> None:
    manager = _manager(["10000"])
    assert manager.is_super_admin(10000) is True
    assert manager.is_super_admin("10000") is True


def test_openid_sub_admin_is_not_super_admin() -> None:
    manager = _manager([OPENID], [OPENID_SUB])
    assert manager.is_sub_admin(OPENID_SUB) is True
    assert manager.can(OPENID_SUB, PERM_SUB_ADMIN) is True
    assert manager.is_super_admin(OPENID_SUB) is False


def test_describe_counts_openid_admins() -> None:
    manager = _manager([OPENID], [OPENID_SUB])
    text = manager.describe()
    assert "超级管理员 1 人" in text
    assert "次级管理员 1 人" in text

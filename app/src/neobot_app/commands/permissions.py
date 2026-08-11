"""权限树:超级管理员 / 次级管理员 / 所有人。

超级管理员来源:config.chat.admin_accounts(仅配置增减,命令不可修改)。
次级管理员来源:config.chat.sub_admin_accounts(超级管理员可通过命令增删)。
权限判断动态读取 ConfigProxy,配合配置热重载实时生效。
"""

from __future__ import annotations

from typing import Any

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
)


class PermissionManager:
    def __init__(self, config: Any) -> None:
        self._config = config  # ConfigProxy,动态读取

    @property
    def super_admins(self) -> set[int]:
        """超级管理员 QQ 号集合(配置不可被命令修改)。"""
        return self._admin_set("admin_accounts")

    @property
    def sub_admins(self) -> set[int]:
        """次级管理员 QQ 号集合(命令可增删)。"""
        return self._admin_set("sub_admin_accounts")

    def _admin_set(self, field: str) -> set[int]:
        chat = getattr(self._config, "chat", None) if self._config is not None else None
        if chat is None:
            return set()
        values = getattr(chat, field, None) or []
        result: set[int] = set()
        for value in values:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def is_super_admin(self, user_id: int | str) -> bool:
        return int(user_id) in self.super_admins

    def is_sub_admin(self, user_id: int | str) -> bool:
        uid = int(user_id)
        return uid in self.sub_admins or uid in self.super_admins

    def can(self, user_id: int | str, level: int) -> bool:
        """用户是否具备指定权限等级。"""
        if level <= PERM_EVERYONE:
            return True
        if level == PERM_SUB_ADMIN:
            return self.is_sub_admin(user_id)
        if level == PERM_SUPER_ADMIN:
            return self.is_super_admin(user_id)
        return False

    def describe(self) -> str:
        supers = "、".join(str(uid) for uid in sorted(self.super_admins)) or "(未配置)"
        subs = "、".join(str(uid) for uid in sorted(self.sub_admins)) or "(无)"
        return f"超级管理员: {supers}\n次级管理员: {subs}"

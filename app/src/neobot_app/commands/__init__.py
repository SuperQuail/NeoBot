"""内建命令系统:权限树 / 命令注册表 / 解析 / 执行。

设计:
- 触发方式:群聊被 @bot + `/` 前缀;私聊直接 `/` 前缀
- 解析:`/` 前后允许任意数量空格,不允许其他字符;非法命令移交正常聊天管线
- 权限树:超级管理员(config.chat.admin_accounts,只能配置增减) /
  次级管理员(config.chat.sub_admin_accounts,命令可增删) / 所有人
- 命令默认顶掉回复管线,可配置 sync_reply 同步触发回复管线
- bot 自己也可查看/触发命令
"""

from __future__ import annotations

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
    Command,
    CommandContext,
    CommandHandleResult,
)
from neobot_app.commands.permissions import PermissionManager
from neobot_app.commands.registry import CommandRegistry

__all__ = [
    "PERM_EVERYONE",
    "PERM_SUB_ADMIN",
    "PERM_SUPER_ADMIN",
    "Command",
    "CommandContext",
    "CommandHandleResult",
    "CommandRegistry",
    "PermissionManager",
]

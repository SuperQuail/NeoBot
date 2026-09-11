"""命令模型与权限常量。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from neobot_app.commands.service import CommandService

# 权限等级
PERM_EVERYONE = 0  # 所有人
PERM_SUB_ADMIN = 1  # 次级管理员(命令可增删)
PERM_SUPER_ADMIN = 2  # 超级管理员(仅配置增减)

_PERM_NAMES = {
    PERM_EVERYONE: "所有人",
    PERM_SUB_ADMIN: "次级管理员",
    PERM_SUPER_ADMIN: "超级管理员",
}


def permission_name(level: int) -> str:
    return _PERM_NAMES.get(level, f"等级{level}")


@dataclass
class CommandHandleResult:
    """命令处理结果。

    consumed=True:命令已处理,顶掉回复管线;
    background 非空:命令已处理,但需同步触发回复管线(结果作为背景内容)。
    """

    consumed: bool = False
    background: str | None = None


@dataclass(frozen=True)
class ConfigSaveResult:
    """配置写回结果。

    命令层据此区分「真的写进磁盘并生效」与「看起来成功」：
    早期实现只返回字符串，写盘静默失败时命令照样回复成功，
    于是 /add_admin 加了管理员、重启后却没了。
    """

    ok: bool
    error: str = ""
    #: 写盘后回读到的次级管理员列表（规范化后的字符串）
    accounts: tuple[str, ...] = ()
    #: 是否已经把新配置热重载进当前进程（False 表示需重启生效）
    applied: bool = False
    #: 实际写入的配置文件路径（用于失败提示）
    path: str = ""


@dataclass
class CommandContext:
    """命令执行上下文。"""

    service: "CommandService"
    kind: str  # group / private
    conv_id: str
    user_id: int
    command: Command
    raw_args: str
    args: list[str]
    at_qqs: list[int]
    message: Any = None

    async def reply(self, text: str) -> None:
        """向当前会话发送回复(群聊 at 发起者)。"""
        await self.service.reply_to(self.kind, self.conv_id, text, at_user_id=self.user_id)

    async def reply_plain(self, text: str) -> None:
        """向当前会话发送回复(不带 at)。"""
        await self.service.reply_to(self.kind, self.conv_id, text, at_user_id=None)


@dataclass
class Command:
    """一条命令定义。"""

    name: str
    description: str
    handler: Callable[[CommandContext], Awaitable[str | None]]
    permission: int = PERM_EVERYONE
    usage: str = ""
    params: tuple[tuple[str, str], ...] = ()  # (参数名, 说明),用于 /help <命令> 详情
    sync_reply: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def display_name(self) -> str:
        return f"/{self.name}"

    @property
    def help_line(self) -> str:
        usage = f" {self.usage}" if self.usage else ""
        return f"{self.display_name}{usage} — {self.description} [权限:{permission_name(self.permission)}]"

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("命令名不能为空")
        if any(char.isspace() for char in self.name):
            raise ValueError(f"命令名不能包含空白: {self.name!r}")

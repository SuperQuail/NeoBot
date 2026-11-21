"""跨聊天会话记录（持久化模型）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CrossChatSessionRecord:
    """一条跨聊天交互记录。

    ``boot_id`` 是写入时进程的启动标识：查询只返回与当前进程一致的记录，
    因此重启后旧的 session 不会显示（数据仍留在库里，等待后续清理策略）。
    """

    origin_kind: str
    origin_id: str
    target_kind: str
    target_id: str
    task_id: str
    mode: str
    notification_mode: str
    status: str
    reply: str
    boot_id: str
    created_at: datetime
    updated_at: datetime

    @property
    def origin_key(self) -> str:
        return f"{self.origin_kind}:{self.origin_id}"

    @property
    def target_key(self) -> str:
        return f"{self.target_kind}:{self.target_id}"

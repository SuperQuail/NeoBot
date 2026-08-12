"""凭据数据模型与动作权限映射。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from neobot_app.commands.model import PERM_SUB_ADMIN, PERM_SUPER_ADMIN

# 凭据类型
CRED_TYPE_ONE_TIME = "one_time"  # 一次性:使用后失效
CRED_TYPE_TIMED = "timed"  # 时间凭据:签发后持续一段时间

# 凭据状态
CRED_STATUS_PENDING = "pending"  # 等待管理员发送确认
CRED_STATUS_ACTIVE = "active"  # 已签发,可用
CRED_STATUS_USED = "used"  # 已消费
CRED_STATUS_EXPIRED = "expired"  # 已过期/已撤销

# 需要凭据的动作 → 签发者最低等级
# 踢人/退群需要超级管理员凭据;新动作在此追加
ACTION_REQUIRED_LEVEL: dict[str, int] = {
    "kick": PERM_SUPER_ADMIN,
    "quit_group": PERM_SUPER_ADMIN,
    # 设置全局回复意愿(运行时,影响所有群聊;私聊固定百分百不受影响)
    "willing_global": PERM_SUB_ADMIN,
    # 查看/编辑 config 中的全局回复意愿系数(持久化,热重载)
    "willing_config": PERM_SUPER_ADMIN,
}

# 未登记动作的默认签发等级
DEFAULT_REQUIRED_LEVEL = PERM_SUPER_ADMIN


@dataclass
class Credential:
    """一条凭据。"""

    code: str  # 短文本,管理员在聊天中发送
    chat_flow: str  # 绑定的聊天流,如 "group:123456" / "private:123"
    action: str  # 用途,如 "kick" / "quit_group"
    cred_type: str  # one_time / timed
    duration_minutes: int  # timed 有效时长(签发后计时)
    required_level: int  # 签发者最低等级
    requester_id: int  # 申请者 QQ
    status: str = CRED_STATUS_PENDING
    issuer_id: int | None = None  # 签发者 QQ
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # timed:签发时间 + 时长
    used_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "chat_flow": self.chat_flow,
            "action": self.action,
            "cred_type": self.cred_type,
            "duration_minutes": self.duration_minutes,
            "required_level": self.required_level,
            "requester_id": self.requester_id,
            "status": self.status,
            "issuer_id": self.issuer_id,
            "expires_at": self.expires_at,
        }

    def is_expired(self, now: float | None = None) -> bool:
        if self.status != CRED_STATUS_ACTIVE:
            return False
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) > self.expires_at

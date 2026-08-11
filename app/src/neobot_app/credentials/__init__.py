"""凭据管理器:对聊天流绑定的风险操作授权。

流程:
1. bot 通过 credential__request 申请凭据(action, 一次性/时间凭据)
2. bot 在聊天中请求管理员发送凭据文本
3. 管理员(超管/次级)发送该文本 → 签发凭据(校验签发者等级)
4. 风险操作(kick/quit_group 等)执行前校验并消费凭据

规则:
- 凭据与聊天流绑定:在哪个会话申请/签发,只能在哪个会话使用
- 一次性凭据:使用一次即失效;时间凭据:签发后持续 duration 分钟
- 默认有效 5 分钟,最长 30 分钟
- 踢人/退群等动作要求超级管理员凭据
"""

from __future__ import annotations

from neobot_app.credentials.model import (
    CRED_STATUS_ACTIVE,
    CRED_STATUS_EXPIRED,
    CRED_STATUS_PENDING,
    CRED_STATUS_USED,
    CRED_TYPE_ONE_TIME,
    CRED_TYPE_TIMED,
    ACTION_REQUIRED_LEVEL,
    DEFAULT_REQUIRED_LEVEL,
    Credential,
)
from neobot_app.credentials.service import CredentialIssueResult, CredentialManager

__all__ = [
    "CRED_STATUS_ACTIVE",
    "CRED_STATUS_EXPIRED",
    "CRED_STATUS_PENDING",
    "CRED_STATUS_USED",
    "CRED_TYPE_ONE_TIME",
    "CRED_TYPE_TIMED",
    "ACTION_REQUIRED_LEVEL",
    "DEFAULT_REQUIRED_LEVEL",
    "Credential",
    "CredentialManager",
    "CredentialIssueResult",
]

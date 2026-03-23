"""Chat 服务装配"""

from __future__ import annotations

from neobot_contracts.ports.logging import Logger


def build_chat_service(
    *,
    provider: object | None = None,
    logger: Logger | None = None,
):
    """构建 chat 服务

    目前 chat 包的 Agent/Workflow 需要具体 Provider 实例，
    此函数作为未来完整装配的占位
    """
    # TODO: 当 chat 包完善后，在此组装 Agent/Workflow
    return None

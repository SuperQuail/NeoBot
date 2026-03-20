"""适配器装配"""

from __future__ import annotations

from neobot_adapter import OneBotAdapter
from neobot_adapter.gateway import OneBotGateway

from neobot_contracts.ports.gateway import BotGateway
from neobot_contracts.ports.logging import Logger, NullLogger


def build_adapter(*, logger: Logger | None = None) -> OneBotAdapter:
    return OneBotAdapter(logger=logger or NullLogger())


def build_gateway(adapter: OneBotAdapter) -> BotGateway:
    return OneBotGateway(adapter)

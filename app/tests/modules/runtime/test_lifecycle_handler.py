from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neobot_app.runtime.event_context import EventContext
from neobot_app.runtime.lifecycle_handler import LifecycleHandler


@pytest.mark.asyncio
async def test_normal_heartbeat_is_not_logged() -> None:
    logger = MagicMock()
    handler = LifecycleHandler(logger=logger)

    await handler.handle(
        EventContext(
            {
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "interval": 3000,
                "status": {"online": True, "good": True},
            }
        )
    )

    logger.info.assert_not_called()
    logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_abnormal_heartbeat_logs_warning() -> None:
    logger = MagicMock()
    handler = LifecycleHandler(logger=logger)
    status = {"online": False, "good": False}

    await handler.handle(
        EventContext(
            {
                "post_type": "meta_event",
                "meta_event_type": "heartbeat",
                "status": status,
            }
        )
    )

    logger.info.assert_not_called()
    logger.warning.assert_called_once_with(f"心跳状态异常: {status}")


@pytest.mark.asyncio
async def test_lifecycle_event_remains_logged() -> None:
    logger = MagicMock()
    handler = LifecycleHandler(logger=logger)

    await handler.handle(
        EventContext(
            {
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": "connect",
                "self_id": 123,
            }
        )
    )

    logger.info.assert_called_once_with(
        "收到元事件[lifecycle.connect] self_id=123"
    )

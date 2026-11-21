from __future__ import annotations

import asyncio
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


@pytest.mark.asyncio
async def test_on_connect_runs_only_for_connect_lifecycle_event() -> None:
    """on_connect 只在 lifecycle.connect 时触发；其余元事件/消息不触发。"""
    calls: list[str] = []

    async def on_connect() -> None:
        calls.append("connect")

    handler = LifecycleHandler(logger=MagicMock(), on_connect=on_connect)
    events = [
        {"post_type": "meta_event", "meta_event_type": "lifecycle", "sub_type": "enable"},
        {"post_type": "meta_event", "meta_event_type": "heartbeat", "status": {}},
        {"post_type": "message", "message_type": "private", "user_id": 1},
        {"post_type": "meta_event", "meta_event_type": "lifecycle", "sub_type": "connect"},
    ]
    for event in events:
        await handler.handle(EventContext(event))
        await asyncio.sleep(0)

    assert calls == ["connect"]


@pytest.mark.asyncio
async def test_on_connect_failure_is_logged_without_breaking_dispatch() -> None:
    """on_connect 抛错只记 warning，事件分发（含元事件日志）照旧。"""
    logger = MagicMock()

    async def on_connect() -> None:
        raise RuntimeError("api down")

    handler = LifecycleHandler(logger=logger, on_connect=on_connect)

    await handler.handle(
        EventContext(
            {
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": "connect",
            }
        )
    )
    await asyncio.sleep(0)

    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[0] == "连接后处理失败"
    logger.info.assert_called_once()

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_app.runtime.event_pipeline import EventPipeline
from neobot_app.skills.image_parse_skill import ImageParseSkill


@pytest.mark.asyncio
async def test_image_parse_empty_message_returns_structured_failure():
    skill = object.__new__(ImageParseSkill)

    result = await skill._extract_image_from_message(SimpleNamespace(message=[]))

    assert result[0] is None
    assert result[1]


@pytest.mark.asyncio
async def test_event_pipeline_name_resolution_uses_public_adapter():
    pipeline = object.__new__(EventPipeline)
    pipeline.adapter = AsyncMock()
    pipeline.adapter.get_stranger_info.return_value = SimpleNamespace(
        data=SimpleNamespace(nickname="Alice")
    )
    pipeline._profile_service = None
    pipeline._logger = AsyncMock()

    name = await pipeline._resolve_name(12345)

    assert name == "Alice"
    pipeline.adapter.get_stranger_info.assert_awaited_once_with(12345)


def test_legacy_adapter_request_models_import_with_package_relative_paths():
    from neobot_adapter.model.request import FriendRequest, Request

    assert Request() is not None
    assert FriendRequest(user_id=12345).user_id == 12345


def test_bilibili_prompt_module_uses_standard_datetime_module():
    from neobot_app.bilibili import prompts

    assert prompts.datetime.datetime is not None

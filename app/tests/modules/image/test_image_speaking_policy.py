"""Image understanding follows the same conversation policy as replies."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment, PrivateMessage
from neobot_app.image.parser import ImageParseService
from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
from neobot_app.skills.image_parse_skill import ImageParseSkill
from neobot_contracts.ports.speaking import SpeakingDecision, SpeechBlocked


def setup_policy():
    gate = [True]
    registry = SpeakingPolicyRegistry()
    registry.register("speaking_schedule", lambda c: SpeakingDecision(gate[0] or c.id == "99", "quiet"))
    return gate, SimpleNamespace(core=SimpleNamespace(speaking_policy=registry))


def message(kind):
    cls = GroupMessage if kind == "group" else PrivateMessage
    kwargs = {"group_id": 42} if kind == "group" else {}
    return cls(
        message_id=1,
        user_id=7,
        sender=PostMessageMessagesender(user_id=7),
        message=[MessageSegment(type="image", data={"url": "https://example.invalid/image.png"})],
        **kwargs,
    )


@pytest.mark.parametrize("kind", ["group", "private"])
async def test_quiet_image_creates_no_download_or_pending_task(kind):
    gate, adapter = setup_policy()
    gate[0] = False
    service = ImageParseService(adapter=adapter)
    service._parse_single_image = AsyncMock(return_value="description")
    msg = message(kind)
    await service.parse_message_images(msg, "queue")
    await service.wait_for_queue("queue")
    service._parse_single_image.assert_not_called()
    assert msg.message[0].type == "image"
    assert not service._pending
    gate[0] = True
    await asyncio.sleep(0)
    service._parse_single_image.assert_not_called()  # No delayed catch-up.
    await service.parse_message_images(msg, "queue")
    await service.wait_for_queue("queue")
    service._parse_single_image.assert_awaited_once()


async def test_closing_while_downloading_does_not_call_vision(monkeypatch):
    gate, adapter = setup_policy()
    provider = SimpleNamespace(chat=AsyncMock(return_value={"content": "description"}))
    service = ImageParseService(adapter=adapter, vision_provider=provider)

    async def download(_segment):
        gate[0] = False
        return b"fake-bytes", None

    service._download_image_with_reason = download
    monkeypatch.setattr("neobot_app.image.parser._build_vision_image_part", lambda *a, **kw: {})
    msg = message("group")
    await service.parse_message_images(msg, "42")
    await service.wait_for_queue("42")
    provider.chat.assert_not_called()
    assert msg.message[0].type == "image"
    assert not service._pending


@pytest.mark.parametrize("key,blocked", [("group:42", True), ("private:7", True), ("group:99", False)])
async def test_explicit_image_tool_checks_conversation(key, blocked):
    gate, adapter = setup_policy()
    gate[0] = False
    provider = SimpleNamespace(chat=AsyncMock(return_value={"content": "description"}))
    skill = ImageParseSkill(vision_provider=provider, adapter=adapter)
    args = {"pipeline_key": key, "image_url": "https://example.invalid/image.png"}
    if blocked:
        with pytest.raises(SpeechBlocked):
            await skill.execute("parse_image", args)
        provider.chat.assert_not_called()
    else:
        await skill.execute("parse_image", args)
        provider.chat.assert_awaited_once()


async def test_explicit_tool_rechecks_after_image_resolution(monkeypatch):
    gate, adapter = setup_policy()
    provider = SimpleNamespace(chat=AsyncMock(return_value={"content": "description"}))
    skill = ImageParseSkill(vision_provider=provider, adapter=adapter)

    async def resolve(*args, **kwargs):
        gate[0] = False
        return b"fake-bytes", None

    skill._resolve_by_message_id_with_error = AsyncMock(side_effect=resolve)
    monkeypatch.setattr("neobot_app.image.parser._build_vision_image_part", lambda *a, **kw: {})
    with pytest.raises(SpeechBlocked):
        await skill.execute("parse_image", {"pipeline_key": "group:42", "message_id": 1})
    provider.chat.assert_not_called()


async def test_concurrent_image_conversations_keep_override_isolated(monkeypatch):
    gate, adapter = setup_policy()
    provider = SimpleNamespace(chat=AsyncMock(return_value={"content": "description"}))
    service = ImageParseService(adapter=adapter, vision_provider=provider)

    async def download(_segment):
        await asyncio.sleep(0)
        gate[0] = False
        return b"fake-bytes", None

    service._download_image_with_reason = download
    monkeypatch.setattr("neobot_app.image.parser._build_vision_image_part", lambda *a, **kw: {})
    blocked, allowed = message("group"), message("group")
    allowed.group_id = 99
    await service.parse_message_images(blocked, "42")
    await service.parse_message_images(allowed, "99")
    await asyncio.gather(service.wait_for_queue("42"), service.wait_for_queue("99"))
    provider.chat.assert_awaited_once()
    assert blocked.message[0].type == "image"
    assert allowed.message[0].type == "text"
    assert not service._pending

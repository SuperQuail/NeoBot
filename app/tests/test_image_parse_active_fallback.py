from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.image.parser import ImageParseService
from neobot_app.message.queue import MessageQueue
from neobot_app.skills.image_parse_skill import ImageParseSkill


def _group_message(
    message_id: int,
    *segments: tuple[str, dict],
) -> GroupMessage:
    return GroupMessage(
        message_id=message_id,
        user_id=7,
        group_id=42,
        sender=PostMessageMessagesender(
            user_id=7,
            nickname="tester",
        ),
        message=[
            MessageSegment(type=segment_type, data=data)
            for segment_type, data in segments
        ],
        raw_message="",
    )


async def _replace_images_with_auto_descriptions(
    message: GroupMessage,
    queue_key: str = "42",
) -> None:
    """使用当前自动解析实现制造真实的“队列图片已被替换”状态。"""
    service = ImageParseService()
    service._parse_single_image = AsyncMock(
        return_value="[图片：自动解析结果]"
    )
    await service.parse_message_images(message, queue_key)
    await service.wait_for_queue(queue_key)


def _build_skill(
    queue: MessageQueue,
    raw_messages: dict[int, GroupMessage],
) -> tuple[ImageParseSkill, SimpleNamespace]:
    async def get_msg(message_id: int):
        message = raw_messages.get(message_id)
        return SimpleNamespace(data=message)

    adapter = SimpleNamespace(
        get_msg=AsyncMock(side_effect=get_msg),
        call_api=AsyncMock(),
    )
    skill = ImageParseSkill(
        vision_provider=object(),
        adapter=adapter,
        group_message_queue=queue,
    )

    async def download(segment_data: dict, *, timeout: float = 30.0):
        del timeout
        file_name = segment_data.get("file")
        if not file_name:
            return None, "missing file"
        return str(file_name).encode(), None

    skill._download_image_segment = AsyncMock(side_effect=download)
    return skill, adapter


@pytest.mark.asyncio
async def test_msg_number_recovers_image_replaced_by_automatic_parser():
    message = _group_message(
        1001,
        ("image", {"file": "first.jpg", "url": "https://expired.invalid/1"}),
    )
    raw_message = message.model_copy(deep=True)
    queue = MessageQueue()
    queue.push("42", message)

    await _replace_images_with_auto_descriptions(message)
    assert message.message
    assert message.message[0].type == "text"

    skill, adapter = _build_skill(queue, {1001: raw_message})
    image, error = await skill._resolve_by_msg_number(
        "group:42",
        1,
        numbering_mapping={1: 1001},
    )

    assert image == b"first.jpg"
    assert error is None
    adapter.get_msg.assert_awaited_once_with(1001)


@pytest.mark.asyncio
async def test_msg_number_recovers_multiple_images_with_one_adapter_lookup():
    message = _group_message(
        1002,
        ("image", {"file": "first.jpg"}),
        ("text", {"text": "between"}),
        ("image", {"file": "second.jpg"}),
    )
    raw_message = message.model_copy(deep=True)
    queue = MessageQueue()
    queue.push("42", message)
    await _replace_images_with_auto_descriptions(message)

    skill, adapter = _build_skill(queue, {1002: raw_message})
    results = await skill._resolve_many_by_msg_number(
        "group:42",
        3,
        [0, 1],
        numbering_mapping={3: 1002},
    )

    assert results == [(b"first.jpg", None), (b"second.jpg", None)]
    adapter.get_msg.assert_awaited_once_with(1002)


@pytest.mark.asyncio
async def test_replied_message_number_recovers_original_image_from_adapter():
    referenced = _group_message(
        2001,
        ("image", {"file": "referenced.jpg"}),
    )
    raw_referenced = referenced.model_copy(deep=True)
    reply = _group_message(
        2002,
        ("text", {"text": "解析这张图"}),
    )
    queue = MessageQueue()
    queue.push("42", reply, replied_messages=[referenced])
    await _replace_images_with_auto_descriptions(referenced)

    skill, adapter = _build_skill(queue, {2001: raw_referenced})
    image, error = await skill._resolve_by_msg_number(
        "group:42",
        8,
        numbering_mapping={8: 2001},
    )

    assert image == b"referenced.jpg"
    assert error is None
    adapter.get_msg.assert_awaited_once_with(2001)


@pytest.mark.asyncio
async def test_chat_flow_recovers_image_replaced_by_automatic_parser():
    message = _group_message(
        3001,
        ("image", {"file": "flow.jpg"}),
    )
    raw_message = message.model_copy(deep=True)
    queue = MessageQueue()
    queue.push("42", message)
    await _replace_images_with_auto_descriptions(message)

    skill, adapter = _build_skill(queue, {3001: raw_message})
    image = await skill._resolve_by_chat_flow("Group_42", 0)

    assert image == b"flow.jpg"
    adapter.get_msg.assert_awaited_once_with(3001)

"""官方发送：Markdown 降级、被动回复限额、多段拆发与 4000 字切分。"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import NullLogger


from neobot_adapter.official.identity import IdentityMap, MessageIdMap
from neobot_adapter.official.media import MediaFile, MediaUploader
from neobot_adapter.official.send import (
    MessageSender,
    OfficialApiError,
    PassiveReplyCache,
)
from neobot_adapter.official.settings import OfficialSettings


@pytest.fixture
def workdir():
    """隔离落盘目录；pytest 的 tmp_path 用 0o700 建目录，本机沙箱下会拒绝访问。"""
    path = Path(tempfile.gettempdir()) / f"neobot-official-{uuid.uuid4().hex}"
    os.mkdir(path)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


class _FakeApi:
    """记录 POST 请求、按需抛错的官方 HTTP 桩。"""

    def __init__(self, *, fail_markdown_once: bool = False, failure: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._fail_markdown_once = fail_markdown_once
        self._failure = failure
        self._sent = 0

    async def request(self, method: str, path: str, *, body=None, timeout: float = 10.0) -> dict:
        self.calls.append({"method": method, "path": path, "body": dict(body or {})})
        if self._failure is not None:
            raise self._failure
        if self._fail_markdown_once and (body or {}).get("markdown"):
            self._fail_markdown_once = False
            raise OfficialApiError("不允许发送原生 markdown", code=40034004, status=400)
        self._sent += 1
        return {"code": 0, "data": {"id": f"ROBOT1.0_sent-{self._sent}"}}


class _RecordingLogger(NullLogger):
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, msg: str, **kw) -> None:
        self.warnings.append(msg)


def _sender(
    workdir,
    *,
    markdown: bool = True,
    clock=None,
    logger=None,
    api: _FakeApi | None = None,
):
    settings = OfficialSettings(
        app_id="app",
        client_secret="secret",
        markdown=markdown,
        data_dir=workdir,
    )
    identity = IdentityMap(workdir)
    message_ids = MessageIdMap()
    passive = PassiveReplyCache(clock=clock or time.monotonic)
    sender = MessageSender(
        api=api or _FakeApi(),
        settings=settings,
        identity=identity,
        message_ids=message_ids,
        passive=passive,
        media=MediaUploader(NullLogger()),
        logger=logger or NullLogger(),
    )
    return sender, api or sender._api, identity, passive, message_ids


def _private(identity: IdentityMap, openid: str = "user-openid") -> ConversationRef:
    return ConversationRef(kind="private", id=str(identity.user_id(openid)))


def _group(identity: IdentityMap, openid: str = "group-openid") -> ConversationRef:
    return ConversationRef(kind="group", id=str(identity.group_id(openid)))


async def test_text_defaults_to_markdown(workdir) -> None:
    sender, api, identity, _, message_ids = _sender(workdir)
    conversation = _private(identity)

    result = await sender.send(conversation, "你好")

    assert result.status == "ok"
    call = api.calls[0]
    assert call["path"] == f"/v2/users/{identity.openid(int(conversation.id), 'private')}/messages"
    assert call["body"]["msg_type"] == 2
    assert call["body"]["markdown"] == {"content": "你好"}
    assert isinstance(call["body"]["msg_seq"], int)
    assert result.data.message_id == message_ids.next("ROBOT1.0_sent-1")


async def test_markdown_disabled_sends_plain_content(workdir) -> None:
    sender, api, identity, _, _ = _sender(workdir, markdown=False)

    result = await sender.send(_private(identity), "你好")

    assert result.status == "ok"
    body = api.calls[0]["body"]
    assert body["msg_type"] == 0
    assert body["content"] == "你好"
    assert "markdown" not in body


async def test_markdown_rejected_falls_back_to_plain_text(workdir) -> None:
    api = _FakeApi(fail_markdown_once=True)
    sender, _, identity, _, _ = _sender(workdir, api=api)

    result = await sender.send(_private(identity), "**markdown**")

    assert result.status == "ok"
    assert len(api.calls) == 2
    fallback = api.calls[1]["body"]
    assert fallback["msg_type"] == 0
    assert fallback["content"] == "**markdown**"
    assert "markdown" not in fallback


async def test_passive_reply_limit_switches_to_proactive(workdir) -> None:
    logger = _RecordingLogger()
    sender, api, identity, passive, _ = _sender(workdir, logger=logger)
    conversation = _group(identity)
    passive.remember("group", int(conversation.id), "ROBOT1.0_user-msg")

    for _ in range(4):
        await sender.send(conversation, "回复")
    await sender.send(conversation, "超出限额")

    bodies = [call["body"] for call in api.calls]
    assert all(body.get("msg_id") == "ROBOT1.0_user-msg" for body in bodies[:4])
    assert "msg_id" not in bodies[4]
    assert any("主动推送" in message for message in logger.warnings)
    assert len([m for m in logger.warnings if "主动推送" in m]) == 1


async def test_expired_passive_target_switches_to_proactive(workdir) -> None:
    now = [0.0]
    logger = _RecordingLogger()
    sender, api, identity, passive, _ = _sender(workdir, clock=lambda: now[0], logger=logger)
    conversation = _group(identity)
    passive.remember("group", int(conversation.id), "ROBOT1.0_old")

    now[0] = 301.0
    await sender.send(conversation, "过期后的回复")

    assert "msg_id" not in api.calls[0]["body"]
    assert any("主动推送" in message for message in logger.warnings)


async def test_text_and_media_are_split_into_separate_messages(workdir, monkeypatch) -> None:
    sender, api, identity, _, _ = _sender(workdir)
    uploaded: list[dict] = []

    async def fake_upload(api, **kwargs):
        uploaded.append(kwargs)
        return MediaFile(file_info="FILE-INFO", file_uuid="FILE-UUID", ttl=0)

    monkeypatch.setattr(sender._media, "upload", fake_upload)

    result = await sender.send(
        _private(identity),
        [
            {"type": "text", "data": {"text": "看这个"}},
            {"type": "image", "data": {"file": "base64://YWJj"}},
        ],
    )

    assert result.status == "ok"
    assert len(api.calls) == 2
    assert api.calls[0]["body"]["markdown"] == {"content": "看这个"}
    media_body = api.calls[1]["body"]
    assert media_body["msg_type"] == 7
    assert media_body["media"]["file_info"] == "FILE-INFO"
    assert uploaded[0]["segment_type"] == "image"


async def test_long_text_is_split_without_losing_characters(workdir) -> None:
    sender, api, identity, _, _ = _sender(workdir)
    text = "a" * 3500 + "\n" + "b" * 1500

    result = await sender.send(_private(identity), text)

    assert result.status == "ok"
    assert len(api.calls) == 2
    chunks = [call["body"]["markdown"]["content"] for call in api.calls]
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks) == text


async def test_at_segment_becomes_nickname_text(workdir) -> None:
    sender, api, identity, _, _ = _sender(workdir)

    await sender.send(
        _group(identity),
        [
            {"type": "at", "data": {"qq": 42, "name": "小明"}},
            {"type": "text", "data": {"text": " 你好"}},
        ],
    )

    assert api.calls[0]["body"]["markdown"] == {"content": "@小明 你好"}


async def test_known_at_segment_uses_markdown_mention(workdir) -> None:
    """群聊 @ 用户用官方 markdown 内嵌格式 <qqbot-at-user id=member_openid />。"""
    sender, api, identity, _, _ = _sender(workdir)
    member_id = identity.user_id("member-openid")
    conversation = _group(identity)

    await sender.send(
        conversation,
        [
            {"type": "at", "data": {"qq": member_id, "name": "小明"}},
            {"type": "text", "data": {"text": " 你好"}},
        ],
    )

    body = api.calls[0]["body"]
    assert body["msg_type"] == 2
    assert body["markdown"]["content"] == '<qqbot-at-user id="member-openid" /> 你好'


async def test_at_mention_forces_markdown_even_when_markdown_disabled(workdir) -> None:
    sender, api, identity, _, _ = _sender(workdir, markdown=False)
    member_id = identity.user_id("member-openid")

    await sender.send(
        _group(identity),
        [
            {"type": "at", "data": {"qq": member_id, "name": "小明"}},
            {"type": "text", "data": {"text": " 你好"}},
        ],
    )

    assert api.calls[0]["body"]["msg_type"] == 2
    assert "<qqbot-at-user" in api.calls[0]["body"]["markdown"]["content"]


async def test_reply_segment_maps_back_to_official_message_id(workdir) -> None:
    sender, api, identity, _, message_ids = _sender(workdir)
    synthetic = message_ids.next("ROBOT1.0_quoted")

    await sender.send(
        _private(identity),
        [
            {"type": "reply", "data": {"id": synthetic}},
            {"type": "text", "data": {"text": "收到"}},
        ],
    )

    assert api.calls[0]["body"]["message_reference"] == {"message_id": "ROBOT1.0_quoted"}


async def test_unknown_conversation_returns_failed(workdir) -> None:
    sender, api, _, _, _ = _sender(workdir)

    result = await sender.send(ConversationRef(kind="private", id="9999999999999"), "在吗")

    assert result.status == "failed"
    assert "openid" in (result.message or "")
    assert api.calls == []


async def test_api_error_returns_failed_response(workdir) -> None:
    api = _FakeApi(failure=OfficialApiError("官方接口炸了", code=500))
    sender, _, identity, _, _ = _sender(workdir, api=api)

    result = await sender.send(_private(identity), "你好")

    assert result.status == "failed"
    assert "官方接口炸了" in (result.message or "")


async def test_auth_error_is_reported_as_failed_response(workdir) -> None:
    """token 获取失败不能从 send() 抛出，必须返回 failed 响应。"""
    from neobot_adapter.official.auth import OfficialAuthError

    sender, _api, identity, _, _ = _sender(
        workdir, api=_FakeApi(failure=OfficialAuthError("token boom"))
    )

    result = await sender.send(_private(identity), "你好")

    assert result.status == "failed"
    assert "token boom" in result.message

"""官方发送链路：纯文本 msg_type=0、显式 Markdown、被动回复限额与引用。

失败一律返回 failed 且只落 info 日志；这里同时锁死「没有自动降级/回退」：
Markdown 被拒、被动额度用尽、媒体失败都不会改发其它形态。
"""

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

from neobot_adapter.official.auth import OfficialAuthError
from neobot_adapter.official.identity import IdentityMap, MessageIdMap
from neobot_adapter.official.media import MediaFile, MediaUploader
from neobot_adapter.official.send import (
    MessageSender,
    OfficialApi,
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

    def __init__(self, *, failure: Exception | None = None, failure_on: int | None = None) -> None:
        self.calls: list[dict] = []
        self._failure = failure
        self._failure_on = failure_on
        self._sent = 0
        self.bot_role = "admin"

    async def request(self, method: str, path: str, *, body=None, timeout: float = 10.0) -> dict:
        index = len(self.calls)
        self.calls.append({"method": method, "path": path, "body": dict(body or {})})
        if method == "GET" and path.endswith("/bot_state"):
            return {"member_role": self.bot_role}
        if self._failure is not None and self._failure_on in (None, index):
            raise self._failure
        self._sent += 1
        return {
            "id": f"ROBOT1.0_sent-{self._sent}",
            "ext_info": {"ref_idx": f"REFIDX_sent-{self._sent}"},
        }


class _RecordingLogger(NullLogger):
    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []

    def info(self, msg: str, **kw) -> None:
        self.infos.append(msg)

    def warning(self, msg: str, **kw) -> None:
        self.warnings.append(msg)


def _sender(
    workdir,
    *,
    clock=None,
    logger=None,
    api: _FakeApi | None = None,
):
    identity = IdentityMap(workdir)
    message_ids = MessageIdMap()
    passive = PassiveReplyCache(clock=clock or time.monotonic)
    fake_api = api or _FakeApi()
    sender = MessageSender(
        api=fake_api,
        identity=identity,
        message_ids=message_ids,
        passive=passive,
        media=MediaUploader(NullLogger()),
        logger=logger or NullLogger(),
    )
    return sender, fake_api, identity, passive, message_ids


def _private(identity: IdentityMap, openid: str = "user-openid") -> ConversationRef:
    return ConversationRef(kind="private", id=str(identity.user_id(openid)))


def _group(identity: IdentityMap, openid: str = "group-openid") -> ConversationRef:
    return ConversationRef(kind="group", id=str(identity.group_id(openid)))


def _remember(passive: PassiveReplyCache, conversation: ConversationRef) -> None:
    passive.remember(conversation.kind, int(conversation.id), "ROBOT1.0_user-msg")


def _markdown(content: str) -> dict:
    return {"type": "official_markdown", "data": {"content": content}}


# ── 纯文本 ──────────────────────────────────────────────────────────


async def test_plain_text_is_always_msg_type_0(workdir) -> None:
    sender, api, identity, passive, message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, "你好")

    assert result.status == "ok"
    call = api.calls[0]
    assert call["path"] == f"/v2/users/{identity.openid(int(conversation.id), 'private')}/messages"
    assert call["body"]["msg_type"] == 0
    assert call["body"]["content"] == "你好"
    assert "markdown" not in call["body"]
    assert call["body"]["msg_id"] == "ROBOT1.0_user-msg"
    assert call["body"]["msg_seq"] == 1
    assert result.data.message_id == message_ids.next("ROBOT1.0_sent-1")


async def test_plain_text_without_passive_target_fails_instead_of_active_push(workdir) -> None:
    logger = _RecordingLogger()
    sender, api, identity, _passive, _message_ids = _sender(workdir, logger=logger)

    result = await sender.send(_private(identity), "在吗")

    assert result.status == "failed"
    assert "被动回复" in (result.message or "")
    assert api.calls == []
    assert any("未发送" in message for message in logger.infos)


async def test_passive_limit_is_five_for_group_and_seq_increments(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _group(identity)
    _remember(passive, conversation)

    results = [await sender.send(conversation, "回复") for _ in range(6)]

    assert [item.status for item in results[:5]] == ["ok"] * 5
    assert results[5].status == "failed"
    assert "上限" in (results[5].message or "")
    bodies = [call["body"] for call in api.calls]
    assert [body["msg_id"] for body in bodies] == ["ROBOT1.0_user-msg"] * 5
    assert [body["msg_seq"] for body in bodies] == [1, 2, 3, 4, 5]


async def test_passive_limit_is_four_for_private(workdir) -> None:
    sender, _api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    results = [await sender.send(conversation, "回复") for _ in range(5)]

    assert [item.status for item in results[:4]] == ["ok"] * 4
    assert results[4].status == "failed"


async def test_expired_passive_target_fails_explicitly(workdir) -> None:
    now = [0.0]
    sender, api, identity, passive, _message_ids = _sender(workdir, clock=lambda: now[0])
    conversation = _group(identity)
    _remember(passive, conversation)

    now[0] = 301.0
    result = await sender.send(conversation, "过期后的回复")

    assert result.status == "failed"
    assert "过期" in (result.message or "")
    assert api.calls == []


async def test_long_plain_text_is_split_without_losing_characters(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)
    text = "a" * 3500 + "\n" + "b" * 1500

    result = await sender.send(conversation, text)

    assert result.status == "ok"
    assert len(api.calls) == 2
    chunks = [call["body"]["content"] for call in api.calls]
    assert all(call["body"]["msg_type"] == 0 for call in api.calls)
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks) == text


async def test_at_segment_becomes_plain_text_mention(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _group(identity)
    _remember(passive, conversation)
    member_id = identity.user_id("member-openid")

    await sender.send(
        conversation,
        [
            {"type": "at", "data": {"qq": member_id, "name": "小明"}},
            {"type": "text", "data": {"text": " 你好"}},
        ],
    )

    body = api.calls[0]["body"]
    assert body["msg_type"] == 0
    assert body["content"] == "@小明 你好"


# ── 显式 Markdown ───────────────────────────────────────────────────


async def test_markdown_segment_sends_single_msg_type_2(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, [_markdown("## 标题\n- 列表")])

    assert result.status == "ok"
    assert len(api.calls) == 1
    body = api.calls[0]["body"]
    assert body["msg_type"] == 2
    assert body["markdown"] == {"content": "## 标题\n- 列表"}
    assert "content" not in body


async def test_markdown_embedded_at_user_is_rendered_to_openid(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _group(identity)
    _remember(passive, conversation)
    member_id = identity.user_id("member-openid")
    content = f'<qqbot-at-user id="{member_id}"> 你好 <qqbot-at-everyone /> <qqbot-cmd-input text="x" />'

    await sender.send(conversation, [_markdown(content)])

    markdown = api.calls[-1]["body"]["markdown"]["content"]
    assert '<qqbot-at-user id="member-openid" />' in markdown
    assert "<qqbot-at-everyone />" in markdown
    assert '<qqbot-cmd-input text="x" />' in markdown


async def test_markdown_unknown_at_user_fails_without_sending(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _group(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, [_markdown('<qqbot-at-user id="9000000009999"> 你好')])

    assert result.status == "failed"
    assert "openid" in (result.message or "")
    assert api.calls == []


async def test_markdown_at_user_in_private_fails(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)
    member_id = identity.user_id("member-openid")

    result = await sender.send(conversation, [_markdown(f'<qqbot-at-user id="{member_id}" /> 你好')])

    assert result.status == "failed"
    assert "单聊" in (result.message or "")
    assert api.calls == []


async def test_markdown_cannot_mix_with_text_or_media(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(
        conversation,
        [_markdown("## 标题"), {"type": "text", "data": {"text": "正文"}}],
    )

    assert result.status == "failed"
    assert "混用" in (result.message or "")
    assert api.calls == []


async def test_markdown_over_limit_fails_without_splitting(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, [_markdown("a" * 4001)])

    assert result.status == "failed"
    assert "4000" in (result.message or "")
    assert api.calls == []


async def test_empty_markdown_fails(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, [_markdown("   ")])

    assert result.status == "failed"
    assert api.calls == []


# ── 引用 ────────────────────────────────────────────────────────────


async def test_reply_segment_uses_remembered_reference_idx(workdir) -> None:
    sender, api, identity, passive, message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)
    synthetic = message_ids.next("ROBOT1.0_quoted")
    message_ids.remember_reference(synthetic, "REFIDX_quoted")

    await sender.send(
        conversation,
        [{"type": "reply", "data": {"id": synthetic}}, {"type": "text", "data": {"text": "收到"}}],
    )

    assert api.calls[0]["body"]["message_reference"] == {"message_id": "REFIDX_quoted"}


async def test_reply_without_reference_idx_is_not_filled(workdir) -> None:
    sender, api, identity, passive, message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)
    synthetic = message_ids.next("ROBOT1.0_quoted")

    await sender.send(
        conversation,
        [{"type": "reply", "data": {"id": synthetic}}, {"type": "text", "data": {"text": "收到"}}],
    )

    assert "message_reference" not in api.calls[0]["body"]


async def test_reply_direct_refidx_is_used(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    await sender.send(
        conversation,
        [{"type": "reply", "data": {"id": "REFIDX_direct"}}, {"type": "text", "data": {"text": "收到"}}],
    )

    assert api.calls[0]["body"]["message_reference"] == {"message_id": "REFIDX_direct"}


async def test_sent_response_ref_idx_and_context_are_remembered(workdir) -> None:
    sender, _api, identity, passive, message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, "你好")

    synthetic = result.data.message_id
    assert synthetic is not None
    assert message_ids.reference(synthetic) == "REFIDX_sent-1"
    context = message_ids.context(synthetic)
    assert context is not None
    assert context["kind"] == "private"
    assert context["openid"] == "user-openid"


# ── 媒体与失败处理 ──────────────────────────────────────────────────


async def test_text_and_media_are_sent_as_separate_messages(workdir, monkeypatch) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)
    uploaded: list[dict] = []

    async def fake_upload(api_arg, **kwargs):
        uploaded.append(kwargs)
        return MediaFile(file_info="FILE-INFO", file_uuid="FILE-UUID", ttl=0)

    monkeypatch.setattr(sender._media, "upload", fake_upload)

    result = await sender.send(
        conversation,
        [
            {"type": "text", "data": {"text": "看这个"}},
            {"type": "image", "data": {"file": "base64://YWJj"}},
        ],
    )

    assert result.status == "ok"
    assert len(api.calls) == 2
    assert api.calls[0]["body"]["msg_type"] == 0
    assert api.calls[0]["body"]["content"] == "看这个"
    media_body = api.calls[1]["body"]
    assert media_body["msg_type"] == 7
    assert media_body["media"]["file_info"] == "FILE-INFO"
    assert uploaded[0]["segment_type"] == "image"


async def test_media_failure_returns_failed_without_fallback(workdir, monkeypatch) -> None:
    from neobot_adapter.official.media import MediaUploadError

    logger = _RecordingLogger()
    sender, api, identity, passive, _message_ids = _sender(workdir, logger=logger)
    conversation = _private(identity)
    _remember(passive, conversation)

    async def failing_upload(api_arg, **kwargs):
        raise MediaUploadError("url not reachable", code=850026)

    monkeypatch.setattr(sender._media, "upload", failing_upload)

    result = await sender.send(
        conversation,
        [{"type": "image", "data": {"file": "https://example.com/a.png"}}],
    )

    assert result.status == "failed"
    assert "url not reachable" in (result.message or "")
    assert len(api.calls) == 0
    assert any("未发送" in message for message in logger.infos)


async def test_api_error_returns_failed_and_logs_info(workdir) -> None:
    logger = _RecordingLogger()
    api = _FakeApi(failure=OfficialApiError("接口炸了", code=40034005))
    sender, _api, identity, passive, _message_ids = _sender(workdir, api=api, logger=logger)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, "你好")

    assert result.status == "failed"
    assert "接口炸了" in (result.message or "")
    assert logger.infos


async def test_auth_error_is_reported_as_failed_response(workdir) -> None:
    sender, _api, identity, passive, _message_ids = _sender(
        workdir, api=_FakeApi(failure=OfficialAuthError("token boom"))
    )
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, "你好")

    assert result.status == "failed"
    assert "token boom" in (result.message or "")


async def test_unknown_conversation_returns_failed(workdir) -> None:
    sender, api, _identity, _passive, _message_ids = _sender(workdir)

    result = await sender.send(ConversationRef(kind="private", id="9999999999999"), "在吗")

    assert result.status == "failed"
    assert "openid" in (result.message or "")
    assert api.calls == []


async def test_empty_message_returns_failed(workdir) -> None:
    sender, api, identity, passive, _message_ids = _sender(workdir)
    conversation = _private(identity)
    _remember(passive, conversation)

    result = await sender.send(conversation, [])

    assert result.status == "failed"
    assert api.calls == []


# ── OfficialApi 错误码识别 ─────────────────────────────────────────


class _FakeTokenProvider:
    def __init__(self) -> None:
        self.forced = 0

    async def get_token(self, *, force: bool = False) -> str:
        if force:
            self.forced += 1
        return "tok"


class _FakeResponse:
    def __init__(self, status: int, payload) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> bool:
        return False


class _EmptyResponse(_FakeResponse):
    def __init__(self, status: int) -> None:
        super().__init__(status, None)

    async def json(self, content_type=None):
        raise ValueError("empty body")

    async def text(self) -> str:
        return ""


class _FakeSession:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.requests.append({"method": method, "url": url, "json": json})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return item


def _api(workdir, session) -> OfficialApi:
    settings = OfficialSettings(app_id="app", client_secret="secret", data_dir=workdir)
    return OfficialApi(settings, _FakeTokenProvider(), NullLogger(), http=session)


@pytest.mark.parametrize("payload", [{"err_code": 40034005}, {"code": 40054005}, {"biz_code": 304103}])
async def test_api_recognizes_business_error_codes(workdir, payload) -> None:
    api = _api(workdir, _FakeSession(_FakeResponse(200, dict(payload, message="失败"))))

    with pytest.raises(OfficialApiError) as excinfo:
        await api.request("POST", "/v2/users/u/messages", body={})

    expected = next(iter(payload.values()))
    assert excinfo.value.code == expected


async def test_api_accepts_http_200_success_body(workdir) -> None:
    body = {"id": "ROBOT1.0_x", "ext_info": {"ref_idx": "REFIDX_x"}}
    api = _api(workdir, _FakeSession(_FakeResponse(200, body)))

    assert await api.request("POST", "/v2/users/u/messages", body={}) == body


async def test_api_accepts_empty_delete_response(workdir) -> None:
    api = _api(workdir, _FakeSession(_EmptyResponse(204)))

    assert await api.request("DELETE", "/v2/users/u/messages/1") == {}


async def test_api_retries_once_after_401(workdir) -> None:
    token = _FakeTokenProvider()
    settings = OfficialSettings(app_id="app", client_secret="secret", data_dir=workdir)
    session = _FakeSession(_FakeResponse(401, {"message": "unauthorized"}), _FakeResponse(200, {"id": "ok"}))
    api = OfficialApi(settings, token, NullLogger(), http=session)

    assert await api.request("GET", "/users/@me") == {"id": "ok"}
    assert token.forced == 1
    assert len(session.requests) == 2


async def test_api_raises_on_http_error_status(workdir) -> None:
    api = _api(workdir, _FakeSession(_FakeResponse(500, {"err_code": 50055001, "message": "内部错误"})))

    with pytest.raises(OfficialApiError) as excinfo:
        await api.request("POST", "/v2/users/u/messages", body={})

    assert excinfo.value.code == 50055001
    assert excinfo.value.status == 500


async def test_markdown_at_everyone_requires_admin_role(workdir) -> None:
    sender, api, identity, passive, _ = _sender(workdir)
    conversation = _group(identity)
    _remember(passive, conversation)
    api.bot_role = "member"

    result = await sender.send(conversation, [_markdown("hello <qqbot-at-everyone />")])

    assert result.status == "failed"
    assert "群管理员" in result.message

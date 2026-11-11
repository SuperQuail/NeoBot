"""官方通道的合成 ID 不能渲染成 QQ 号。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.reply.orchestrator_parts.prompt_build import PromptBuildMixin
from neobot_app.runtime.pipeline_parts.helpers import _sender_name


def _message(
    *, channel: str, user_id: int = 9000000000001, group_id: int = 8000000000001
) -> SimpleNamespace:
    return SimpleNamespace(
        message_type="group",
        user_id=user_id,
        group_id=group_id,
        message=[],
        raw_message="",
        sender=SimpleNamespace(card="", nickname="张三"),
        neobot_channel=channel,
    )


def _event(*, channel: str, message=None) -> SimpleNamespace:
    return SimpleNamespace(message=message, neobot_channel=channel)


def test_official_group_context_uses_id_not_qq() -> None:
    text = PromptBuildMixin._build_chat_context(
        _event(channel="official", message=_message(channel="official")), "8000000000001"
    )
    assert "群 ID：" in text
    assert "（ID：" in text
    assert "QQ" not in text


def test_onebot_group_context_keeps_qq_label() -> None:
    text = PromptBuildMixin._build_chat_context(
        _event(
            channel="onebot",
            message=_message(channel="onebot", user_id=123456, group_id=456),
        ),
        "456",
    )
    assert "群号：" in text
    assert "（QQ：123456）" in text


def test_onebot_12_digit_group_number_keeps_group_label() -> None:
    """群号上限 12 位：12 位真实群号不能被当成官方群 ID。"""
    text = PromptBuildMixin._build_chat_context(
        _event(
            channel="onebot",
            message=_message(channel="onebot", user_id=123456, group_id=123456789012),
        ),
        "123456789012",
    )
    assert "群号：123456789012" in text
    assert "群 ID" not in text


def test_mapped_synthetic_id_displays_as_real_qq(tmp_path) -> None:
    from neobot_app.user_identity import bind_user_identity, link_user_qq

    synthetic = 9000000000001
    bind_user_identity(tmp_path)
    try:
        assert link_user_qq(synthetic, 123456789)[0]
        message = _message(channel="official")
        message.sender = None
        assert _sender_name(message) == "QQ:123456789"
        text = PromptBuildMixin._build_chat_context(
            _event(channel="official", message=message), "8000000000001"
        )
        assert "消息发送者QQ：123456789" in text
        assert "ID：9000000000001" not in text
    finally:
        bind_user_identity(None)


def test_mapped_official_group_shows_real_group_number(tmp_path) -> None:
    from neobot_app.user_identity import bind_user_identity, link_group_number

    group_id = 8000000000001
    bind_user_identity(tmp_path)
    try:
        assert link_group_number(group_id, 123456789)[0]
        text = PromptBuildMixin._build_chat_context(
            _event(channel="official", message=_message(channel="official", group_id=group_id)),
            str(group_id),
        )
        assert "群号：123456789" in text
        assert "群 ID" not in text
    finally:
        bind_user_identity(None)


def test_sender_name_fallback_label_follows_channel() -> None:
    official = _message(channel="official")
    official.sender = None
    assert _sender_name(official) == "ID:9000000000001"

    onebot = _message(channel="onebot", user_id=123456)
    onebot.sender = None
    assert _sender_name(onebot) == "QQ:123456"

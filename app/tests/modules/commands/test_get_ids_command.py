"""/get openid / groupid：只读展示当前通道本地 ID。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.service import CommandService


def _config() -> SimpleNamespace:
    chat = SimpleNamespace(admin_accounts=[], sub_admin_accounts=[])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=0))


def _service() -> tuple[CommandService, list[tuple]]:
    sent: list[tuple] = []

    async def send(*args, **kwargs) -> None:
        sent.append((args, kwargs))

    service = CommandService(
        config=_config(),
        adapter=SimpleNamespace(send=lambda c, s: None),
        send_callback=send,
        register_builtins=True,
    )
    return service, sent


def _message(
    text: str,
    *,
    user_id: str = "OPENID-SELF",
    group_id: str = "OPENID-GROUP",
    channel: str = "official",
    at_qqs: tuple[str, ...] = (),
    mentioned_self: bool | None = None,
    self_id: int = 0,
) -> SimpleNamespace:
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs:
        segments.append({"type": "at", "data": {"qq": qq}})
    if channel == "official" and mentioned_self is None:
        mentioned_self = True  # 官方群命令需要被 @；测试直接给权威标记
    return SimpleNamespace(
        user_id=user_id,
        group_id=group_id,
        message=segments,
        neobot_channel=channel,
        raw_message=text,
        message_type="group",
        mentioned_self=mentioned_self,
        self_id=self_id,
    )


async def _run(text: str, **kwargs) -> str:
    service, sent = _service()
    kind = kwargs.pop("kind", "group")
    queue_key = str(
        kwargs.get("group_id")
        or (kwargs.get("user_id") if kind != "group" else "OPENID-GROUP")
        or "q"
    )
    result = await service.handle_message(_message(text, **kwargs), kind=kind, queue_key=queue_key)
    assert result.consumed is True
    assert sent, "命令没有产生回复"
    args = sent[0][0]
    return str(args[2]) if len(args) > 2 else " ".join(str(part) for part in args)


async def test_get_openid_self_full_value() -> None:
    reply = await _run("/get openid")
    assert "openid：OPENID-SELF" in reply


async def test_get_openid_at_user_full_value() -> None:
    reply = await _run("/get openid", at_qqs=("OPENID-TARGET",))
    assert "OPENID-TARGET" in reply
    assert "OPENID-SELF" not in reply


async def test_get_openid_onebot_does_not_echo_qq_number() -> None:
    reply = await _run(
        "/get openid", user_id="10001", channel="onebot", self_id=10001, at_qqs=("10001",)
    )
    assert "没有 openid" in reply
    assert "10001" not in reply


async def test_get_groupid_official_full_value() -> None:
    reply = await _run("/get groupid")
    assert "group openid：OPENID-GROUP" in reply


async def test_get_groupid_onebot_does_not_echo_group_number() -> None:
    reply = await _run(
        "/get groupid", group_id="123456", channel="onebot", self_id=10001, at_qqs=("10001",)
    )
    assert "没有 group openid" in reply
    assert "123456" not in reply


async def test_get_groupid_private_is_rejected() -> None:
    reply = await _run("/get groupid", kind="private", mentioned_self=False)
    assert "只能在群聊" in reply


async def test_get_rejects_multiple_at_targets() -> None:
    reply = await _run("/get openid", at_qqs=("OPENID-A", "OPENID-B"))
    assert "一次只能 @ 一个用户" in reply


async def test_get_openid_ignores_bot_at_segment() -> None:
    """官方 @ 事件会带 bot 自己的 at 段，@用户查询只能取被 @ 的人。"""
    reply = await _run(
        "/get openid", at_qqs=("88888", "OPENID-TARGET"), self_id=88888
    )
    assert "OPENID-TARGET" in reply
    assert "88888" not in reply


async def test_get_openid_rejects_extra_text_arguments() -> None:
    reply = await _run("/get openid someone")
    assert "用法" in reply


async def test_get_without_subcommand_shows_usage() -> None:
    reply = await _run("/get")
    assert "用法" in reply

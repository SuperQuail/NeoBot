"""官方通道工具可见性：隐藏 OneBot/协议无等价能力的工具。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.reply.tools import ReplyToolExecutor


def _definition(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "",
            "parameters": {"type": "object", "properties": {}},
        },
    }


_NAMES = [
    "send_reply",
    "send_long_reply",
    "speak",
    "sticker__send_sticker",
    "react_emoji",
    "search_qq_emoji",
    "poke_user",
    "onebot__call",
    "onebot__doc",
    "group_management__manage_group",
    "friend_management__manage_friend",
    "forward_message__read_forward_msg",
]


def _visible(official: bool) -> set[str]:
    executor = ReplyToolExecutor(official_platform=official)
    return {
        item["function"]["name"]
        for item in executor._filter_tool_defs([_definition(name) for name in _NAMES])
    }


def test_official_hides_unsupported_tools() -> None:
    visible = _visible(True)

    assert {"send_reply", "send_long_reply", "speak", "sticker__send_sticker"} <= visible
    assert "react_emoji" not in visible
    assert "search_qq_emoji" not in visible
    assert "poke_user" not in visible
    assert not any(name.startswith("onebot__") for name in visible)
    assert not any(name.startswith("group_management__") for name in visible)
    assert not any(name.startswith("friend_management__") for name in visible)
    assert not any(name.startswith("forward_message__") for name in visible)


def test_onebot_keeps_all_tools() -> None:
    assert _visible(False) == set(_NAMES)


def test_official_hidden_tool_reports_supported_error() -> None:
    executor = ReplyToolExecutor(official_platform=True)

    assert "官方" in executor.authorization_error("poke_user")
    assert "官方" in executor.authorization_error("group_management__manage_group")


def _markdown_executor(handler):
    from types import SimpleNamespace

    return ReplyToolExecutor(
        official_platform=True,
        send_official_markdown_handler=handler,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )


async def test_official_markdown_tool_only_exposed_on_official() -> None:
    async def handler(**kwargs):
        return SimpleNamespace(status="ok")

    official = _markdown_executor(handler)
    names = {item["function"]["name"] for item in official.definitions()}
    assert "send_official_markdown" in names

    onebot = ReplyToolExecutor(official_platform=False)
    names = {item["function"]["name"] for item in onebot.definitions()}
    assert "send_official_markdown" not in names


async def test_official_markdown_tool_sends_and_rejects_bad_tags() -> None:
    calls: list[dict] = []

    async def handler(**kwargs):
        calls.append(kwargs)
        from types import SimpleNamespace
        return SimpleNamespace(status="ok", message="")

    executor = _markdown_executor(handler)
    ok = await executor.execute(
        "send_official_markdown",
        {"content": "# 标题\n<qqbot-at-user id=\"9000000000003\" /> 你好", "reply_to_number": 2},
    )
    assert '"ok": true' in ok
    assert calls[0]["content"].startswith("# 标题")
    assert calls[0]["reply_to_number"] == 2

    bad = await executor.execute(
        "send_official_markdown", {"content": "<script>alert(1)</script>"}
    )
    assert "错误" in bad
    assert len(calls) == 1

"""send_official_markdown 工具：参数校验、注入防护、@全体节流与指令按钮。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from neobot_app.reply.tool_parts.official_tools import _AT_EVERYONE_SENT
from neobot_app.reply.tools import ReplyToolExecutor


@pytest.fixture(autouse=True)
def _reset_at_everyone_throttle():
    _AT_EVERYONE_SENT.clear()
    yield
    _AT_EVERYONE_SENT.clear()


class _Handler:
    def __init__(self, result: object | None = None) -> None:
        self.calls: list[dict] = []
        self._result = result if result is not None else SimpleNamespace(status="ok", message="")

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class _Numbering:
    def __init__(self, mapping: dict[int, int] | None = None) -> None:
        self.mapping = dict(mapping or {})
        self._ids = {number: 1000 + number for number in self.mapping}

    def get_message_id(self, number: int) -> int | None:
        return self._ids.get(number)


def _executor(
    handler: _Handler,
    *,
    kind: str = "group",
    conversation_id: str = "group-openid",
    numbering: _Numbering | None = None,
) -> ReplyToolExecutor:
    return ReplyToolExecutor(
        official_platform=True,
        send_official_markdown_handler=handler,
        conv_kind=kind,
        conv_id=conversation_id,
        numbering=numbering,
        logger=SimpleNamespace(info=lambda *a, **k: None),
    )


def _payload(result: str) -> dict:
    return json.loads(result)


# ── 参数校验（失败即 JSON error、不发送） ───────────────────────────


async def test_empty_content_is_rejected() -> None:
    handler = _Handler()

    result = _payload(await _executor(handler).execute("send_official_markdown", {"content": "   "}))

    assert result["ok"] is False
    assert "错误" in result["error"]
    assert handler.calls == []


async def test_content_over_limit_is_rejected() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute("send_official_markdown", {"content": "a" * 4001})
    )

    assert result["ok"] is False
    assert "4000" in result["error"]
    assert handler.calls == []


async def test_tool_is_official_only() -> None:
    handler = _Handler()
    executor = ReplyToolExecutor(
        official_platform=False,
        send_official_markdown_handler=handler,
    )

    result = _payload(await executor.execute("send_official_markdown", {"content": "你好"}))

    assert result["ok"] is False
    assert "官方" in result["error"]
    assert handler.calls == []


async def test_commands_must_be_object_array() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "你好", "commands": "x"}
        )
    )

    assert result["ok"] is False
    assert "对象数组" in result["error"]
    assert handler.calls == []


@pytest.mark.parametrize(
    "command, expected",
    [
        ({"text": ""}, "1~100"),
        ({"text": "a" * 101}, "1~100"),
        ({"text": "/x", "show": "b" * 101}, "1~100"),
    ],
)
async def test_command_text_limits(command: dict, expected: str) -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "你好", "commands": [command]}
        )
    )

    assert result["ok"] is False
    assert expected in result["error"]
    assert handler.calls == []


async def test_group_enter_command_is_rejected() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown",
            {"content": "你好", "commands": [{"text": "/x", "enter": True}]},
        )
    )

    assert result["ok"] is False
    assert "回车" in result["error"]
    assert handler.calls == []


async def test_private_at_user_is_rejected() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler, kind="private", conversation_id="user-openid").execute(
            "send_official_markdown",
            {"content": '<qqbot-at-user id="member-openid" /> 你好'},
        )
    )

    assert result["ok"] is False
    assert "单聊" in result["error"]
    assert handler.calls == []


async def test_private_at_everyone_is_rejected() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler, kind="private", conversation_id="user-openid").execute(
            "send_official_markdown", {"content": "你好", "at_everyone": True}
        )
    )

    assert result["ok"] is False
    assert "单聊" in result["error"]
    assert handler.calls == []


async def test_at_everyone_must_be_boolean() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "你好", "at_everyone": "yes"}
        )
    )

    assert result["ok"] is False
    assert "布尔" in result["error"]
    assert handler.calls == []


async def test_reply_to_number_must_exist() -> None:
    handler = _Handler()
    numbering = _Numbering({1: 101})

    result = _payload(
        await _executor(handler, numbering=numbering).execute(
            "send_official_markdown", {"content": "你好", "reply_to_number": 2}
        )
    )

    assert result["ok"] is False
    assert "不存在" in result["error"]
    assert handler.calls == []


# ── 合法输入与结构化参数 ───────────────────────────────────────────


async def test_valid_content_is_forwarded() -> None:
    handler = _Handler()
    numbering = _Numbering({1: 101})
    content = '## 标题\n\n<qqbot-at-user id="member-openid" /> 你好\n\n- 列表'

    result = _payload(
        await _executor(handler, numbering=numbering).execute(
            "send_official_markdown", {"content": content, "reply_to_number": 1}
        )
    )

    assert result["ok"] is True
    assert result["sent_count"] == 1
    call = handler.calls[0]
    assert call["content"] == content
    assert call["reply_to_number"] == 1
    assert call["at_everyone"] is False
    assert call["commands"] == []


async def test_at_everyone_is_structured_and_forwarded() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "今晚活动", "at_everyone": True}
        )
    )

    assert result["ok"] is True
    call = handler.calls[0]
    assert call["at_everyone"] is True
    assert call["content"] == "今晚活动"
    assert call["display_text"].startswith("@全体成员 今晚活动")


async def test_at_everyone_is_throttled_per_group_and_day() -> None:
    first = _Handler()
    second = _Handler()

    ok = _payload(
        await _executor(first, conversation_id="group-a").execute(
            "send_official_markdown", {"content": "今晚活动", "at_everyone": True}
        )
    )
    again = _payload(
        await _executor(second, conversation_id="group-a").execute(
            "send_official_markdown", {"content": "再说一次", "at_everyone": True}
        )
    )

    assert ok["ok"] is True
    assert again["ok"] is False
    assert "已用掉" in again["error"]
    assert second.calls == []


async def test_at_everyone_is_allowed_for_another_group() -> None:
    handler = _Handler()

    await _executor(handler, conversation_id="group-a").execute(
        "send_official_markdown", {"content": "第一个群", "at_everyone": True}
    )
    result = _payload(
        await _executor(handler, conversation_id="group-b").execute(
            "send_official_markdown", {"content": "第二个群", "at_everyone": True}
        )
    )

    assert result["ok"] is True
    assert [call["at_everyone"] for call in handler.calls] == [True, True]


async def test_commands_are_forwarded_for_adapter_encoding() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown",
            {"content": "点按钮", "commands": [{"text": "/签到", "show": "去签到"}]},
        )
    )

    assert result["ok"] is True
    commands = handler.calls[0]["commands"]
    assert commands == [
        {"text": "/签到", "show": "去签到", "enter": False, "reference": False}
    ]
    assert "[按钮：去签到]" in handler.calls[0]["display_text"]


async def test_private_enter_command_is_allowed() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler, kind="private", conversation_id="user-openid").execute(
            "send_official_markdown",
            {"content": "点按钮", "commands": [{"text": "/今日运势", "enter": True}]},
        )
    )

    assert result["ok"] is True
    assert handler.calls[0]["commands"][0]["enter"] is True


# ── 注入防护：标签转义、链接校验 ──────────────────────────────────


async def test_forbidden_official_tags_are_neutralized() -> None:
    handler = _Handler()
    content = (
        '<qqbot-at-everyone /> <qqbot-cmd-input text="x" /> '
        "<@123456> 你好"
    )

    result = _payload(
        await _executor(handler).execute("send_official_markdown", {"content": content})
    )

    assert result["ok"] is True
    assert result["neutralized"] == 3
    sent = handler.calls[0]["content"]
    assert "<qqbot-at-everyone" not in sent
    assert "<qqbot-cmd-" not in sent
    assert "<@123456>" not in sent
    assert "＜qqbot-at-everyone /＞" in sent
    assert handler.calls[0]["at_everyone"] is False


async def test_html_tags_are_rejected() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "<script>alert(1)</script>"}
        )
    )

    assert result["ok"] is False
    assert "不支持的标签" in result["error"]
    assert handler.calls == []


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/plain,abc",
        "file:///etc/passwd",
        "http://127.0.0.1/a",
        "http://10.0.0.8/a",
        "http://192.168.1.2/a",
        "http://169.254.1.1/a",
        "http://localhost/a",
        "http://router.local/a",
    ],
)
async def test_unsafe_links_are_rejected(url: str) -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": f"[点我]({url})"}
        )
    )

    assert result["ok"] is False
    assert "链接" in result["error"]
    assert handler.calls == []


async def test_https_link_is_allowed() -> None:
    handler = _Handler()

    result = _payload(
        await _executor(handler).execute(
            "send_official_markdown", {"content": "[点我](https://example.com/a?b=1)"}
        )
    )

    assert result["ok"] is True
    assert handler.calls[0]["content"] == "[点我](https://example.com/a?b=1)"


# ── 单轮限流与历史可读文本 ─────────────────────────────────────────


async def test_one_markdown_message_per_pipeline() -> None:
    handler = _Handler()
    executor = _executor(handler)

    first = _payload(
        await executor.execute("send_official_markdown", {"content": "第一条"})
    )
    second = _payload(
        await executor.execute("send_official_markdown", {"content": "第二条"})
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert "最多 1 条" in second["error"]
    assert len(handler.calls) == 1


async def test_failure_does_not_consume_pipeline_quota() -> None:
    failed = _Handler(SimpleNamespace(status="failed", message="官方拒绝"))
    executor = _executor(failed)

    first = _payload(await executor.execute("send_official_markdown", {"content": "第一条"}))
    second = _payload(
        await executor.execute("send_official_markdown", {"content": "第二条"})
    )

    assert first["ok"] is False
    assert "发送失败" in first["error"]
    assert second["ok"] is False
    assert "发送失败" in second["error"]
    assert len(failed.calls) == 2


async def test_history_arguments_keep_structured_params() -> None:
    handler = _Handler()

    await _executor(handler).execute(
        "send_official_markdown",
        {
            "content": "今晚活动",
            "at_everyone": True,
            "commands": [{"text": "/签到", "show": "去签到"}],
        },
    )

    args = handler.calls[0]["tool_arguments"]
    assert args["content"] == "今晚活动"
    assert args["at_everyone"] is True
    assert args["commands"][0]["text"] == "/签到"

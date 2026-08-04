"""StickerSkill 表情包发送测试 — 正常转发/缺失参数/异常兜底。"""

from __future__ import annotations

import json

from neobot_app.skills.sticker_skill import StickerSkill


class _FakeEmojiService:
    """记录调用参数的假表情包服务，可配置抛错。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[object, str, str, str]] = []
        self._error = error

    async def send_sticker(
        self,
        number: object,
        *,
        text: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> str:
        self.calls.append((number, text, group_id, user_id))
        if self._error is not None:
            raise self._error
        return f"sent:{number}"


def _make_skill(service: _FakeEmojiService | None = None) -> StickerSkill:
    return StickerSkill(emoji_service=service)


async def test_send_sticker_forwards_number_to_service():
    """正常路径：send_sticker 应透传 number 并返回 ok=True。"""
    service = _FakeEmojiService()
    skill = _make_skill(service)

    result = json.loads(await skill.execute("send_sticker", {"number": 7}))

    assert result["ok"] is True
    assert "sent:7" in result["result"]
    assert service.calls == [(7, "", "", "")]


async def test_send_sticker_passes_text_and_targets_through():
    """正常路径：text/group_id/user_id 应原样透传给 emoji_service。"""
    service = _FakeEmojiService()
    skill = _make_skill(service)

    result = json.loads(
        await skill.execute("send_sticker", {
            "number": 3,
            "text": "早安",
            "group_id": "888888",
            "user_id": "123456",
        })
    )

    assert result["ok"] is True
    assert service.calls == [(3, "早安", "888888", "123456")]


async def test_send_sticker_missing_number_rejected():
    """异常路径：缺少 number 时应返回 ok=False 且不调用服务。"""
    service = _FakeEmojiService()
    skill = _make_skill(service)

    result = json.loads(await skill.execute("send_sticker", {"text": "hi"}))

    assert result["ok"] is False
    assert "缺少表情包编号" in result["error"]
    assert service.calls == []


async def test_send_sticker_zero_number_is_valid_boundary():
    """边界：number=0 是合法取值，应透传而不被当作缺省拒绝。"""
    service = _FakeEmojiService()
    skill = _make_skill(service)

    result = json.loads(await skill.execute("send_sticker", {"number": 0}))

    assert result["ok"] is True
    assert service.calls == [(0, "", "", "")]


async def test_send_sticker_service_exception_wrapped_in_json():
    """异常路径：emoji_service 抛异常时应包装为 ok=False 的 JSON 而不是上抛。"""
    service = _FakeEmojiService(error=RuntimeError("emoji boom"))
    skill = _make_skill(service)

    result = json.loads(await skill.execute("send_sticker", {"number": 1}))

    assert result["ok"] is False
    assert "emoji boom" in result["error"]


async def test_send_sticker_unconfigured_service_rejected():
    """异常路径：未注入 emoji_service 时应返回配置缺失错误。"""
    skill = _make_skill(None)

    result = json.loads(await skill.execute("send_sticker", {"number": 1}))

    assert result["ok"] is False
    assert "emoji_service 未配置" in result["error"]


async def test_unknown_tool_rejected():
    """异常路径：未知工具名应返回 unknown sticker tool 错误。"""
    skill = _make_skill(_FakeEmojiService())

    result = json.loads(await skill.execute("no_such_tool", {}))

    assert result["ok"] is False
    assert "unknown sticker tool" in result["error"]


def test_get_tools_empty_without_emoji_service():
    """边界：未配置 emoji_service 时不应暴露 send_sticker 工具定义。"""
    skill = _make_skill(None)

    assert skill.get_tools() == []
    assert skill.name == "sticker"


def test_get_tools_exposes_send_sticker_when_configured():
    """正常路径：配置 emoji_service 后工具列表应包含 send_sticker 且要求 number。"""
    skill = _make_skill(_FakeEmojiService())

    tools = skill.get_tools()

    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "send_sticker"
    assert "number" in tools[0]["function"]["parameters"]["required"]

"""ReplyToolExecutor 测试：工具参数校验、wait 冷却、长回复发送、会话工具排队。"""

from __future__ import annotations

import asyncio
import json

import pytest

from neobot_app.reply.tools import ReplyToolExecutor


class _FakeSkillManager:
    """可挂起的假 skill 管理器，用于会话工具排队逻辑。"""

    def __init__(self) -> None:
        self.executions: list[tuple[str, dict]] = []

    def get_tools(self) -> list:
        return []

    def is_session_tool(self, name: str) -> bool:
        return True

    async def execute(self, name: str, args: dict) -> str:
        self.executions.append((name, args))
        await asyncio.sleep(0.5)
        return json.dumps({"ok": True})


def _make_executor(**overrides) -> ReplyToolExecutor:
    return ReplyToolExecutor(**overrides)


# ── send_reply 参数校验 ──────────────────────────────────────────


async def test_send_reply_rejects_non_list_images():
    """images 不是列表时必须返回错误信息且不调用 handler。"""
    called: list = []

    async def handler(**kwargs):
        called.append(kwargs)

    executor = _make_executor(send_reply_handler=handler)
    result = await executor.execute("send_reply", {"text": "你好", "images": 42})
    assert "images 必须为列表" in result
    assert called == []


async def test_send_reply_rejects_bad_reply_to_and_mention():
    """reply_to 非整数、mention 非整数列表时必须返回对应错误信息。"""
    async def handler(**kwargs):
        pass

    executor = _make_executor(send_reply_handler=handler)

    bad_reply_to = await executor.execute("send_reply", {"text": "你好", "reply_to": "abc"})
    bad_mention = await executor.execute("send_reply", {"text": "你好", "mention": ["x"]})

    assert "reply_to 必须为整数" in bad_reply_to
    assert "mention 必须为整数列表" in bad_mention


async def test_send_reply_calls_handler_with_normalized_args():
    """合法参数必须归一化后传给 handler（mention 转 int 列表），并返回发送条数摘要。"""
    captured: dict = {}

    async def handler(**kwargs):
        captured.update(kwargs)

    executor = _make_executor(send_reply_handler=handler)
    result = await executor.execute(
        "send_reply",
        {"text": "你好，今天天气不错", "reply_to": "7", "mention": ["10001", 10002]},
    )

    assert captured["text"] == "你好，今天天气不错"
    assert captured["reply_to"] == 7
    assert captured["mention"] == [10001, 10002]
    assert "已发送" in result


async def test_send_reply_missing_handler_returns_error():
    """未配置 send_reply 处理器时必须返回错误信息而非抛异常。"""
    executor = _make_executor()
    result = await executor.execute("send_reply", {"text": "你好"})
    assert "处理器未配置" in result


# ── wait 冷却与参数校验 ──────────────────────────────────────────


async def test_wait_respects_cooldown():
    """冷却期内再次调用 wait 必须返回冷却提示且不再调用 handler。"""
    calls: list[int] = []

    async def handler(seconds: int = 20) -> str:
        calls.append(seconds)
        return "ok"

    executor = _make_executor(wait_handler=handler, wait_cooldown_seconds=60)
    await executor.execute("wait", {"seconds": 3})
    executor._last_wait_time = __import__("time").monotonic()
    second = await executor.execute("wait", {})

    assert calls == [3]
    assert "冷却" in second


async def test_wait_validates_seconds_and_defaults_to_20():
    """seconds 非整数返回错误；缺省时 handler 收到默认 20 秒。"""
    calls: list[int] = []

    async def handler(seconds: int = 20) -> str:
        calls.append(seconds)
        return "ok"

    executor = _make_executor(wait_handler=handler)
    bad = await executor.execute("wait", {"seconds": "abc"})
    ok = await executor.execute("wait", {})

    assert "seconds 必须为整数" in bad
    assert calls == [20]
    assert ok == "ok"


# ── send_long_reply ──────────────────────────────────────────────


async def test_send_long_reply_requires_markdown_or_image_path():
    """markdown 与 image_path 都为空时必须返回错误，且不调用发送 handler。"""
    sent: list = []

    async def handler(**kwargs):
        sent.append(kwargs)

    executor = _make_executor(
        markdown_image_converter=object(),
        send_long_reply_handler=handler,
    )
    result = json.loads(await executor.execute("send_long_reply", {}))

    assert result["ok"] is False
    assert "至少需要提供一个" in result["error"]
    assert sent == []


async def test_send_long_reply_converter_failure_returns_error():
    """converter.convert 抛异常时返回降级错误信息且不发送。"""

    class _BoomConverter:
        async def convert(self, markdown_text: str) -> str:
            raise RuntimeError("render boom")

    executor = _make_executor(markdown_image_converter=_BoomConverter())
    result = json.loads(await executor.execute("send_long_reply", {"markdown": "# 标题"}))

    assert result["ok"] is False
    assert "render boom" in result["error"]


async def test_send_long_reply_pre_rendered_image_skips_converter():
    """提供 image_path 时直接发送预渲染图片，converter 不得被调用。"""

    class _CounterConverter:
        def __init__(self) -> None:
            self.calls = 0

        async def convert(self, markdown_text: str) -> str:
            self.calls += 1
            return "rendered.png"

    converter = _CounterConverter()
    sent: list[dict] = []

    async def handler(**kwargs):
        sent.append(kwargs)

    executor = _make_executor(
        markdown_image_converter=converter,
        send_long_reply_handler=handler,
    )
    result = json.loads(
        await executor.execute(
            "send_long_reply",
            {"image_path": "pre/rendered.png", "markdown": "# 备注", "caption": "说明"},
        )
    )

    assert result["ok"] is True
    assert result["image_path"] == "pre/rendered.png"
    assert converter.calls == 0
    assert sent[0]["image_path"] == "pre/rendered.png"
    assert sent[0]["caption"] == "说明"


# ── 静态辅助 ─────────────────────────────────────────────────────


def test_normalize_segments_cleans_and_returns_none_for_empty():
    """_normalize_segments：非列表返回 None，空/空白条目被清洗后为空时返回 None。"""
    assert ReplyToolExecutor._normalize_segments(None) is None
    assert ReplyToolExecutor._normalize_segments("not-a-list") is None
    assert ReplyToolExecutor._normalize_segments(["  ", ""]) is None
    assert ReplyToolExecutor._normalize_segments([" 第一句 ", "第二句"]) == ["第一句", "第二句"]


@pytest.mark.xfail(
    reason=(
        "BUG-0002 _normalize_segments 把 None 条目转成字符串 'None'（str(None).strip()），"
        "LLM 传入 null 段会被当作 'None' 文本发送"
    ),
    strict=False,
)
def test_normalize_segments_drops_none_items():
    """_normalize_segments 遇到 None 条目必须丢弃，不得转为字符串 'None'。"""
    assert ReplyToolExecutor._normalize_segments(["有效", None]) == ["有效"]


def test_definitions_include_tools_conditionally():
    """definitions() 按配置注入工具：未配置 wait/converter 时不得出现对应工具定义。"""
    bare = _make_executor()
    names = [d["function"]["name"] for d in bare.definitions()]
    assert "wait" not in names
    assert "send_long_reply" not in names

    full = _make_executor(wait_handler=lambda s: "", markdown_image_converter=object())
    full_names = [d["function"]["name"] for d in full.definitions()]
    assert "wait" in full_names
    assert "send_long_reply" in full_names


# ── 会话工具排队（后台执行）──────────────────────────────────────


async def test_session_tool_queues_and_rejects_third_submission():
    """同一管线会话工具：第 1 次后台执行、第 2 次排队、第 3 次队列满被拒绝。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    try:
        first = json.loads(await executor.execute("download__url", {"url": "http://a"}))
        second = json.loads(await executor.execute("download__url", {"url": "http://b"}))
        third = json.loads(await executor.execute("download__url", {"url": "http://c"}))

        assert first["status"] == "session_submitted"
        assert second["status"] == "queued"
        assert third["status"] == "queue_full"
        assert third["ok"] is False
    finally:
        await executor.close()


async def test_cancel_task_cancels_queued_session_tool():
    """cancel_task(session_tool) 必须同时清掉排队任务并取消运行中的任务。"""
    skill = _FakeSkillManager()
    executor = _make_executor(
        skill_manager=skill,
        conv_kind="group",
        conv_id="123456",
    )
    try:
        await executor.execute("download__url", {"url": "http://a"})
        await executor.execute("download__url", {"url": "http://b"})

        result = json.loads(await executor.execute("cancel_task", {"task_type": "session_tool"}))

        assert result["ok"] is True
        assert len(result["cancelled"]) == 2
        assert not executor._session_task_queue
        await asyncio.sleep(0.1)  # 等待取消回调从运行信息中清理任务
        assert not executor._session_task_info
    finally:
        await executor.close()

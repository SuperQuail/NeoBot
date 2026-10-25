"""BilibiliReplyEngine 测试：一次 LLM 生成、输出清理、限长、记忆档案注入。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from neobot_chat.schema.exceptions import ProviderError

import neobot_app.bilibili.reply_engine as reply_engine_module
from neobot_app.bilibili.prompts import CommentContext, CommentNode, PrivateMessageContext
from neobot_app.bilibili.reply_engine import BilibiliReplyEngine, clean_reply


class FakeProvider:
    def __init__(
        self,
        content: str = "好哦",
        *,
        error: Exception | None = None,
        usage: dict | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.usage = usage
        self.calls: list[list[dict]] = []
        self.model = "fake-model"
        self.registered_key = "fake-model-key"

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        name = "cancel" if self.content.strip().upper() == "[SKIP]" else "send_reply"
        arguments = {} if name == "cancel" else {"text": self.content}
        response = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                }
            ],
        }
        if self.usage is not None:
            response["extensions"] = {"usage": self.usage}
        return response


class _UsageRecorder:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class FakeArchive:
    def __init__(self, entries: dict[tuple[str, str], str] | None = None) -> None:
        self.entries = dict(entries or {})
        self.calls: list[tuple[str, str]] = []

    async def get(self, table_name, key):
        self.calls.append((table_name, key))
        value = self.entries.get((table_name, key))
        return SimpleNamespace(table_name=table_name, key=key, value=value) if value is not None else None


class FakeLinks:
    def __init__(self, qq_by_uid: dict[int, str] | None = None) -> None:
        self.qq_by_uid = dict(qq_by_uid or {})

    async def find_by_uid(self, uid):
        qq = self.qq_by_uid.get(int(uid))
        return [{"bilibili_uid": int(uid), "qq_number": qq}] if qq else []


class FakeProfiles:
    def __init__(self, users: dict[str, SimpleNamespace] | None = None) -> None:
        self.users = dict(users or {})

    async def get_user(self, user_id):
        return self.users.get(str(user_id))


class FakeUow:
    def __init__(self, links=None, profiles=None) -> None:
        self.bilibili_links = links or FakeLinks()
        self.profiles = profiles or FakeProfiles()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _factory(links=None, profiles=None):
    def make():
        return FakeUow(links=links, profiles=profiles)

    return make


def _engine(provider=None, **kwargs) -> BilibiliReplyEngine:
    return BilibiliReplyEngine(provider, bot_name="Neo", bot_uid=1234, **kwargs)


def _comment_ctx(**kwargs) -> CommentContext:
    ctx = CommentContext(
        target_oid=99,
        target_title="视频",
        comment_tree=[
            CommentNode(rpid=7, uid=77, uname="甲", content="你好", ctime=1_700_000_000)
        ],
        reply_target_rpid=7,
        reply_root_rpid=7,
    )
    for key, value in kwargs.items():
        setattr(ctx, key, value)
    return ctx


# ── clean_reply ──


def test_clean_reply_strips_think_and_prefix() -> None:
    assert clean_reply("<think>想一下</think>回复:你好呀") == "你好呀"


def test_clean_reply_skip_and_empty() -> None:
    assert clean_reply("[SKIP]") == ""
    assert clean_reply("  ") == ""
    assert clean_reply(None) == ""


def test_clean_reply_strips_quotes_and_markdown() -> None:
    assert clean_reply('"**其实**可以"') == "其实可以"


def test_clean_reply_truncates_at_sentence_end() -> None:
    text = "第一句话。" + "很长的后半句" * 10
    result = clean_reply(text, max_chars=10)

    assert len(result) <= 10
    assert result == "第一句话"


# ── 生成 ──


async def test_comment_reply_generation_uses_provider() -> None:
    provider = FakeProvider("好哦")
    engine = _engine(provider)

    result = await engine.generate_comment_reply(_comment_ctx())

    assert result == "好哦"
    assert len(provider.calls) >= 1
    messages = provider.calls[0]
    system = next(item for item in messages if item.get("role") == "system")
    user = next(item for item in messages if item.get("role") == "user")
    assert system["role"] == "system" and "B站" in system["content"]
    assert "你好" in user["content"]


async def test_skip_returns_none() -> None:
    engine = _engine(FakeProvider("[SKIP]"))

    assert await engine.generate_comment_reply(_comment_ctx()) is None


async def test_provider_error_is_raised_for_retry() -> None:
    # 契约：provider 异常必须向上抛，调用方回池重试；不能伪装成「模型不回复」。
    engine = _engine(FakeProvider(error=RuntimeError("boom")))

    with pytest.raises(ProviderError) as caught:
        await engine.generate_comment_reply(_comment_ctx())

    assert isinstance(caught.value.original, RuntimeError)


async def test_provider_timeout_is_raised_for_retry() -> None:
    engine = _engine(FakeProvider(error=TimeoutError("provider timeout")))

    with pytest.raises(ProviderError) as caught:
        await engine.generate_private_reply(
            PrivateMessageContext(sender_uid=55, sender_name="王五", current_message="在吗")
        )

    assert isinstance(caught.value.original, TimeoutError)


async def test_provider_usage_is_recorded(monkeypatch) -> None:
    recorder = _UsageRecorder()
    monkeypatch.setattr(reply_engine_module, "get_usage_tracker", lambda: recorder)
    provider = FakeProvider(
        "好哦",
        usage={
            "input_tokens": 12,
            "output_tokens": 3,
            "cache_hit_tokens": 4,
            "cache_miss_tokens": 5,
        },
    )

    await _engine(provider).generate_comment_reply(_comment_ctx())

    assert recorder.records == [
        {
            "module": "bilibili",
            "model_name": "fake-model",
            "registered_key": "fake-model-key",
            "input_tokens": 12,
            "output_tokens": 3,
            "cache_hit_tokens": 4,
            "cache_miss_tokens": 5,
        }
    ]


async def test_missing_provider_usage_still_records_module(monkeypatch) -> None:
    recorder = _UsageRecorder()
    monkeypatch.setattr(reply_engine_module, "get_usage_tracker", lambda: recorder)

    await _engine(FakeProvider("好哦")).generate_comment_reply(_comment_ctx())

    assert len(recorder.records) == 1
    assert recorder.records[0]["module"] == "bilibili"
    assert recorder.records[0]["input_tokens"] == 0
    assert recorder.records[0]["output_tokens"] == 0


async def test_no_provider_returns_none() -> None:
    engine = _engine(None)

    assert engine.available is False
    assert await engine.generate_comment_reply(_comment_ctx()) is None


async def test_comment_length_is_limited() -> None:
    engine = _engine(FakeProvider("啊" * 500), max_comment_chars=20)

    result = await engine.generate_comment_reply(_comment_ctx())

    assert result is not None
    assert len(result) <= 20


# ── 记忆档案 ──


async def test_comment_profiles_from_archive_and_link() -> None:
    archive = FakeArchive(
        {
            ("bilibili_user", "77"): "B站上聊过游戏",
            ("user_summary", "10001"): "QQ档案摘要",
        }
    )
    links = FakeLinks({77: "10001"})
    profiles = FakeProfiles(
        {"10001": SimpleNamespace(remark="老友", profile="常聊天", known_gender="")}
    )
    engine = _engine(
        FakeProvider("好"),
        archive_service=archive,
        uow_factory=_factory(links, profiles),
    )
    ctx = _comment_ctx()

    await engine.generate_comment_reply(ctx)

    assert ctx.commenter_profiles
    profile = ctx.commenter_profiles[0]
    assert profile["remark"] == "老友"
    assert profile["bilibili_memory"] == "B站上聊过游戏"
    assert profile["qq_memory"] == "QQ档案摘要"
    assert ("user_profile", "10001") not in archive.calls  # summary 命中后不再读全量


async def test_private_reply_merges_memory() -> None:
    archive = FakeArchive({("bilibili_user", "55"): "记得他爱问天气"})
    engine = _engine(FakeProvider("在的"), archive_service=archive)
    ctx = PrivateMessageContext(
        sender_uid=55,
        sender_name="王五",
        history=[{"role": "user", "content": "在吗", "time": 1_700_000_000}],
        current_message="在吗",
    )

    result = await engine.generate_private_reply(ctx)

    assert result == "在的"
    assert "记得他爱问天气" in ctx.memory_list


async def test_task_reply_generation() -> None:
    provider = FakeProvider("收到")
    engine = _engine(provider)

    result = await engine.generate_task_reply("告诉对方晚上开黑", history="对方:在吗")

    assert result == "收到"
    messages = provider.calls[0]
    system = next(item for item in messages if item.get("role") == "system")
    user = next(item for item in messages if item.get("role") == "user")
    assert "跨聊天任务" in system["content"]
    assert "告诉对方晚上开黑" in user["content"]


# ── 视频上下文增强 ──

_VIDEO_URL = "https://www.bilibili.com/video/BV1xx411c7mD"


class FakeVideoService:
    def __init__(self, result=None, *, delay: float = 0.0) -> None:
        self.result = result or {
            "ok": True,
            "title": "视频标题",
            "source": "site",
            "transcript": "字幕摘要",
            "url": _VIDEO_URL,
        }
        self.delay = delay
        self.calls: list[tuple] = []

    async def watch(self, identifier, max_chars=6000, include_comments=0):
        self.calls.append((identifier, max_chars, include_comments))
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.result


async def test_comment_video_link_enriches_prompt() -> None:
    video = FakeVideoService()
    provider = FakeProvider("好")
    engine = _engine(provider, video_service=video)
    ctx = _comment_ctx()
    ctx.comment_tree = [
        CommentNode(rpid=7, uid=77, uname="甲", content=f"看这个 {_VIDEO_URL}")
    ]

    result = await engine.generate_comment_reply(ctx)

    assert result == "好"
    assert video.calls == [("BV1xx411c7mD", 3000, 0)]
    assert "标题：视频标题" in ctx.video_context
    assert "来源：site" in ctx.video_context
    messages = provider.calls[0]
    user = next(item for item in messages if item.get("role") == "user")
    assert "<相关视频>" in user["content"]
    assert "视频标题" in user["content"]
    assert "字幕摘要" in user["content"]


async def test_private_video_link_enriches_prompt() -> None:
    video = FakeVideoService(
        {
            "ok": True,
            "title": "私信里的视频",
            "source": "asr",
            "transcript": "语音转写",
            "url": "https://www.bilibili.com/video/av170001",
        }
    )
    provider = FakeProvider("在的")
    engine = _engine(provider, video_service=video)
    ctx = PrivateMessageContext(
        sender_uid=55,
        sender_name="王五",
        current_message="看看 https://www.bilibili.com/video/av170001 这个",
    )

    result = await engine.generate_private_reply(ctx)

    assert result == "在的"
    assert video.calls == [("https://www.bilibili.com/video/av170001", 3000, 0)]
    messages = provider.calls[0]
    user = next(item for item in messages if item.get("role") == "user")
    assert "<相关视频>" in user["content"]
    assert "私信里的视频" in user["content"]
    assert "asr" in user["content"]


async def test_video_enrichment_timeout_degrades(monkeypatch) -> None:
    monkeypatch.setattr(reply_engine_module, "_VIDEO_ENRICH_TIMEOUT_SECONDS", 0.01)
    video = FakeVideoService(delay=0.2)
    provider = FakeProvider("好")
    engine = _engine(provider, video_service=video)
    ctx = _comment_ctx()
    ctx.comment_tree = [
        CommentNode(rpid=7, uid=77, uname="甲", content="看 BV1xx411c7mD")
    ]

    result = await engine.generate_comment_reply(ctx)

    assert result == "好"
    assert video.calls
    assert ctx.video_context == ""
    messages = provider.calls[0]
    user = next(item for item in messages if item.get("role") == "user")
    assert "<相关视频>" not in user["content"]


async def test_video_error_result_is_ignored() -> None:
    video = FakeVideoService({"ok": False, "error": "没有字幕"})
    provider = FakeProvider("好")
    engine = _engine(provider, video_service=video)
    ctx = _comment_ctx()
    ctx.comment_tree = [
        CommentNode(rpid=7, uid=77, uname="甲", content="看 BV1xx411c7mD")
    ]

    result = await engine.generate_comment_reply(ctx)

    assert result == "好"
    assert video.calls
    messages = provider.calls[0]
    user = next(item for item in messages if item.get("role") == "user")
    assert "<相关视频>" not in user["content"]


async def test_no_video_link_does_not_call_watch() -> None:
    video = FakeVideoService()
    provider = FakeProvider("好")

    await _engine(provider, video_service=video).generate_comment_reply(_comment_ctx())

    assert video.calls == []
    assert "<相关视频>" not in provider.calls[0][1]["content"]

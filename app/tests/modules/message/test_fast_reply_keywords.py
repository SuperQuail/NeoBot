"""命中玩法关键词即跳过 @ 提及等待的关键词表用例。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from neobot_app.message import fast_reply_keywords as frk


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    frk.reset_reply_trigger_keywords()
    try:
        yield
    finally:
        frk.reset_reply_trigger_keywords()


def test_register_and_match_longest_keyword() -> None:
    """最长关键词优先：命中「今日运势」时不该只报「运势」。"""
    frk.register_reply_trigger_keywords("minigame", ("签到", "今日运势", "运势"))

    assert frk.match_reply_trigger_keyword("今天要不要签到呀") == "签到"
    assert frk.match_reply_trigger_keyword("@bot 今日运势怎么样") == "今日运势"
    assert frk.match_reply_trigger_keyword("看看运势") == "运势"
    assert frk.match_reply_trigger_keyword("随便聊聊") == ""


def test_register_dedupes_and_ignores_blank() -> None:
    frk.register_reply_trigger_keywords("p", ("Fortune", "fortune", "  ", ""))

    assert frk.reply_trigger_keywords()["p"] == ("Fortune",)
    assert frk.match_reply_trigger_keyword("play FORTUNE now") == "Fortune"


def test_register_requires_owner_and_empty_list_unregisters() -> None:
    with pytest.raises(ValueError):
        frk.register_reply_trigger_keywords("   ", ("x",))

    frk.register_reply_trigger_keywords("p", ("签到",))
    assert frk.register_reply_trigger_keywords("p", ()) == ()
    assert frk.match_reply_trigger_keyword("签到") == ""


def test_unregister_only_removes_that_owner() -> None:
    """按 owner 注销：只清自己的关键词，别人的照旧生效。"""
    frk.register_reply_trigger_keywords("a", ("签到", "抽签"))
    frk.register_reply_trigger_keywords("b", ("接龙",))

    assert frk.unregister_reply_trigger_keywords("a") == ("签到", "抽签")
    assert frk.registered_reply_trigger_owners() == ("b",)
    assert frk.match_reply_trigger_keyword("接龙") == "接龙"
    assert frk.match_reply_trigger_keyword("签到") == ""
    assert frk.unregister_reply_trigger_keywords("a") == ()


def _message(*segments: tuple[str, dict[str, Any]], raw: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        message=[SimpleNamespace(type=kind, data=data) for kind, data in segments],
        raw_message=raw,
    )


def test_message_text_prefers_text_segments() -> None:
    """取文本只取 text 段（@ 段不算正文），与命令系统的取法一致。"""
    frk.register_reply_trigger_keywords("minigame", ("签到",))
    message = _message(
        ("at", {"qq": "88888"}),
        ("text", {"text": " 签到 "}),
        raw="[CQ:at,qq=88888] 签到",
    )

    assert frk.message_text(message) == " 签到 "
    assert frk.matches_reply_trigger(message) == "签到"


def test_message_text_falls_back_to_raw_message() -> None:
    """结构化 message 为空时回落 raw_message（含 CQ 码也能命中关键词）。"""
    frk.register_reply_trigger_keywords("minigame", ("抽签",))
    message = SimpleNamespace(message=None, raw_message="[CQ:at,qq=88888]抽签")

    assert frk.message_text(message) == "[CQ:at,qq=88888]抽签"
    assert frk.matches_reply_trigger(message) == "抽签"


def test_matches_reply_trigger_accepts_plain_text_and_empty() -> None:
    frk.register_reply_trigger_keywords("p", ("签到",))

    assert frk.matches_reply_trigger("签到") == "签到"
    assert frk.matches_reply_trigger("") == ""
    assert frk.matches_reply_trigger(None) == ""
    assert frk.matches_reply_trigger(SimpleNamespace(message=None, raw_message="")) == ""


def test_registry_snapshot_is_a_copy() -> None:
    frk.register_reply_trigger_keywords("p", ("签到",))
    snapshot = frk.reply_trigger_keywords()

    snapshot["p"] = ("偷偷改",)

    assert frk.reply_trigger_keywords()["p"] == ("签到",)

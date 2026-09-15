"""output_guard 单元测试：前缀标注 / 思维链标签的兜底清洗。

用例素材直接取自问题报告里的真实落盘证据（群聊实录），确保这条兜底真的能
拦住「续写聊天记录」与「草稿泄漏」两类脏输出，同时不误伤正常回复。
"""

from __future__ import annotations

import pytest

from neobot_app.reply.output_guard import clean_segments, clean_text, should_drop


BOT_NAME = "AAA大肥鱼"
KNOWN = [BOT_NAME, "贝拉", ".純屬虛構."]


# ── 真实脏输出（报告第一节/第三节的证据） ─────────────────────────


@pytest.mark.parametrize(
    "dirty, expected",
    [
        # 报告现象 1：续写聊天记录，行首带「编号: 名字:」
        ("215: 贝拉: @QQ:3830912140 要抱抱", "@QQ:3830912140 要抱抱"),
        ("193: AAA大肥鱼: 我是一条鱼", "我是一条鱼"),
        # 报告 3.2 的传染链：前缀一层层叠上去，必须全部削掉
        ("166: AAA大肥鱼: AAA大肥鱼: 我是一条鱼", "我是一条鱼"),
        ("168: AAA大肥鱼: 193: AAA大肥鱼: 我是一条鱼", "我是一条鱼"),
        # 行首 [msg_id=...] 标注（含负数合成 id）
        ("[msg_id=-1789473219564212] 169: AAA大肥鱼: 我是一条鱼", "我是一条鱼"),
        ("[msg_id=907583597] 少女", "少女"),
        # 只有名字那一层 / 只有编号那一层
        ("AAA大肥鱼: 你觉得呢", "你觉得呢"),
        ("192: AAA大肥鱼: 我是一条鱼", "我是一条鱼"),
    ],
)
def test_strips_learned_annotation_prefixes(dirty: str, expected: str) -> None:
    assert clean_text(dirty, known_sender_names=KNOWN) == expected


def test_strips_prefix_on_every_line() -> None:
    """多行脏输出（把整段聊天记录续写出来）必须逐行清理。"""
    dirty = "215: 贝拉: 要抱抱\n193: AAA大肥鱼: 我是一条鱼"
    assert clean_text(dirty, known_sender_names=KNOWN) == "要抱抱\n我是一条鱼"


def test_strips_replied_message_marker() -> None:
    assert clean_text("[被回复消息] 贝拉: 在吗", known_sender_names=KNOWN) == "在吗"


# ── 思维链标签（报告 3.3 / P2） ───────────────────────────────────


@pytest.mark.parametrize(
    "dirty, expected",
    [
        ("<think>用户想要抱抱</think>来抱抱", "来抱抱"),
        ("<thinking>草稿</thinking>简短俏皮", "简短俏皮"),
        # 未闭合（输出被截断）时，标签之后的内容全部视为思考
        ("<think>实际上我需要回复一句就好", ""),
        ("先说结论<think>这里是草稿", "先说结论"),
        ("<think>a<think>b</think>c</think>", "c"),
    ],
)
def test_strips_think_tags(dirty: str, expected: str) -> None:
    assert clean_text(dirty) == expected


def test_keeps_fenced_code_intact() -> None:
    """围栏代码块里的 <think> 是用户在聊技术，原样保留。"""
    text = "这样写：\n```\n<think>占位</think>\n```\n结束"
    assert clean_text(text) == text


# ── 不误伤正常回复 ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "好哦",
        "我这就去看看",
        "666",
        "1:0 这比分绝了",
        "看下 [1,2,3] 这个数组",
        "@QQ:3830912140 要抱抱",
        "你说的 贝拉: 那句我没看到",
        "<这是新的可能要回答的内容>",
        "在的，怎么了？",
        "这段话里提到 1: 0 的比分",
    ],
)
def test_keeps_legitimate_replies(text: str) -> None:
    assert clean_text(text, known_sender_names=KNOWN) == text


def test_unknown_name_prefix_is_kept() -> None:
    """名字不在已知集合里时不削 —— 宁可漏一次也不误改正文。"""
    assert clean_text("小明: 你好", known_sender_names=KNOWN) == "小明: 你好"


@pytest.mark.parametrize(
    "text",
    [
        "-1: 这是正文",
        "10: 30 见",
        "20:30 开始",
        "192:草稿没有空格",
    ],
)
def test_bare_number_prefix_needs_annotation_shape(text: str) -> None:
    """裸编号只有在「后面紧跟已知名字」或「整条就到此为止」时才削。

    `10: 30 见` / `20:30 开始` 这类正常内容必须原样保留 —— 精度优先于召回。
    """
    assert clean_text(text, known_sender_names=KNOWN) == text


def test_clean_text_is_idempotent() -> None:
    once = clean_text("193: AAA大肥鱼: <think>草稿</think>我是一条鱼", known_sender_names=KNOWN)
    assert once == "我是一条鱼"
    assert clean_text(once, known_sender_names=KNOWN) == once


@pytest.mark.parametrize("value", ["", "   ", None])
def test_clean_text_handles_blank(value) -> None:
    assert clean_text(value) == ""


def test_known_names_are_escaped() -> None:
    """名字里的正则元字符必须被转义（.純屬虛構. 的点号不能当通配符）。"""
    assert clean_text(".純屬虛構.: 少女", known_sender_names=KNOWN) == "少女"
    assert clean_text("X純屬虛構X: 少女", known_sender_names=KNOWN) == "X純屬虛構X: 少女"


def test_without_known_names_only_brackets_are_stripped() -> None:
    """拿不到发送者名字时保守退化：只削方括号标注与裸编号+行尾。"""
    assert clean_text("[msg_id=1] 193: AAA大肥鱼: 我是一条鱼") == "193: AAA大肥鱼: 我是一条鱼"
    assert clean_text("192:", known_sender_names=None) == ""


# ── 残渣判定与分句清洗 ───────────────────────────────────────────


@pytest.mark.parametrize(
    "original, cleaned, expected",
    [
        ("192:", "", True),
        ("AAA大肥鱼:", "", True),
        ("[msg_id=-123] 169: AAA大肥鱼:", "", True),
        ("192: AAA大肥鱼:", "", True),
        ("666", "666", False),      # 从未被清洗过 ⇒ 不是残渣
        ("...", "...", False),
        ("好哦", "好哦", False),
        ("193: 我是一条鱼", "我是一条鱼", False),
    ],
)
def test_should_drop(original: str, cleaned: str, expected: bool) -> None:
    assert should_drop(original, cleaned, known_sender_names=KNOWN) is expected


def test_clean_segments_drops_residue_and_keeps_order() -> None:
    segments = ["192:", "我是一条鱼", "AAA大肥鱼:", "不是钱", "  "]
    assert clean_segments(segments, known_sender_names=KNOWN) == ["我是一条鱼", "不是钱"]


def test_clean_segments_cleans_each_item() -> None:
    segments = ["193: AAA大肥鱼: 我吃的是token", "<think>草稿</think>不是钱"]
    assert clean_segments(segments, known_sender_names=KNOWN) == ["我吃的是token", "不是钱"]


def test_clean_segments_handles_none() -> None:
    assert clean_segments(None) == []

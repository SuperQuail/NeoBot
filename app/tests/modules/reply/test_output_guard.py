"""output_guard 单元测试：前缀标注 / 思维链标签的兜底清洗。

用例素材直接取自问题报告里的真实落盘证据（群聊实录），确保这条兜底真的能
拦住「续写聊天记录」与「草稿泄漏」两类脏输出，同时不误伤正常回复。
"""

from __future__ import annotations

import pytest

from neobot_app.reply.output_guard import clean_segments, clean_text, should_drop


BOT_NAME = "AAA大肥鱼"
#: 注意：这份集合只是「照着生产接线该长什么样」写的输入参数。
#: 生产里的等价物是 MessageQueue.sender_labels() ∪ 配置昵称，
#: 由 test_sender_labels_come_from_queue_not_handcrafted 锁定（审查指出：
#: 只喂手工构造的名字集合会让用例永远绿灯，掩盖真实缺口）。
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
        # 正文中间的标签是「被提到」而不是泄漏：原样保留，不砍正文
        ("先说结论<think>这里是草稿", "先说结论<think>这里是草稿"),
        # 正文中的标签引用（包括未闭合示例）完整保留，不剥掉示例标签。
        ("前面的话\n<think>这里是草稿", "前面的话\n<think>这里是草稿"),
        # 消息开头的嵌套思考应按深度完整消费，不能把漏洞锁成预期行为。
        ("<think>a<think>b</think>c</think>", ""),
    ],
)
def test_strips_think_tags(dirty: str, expected: str) -> None:
    assert clean_text(dirty) == expected


def test_keeps_inline_and_example_think_tags() -> None:
    """示例/技术性回复里的成对标签属于正文，不得整块删除（只认行首的泄漏）。

    审查员实测场景：群里让机器人写提示词模板时，示例整块消失 → 答非所问。
    """
    example = "模板是这样:\n<thinking>\n先分析用户意图\n</thinking>\n然后回答"
    assert clean_text(example) == example
    fenced = "这样写：\n" + chr(96) * 3 + "\n<think>占位</think>\n" + chr(96) * 3 + "\n结束"
    assert clean_text(fenced) == fenced


def test_keeps_indentation_and_blank_lines() -> None:
    """没有标注时行首空白必须原样保留（markdown 代码块/嵌套列表靠它）。"""
    code = "看这个：\n" + chr(96) * 3 + "python\ndef f():\n    return 1\n" + chr(96) * 3
    assert clean_text(code) == code
    assert clean_text("def f():\n    return 1") == "def f():\n    return 1"
    assert clean_text("- a\n  - b") == "- a\n  - b"
    # 有标注时才连带吃掉标注占的那段空白（用已知名字，见 KNOWN）
    assert clean_text("12: 贝拉:     缩进后面的正文", known_sender_names=KNOWN) == "缩进后面的正文"


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
        # 正文里提到 <think> 标签属于正常聊天：未闭合标签只在行首才当泄漏处理
        "我在想 <think> 这种标签到底是干嘛的",
        "这个 <thinking> 标签是你们内部用的吗",
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


# ── 生产接线：名字集合必须真的从队列里来 ─────────────────────────


def _group_message(message_id: int, user_id: int, nickname: str, text: str):
    from neobot_adapter.model.basic import PostMessageMessagesender
    from neobot_adapter.model.message import GroupMessage, MessageSegment

    return GroupMessage(
        message_id=message_id,
        user_id=user_id,
        group_id=888888,
        sender=PostMessageMessagesender(user_id=user_id, nickname=nickname),
        message=[MessageSegment(type="text", data={"text": text})],
        raw_message=text,
    )


def test_sender_labels_come_from_queue_not_handcrafted() -> None:
    """审查缺口回归：前缀里的名字常常是**别人**，名字集合必须覆盖全部发送者。

    原实现只收 Bot 自己（bot_sender_labels），于是报告主症状
    `215: 贝拉: 要抱抱` 在生产接线下洗不掉，还会被按空格切成三条发出去。
    """
    from neobot_app.message.queue import MessageQueue
    from neobot_app.message.numbering import MessageNumbering

    BOT_QQ, USER_QQ = 10001, 20001
    queue = MessageQueue(
        max_size=50, timestamp_interval_seconds=10_000_000, bot_account=BOT_QQ
    )
    queue.push("888888", _group_message(1, USER_QQ, "贝拉", "要抱抱"))
    queue.push("888888", _group_message(-99, BOT_QQ, BOT_NAME, "我是一条鱼"))

    names = MessageNumbering(bot_account=BOT_QQ, queue=queue).known_sender_names()
    assert "贝拉" in names and BOT_NAME in names

    # 用「生产真实拿到的集合」清洗报告里的脏输出（不是手工喂的 KNOWN）
    assert clean_text("215: 贝拉: 要抱抱", known_sender_names=names) == "要抱抱"
    assert (
        clean_text("193: AAA大肥鱼: 我是一条鱼", known_sender_names=names)
        == "我是一条鱼"
    )


def test_clean_text_is_idempotent_on_annotation_chains() -> None:
    """审查缺口回归：被名字层「露出来」的标注必须当趟就处理干净。

    工具层只清一趟就把「已发送 X」回报给模型，若这里不幂等，
    模型看到的文本与实际发出/写回历史的内容就会漂移。
    """
    cases = [
        "AAA大肥鱼: [msg_id=909] 在的",
        "AAA大肥鱼: 192: 我是一条鱼",
        "166: AAA大肥鱼: AAA大肥鱼: 我是一条鱼",
        "[msg_id=1] 12: 贝拉: [msg_id=2] 你好",
    ]
    for raw in cases:
        once = clean_text(raw, known_sender_names=KNOWN)
        assert clean_text(once, known_sender_names=KNOWN) == once, raw


def test_punctuation_only_reply_is_never_dropped() -> None:
    """审查缺口回归：`？？？`/`。。。` 是正常回复，带前缀也不许被吞。"""
    for text in ["？？？", "。。。", "(^_^)", "!!!"]:
        cleaned = clean_text("12: 贝拉: " + text, known_sender_names=KNOWN)
        assert cleaned == text
        assert should_drop("12: 贝拉: " + text, cleaned, known_sender_names=KNOWN) is False


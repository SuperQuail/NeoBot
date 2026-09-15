"""发送前的输出兜底清洗（前缀标注 / 思维链标签）。

背景（这是一个真实缺陷，不是防御性编程）：

    user:      [msg_id=907583597] 193: .純屬虛構.: 少女
    assistant: [msg_id=-1789473219564212] 169: AAA大肥鱼: 我是一条鱼

模型被告知「assistant 消息就是你自己说过的话」，而历史里的 assistant 消息
**带着系统生成的 `编号: 发送者:` 前缀** —— 于是它把前缀当成了自己该输出的格式，
开始续写聊天记录；脏输出又经 `ReplySender._emit_self_sent_text` 写回历史，
下一轮模仿得更起劲，形成正反馈。

提示词与工具描述已按根因修好（不再把标注渲染进 assistant 消息、并明确禁止
行首标注），本模块是**最后一道兜底**：即使模型偶尔仍然吐标注，也不会发到 QQ。
设计上刻意保守 —— 只处理「行首的、可确证是系统标注」的形态：

* `[msg_id=...]` / `[被回复消息]` 方括号标注：只可能是系统生成的，删；
* `编号: 发送者名字: `：**仅当**名字出现在已知集合里（当前会话出现过的昵称）
  才删，并且可以连续削多层（`168: AAA大肥鱼: 193: AAA大肥鱼: 我是一条鱼`）；
* 裸 `192:`：只有后面紧跟已知名字、或整行就到此为止时才削 ——
  「10: 30 见」「1: 你好」「1:0 这比分绝了」这类正文必须原样保留
  （精度优先于召回，取舍见 `_PrefixStripper._strip_bare_number`）；
* `<think>...</think>`：本体此前承诺了 `<think>` 工作方式却从不剥离（报告 P2），
  这里按「成对 / 未闭合」两种形态剥离；代码围栏内的内容原样保留；
* 整条只剩标注残渣（如 `192:`、`AAA大肥鱼:`）时判定为「应丢弃」，不发空消息。

纯函数、无副作用，可被工具层与发送层重复调用（幂等）。
"""

from __future__ import annotations

import re

#: 发送前清洗时可用的已知发送者名字上限（超出只保留前 N 个，防病态输入）。
MAX_KNOWN_SENDER_NAMES = 200

#: 单次清洗里剥前缀的迭代上限（每次迭代至少删掉一层，正常 1-3 次收敛）。
_MAX_PREFIX_PASSES = 6

#: 嵌套 `<think>` 块的最大剥离轮数（每轮至少吃掉一对标签）。
_MAX_THINK_BLOCK_PASSES = 5

# 思维链标签：本体从不读取 reasoning_content，也不剥离这些标签，模型真按
# <cot> 那段要求写就会原样发到群里，所以这里统一剥掉。
_THINK_TAGS = ("think", "thinking", "reasoning", "cot", "analysis")
_TAG_ALTERNATION = "|".join(_THINK_TAGS)
_THINK_OPEN = re.compile(r"<\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"<\s*/\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE)
#: 行首的未闭合开标签（前面只有空白）：这种才是「思考泄漏」，正文中间的引用不是
_THINK_LINE_OPEN = re.compile(
    r"^[ \t]*<\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE | re.MULTILINE
)
#: 行首的闭合标签（换行后顶格写）：成对块被剥离后留下的那种残渣
_THINK_LINE_CLOSE = re.compile(
    r"^[ \t]*<\s*/\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE | re.MULTILINE
)
_THINK_BLOCK = re.compile(
    r"<\s*(?:" + _TAG_ALTERNATION + r")\s*>.*?<\s*/\s*(?:"
    + _TAG_ALTERNATION
    + r")\s*>",
    re.IGNORECASE | re.DOTALL,
)

#: 行首的 [msg_id=...] 系统标注。message_id 可能是负数（bot 自身发言用合成 id）。
_MSG_ID = re.compile(
    r"^[ \t]*\[\s*msg_id\s*=\s*[-+]?\d+\s*\][ \t]*[:：]?[ \t]*",
    re.MULTILINE,
)

#: 行首的裸 `[被回复消息]` 标注（引用原文时系统加的标记，不属于正文）。
_REPLIED_MARK = re.compile(r"^[ \t]*\[被回复消息\][ \t]*[:：]?[ \t]*", re.MULTILINE)

# 行首的裸编号：`215` / `168`。只接受非负整数（负数合成 id 只出现在
# [msg_id=...] 里），冒号后必须是空白或行尾，否则 `1:0` 这类正文会被误削。
_NUMBER_HEAD = r"[ \t]*\d{1,7}[ \t]*[:：](?=[ \t]|\Z)"
_NUMBER_PREFIX = re.compile(r"^" + _NUMBER_HEAD, re.MULTILINE)
_NUMBER_MARK = re.compile(r"^" + _NUMBER_HEAD, re.MULTILINE)
_NUMBER_ONLY = re.compile(r"^[ \t]*\d{1,7}[ \t]*[:：][ \t]*\Z", re.MULTILINE)
_MARKER_ONLY = re.compile(
    r"^[ \t]*(?:\[msg_id\s*=\s*[-+]?\d+\s*\]|\[被回复消息\])[ \t]*[:：]?[ \t]*\Z",
    re.MULTILINE,
)
_PUNCT_ONLY = re.compile(
    r'^[\s\-–—+*/\\|,，。.:：;；、!！?？~～^_=<>《》「」『』'
    + "'"
    + r'“”‘’()（）\[\]【】{}…#@·•]*\Z'
)

#: 行首的 `发送者名字: ` 引用（名字由调用方给出，见 clean_text）。
_MAX_NAME_CHARS = 40

#: 按代码围栏切分，奇数段是围栏内容（原样保留，不剥标签）。
_FENCE_SPLIT = re.compile(r"(```.*?```)", re.DOTALL)


def _known_names(known_sender_names: list[str] | tuple[str, ...] | None) -> list[str]:
    """规整已知发送者名字：去空、去首尾空白、去重、按长度降序（先长后短）。

    `QQ:123` 形态的兜底名字不参与（正文里出现 `QQ:123` 未必是前缀标注）。
    """
    if not known_sender_names:
        return []
    seen: dict[str, None] = {}
    for raw in known_sender_names:
        name = str(raw or "").strip()
        if not name or name.startswith("QQ:") or len(name) > _MAX_NAME_CHARS:
            continue
        seen.setdefault(name, None)
    return sorted(seen, key=len, reverse=True)[:MAX_KNOWN_SENDER_NAMES]


class _PrefixStripper:
    """行首系统标注的剥离器。

    把「已知名字」编译成一份正则（避免逐行重编译），并负责区分
    「可确认的标注」（该削）与「长得像的正常正文」（必须保留）。
    """

    #: 命中「名字: 」引用的行首匹配式；没有已知名字时为 None
    _ref: re.Pattern[str] | None
    _name_only: re.Pattern[str] | None
    _ref_after_head: re.Pattern[str] | None

    def __init__(self, known_sender_names: list[str] | tuple[str, ...] | None) -> None:
        self._names = _known_names(known_sender_names)
        if self._names:
            alternation = "|".join(re.escape(name) for name in self._names)
            # 行首的「[被回复消息] [名字]: 」；名字两侧的方括号是渲染时可选带的
            head = (
                r"^[ \t]*(?:\[被回复消息\][ \t]*)?\[?(?:"
                + alternation
                + r")\]?[ \t]*[:：][ \t]*"
            )
            self._ref = re.compile(head, re.MULTILINE)
            self._name_only = re.compile(
                r"^[ \t]*\[?(?:" + alternation + r")\]?[ \t]*[:：][ \t]*\Z",
                re.MULTILINE,
            )
        else:
            self._ref = None
            self._name_only = None
        # 名字也能作为 _NUMBER_HEAD 之后紧跟的「引用」，用于判断裸编号是不是标注
        self._ref_after_head = (
            re.compile(r"^\[?(?:" + "|".join(re.escape(name) for name in self._names) + r")\]?[ \t]*[:：]")
            if self._names
            else None
        )

    @property
    def usable(self) -> bool:
        return self._ref is not None

    def strip_prefixes(self, text: str) -> str:
        """连续削掉行首的多层 `编号: 名字: ` 前缀（含整行只剩 `192:` 的情况）。

        逐行处理：模型续写聊天记录时，每一条脏消息都单独占一行。
        """
        if not text:
            return text
        lines = [self._strip_line(line) for line in text.split("\n")]
        return "\n".join(lines)

    def strip_name_prefixes(self, text: str) -> str:
        """削掉行首的裸 `名字: `（逐行）。"""
        if self._ref is None:
            return text
        return self._ref.sub("", text)

    def is_annotation_only(self, text: str) -> bool:
        """判断（已剥过前缀的）文本是否只剩标注残渣。"""
        candidate = text.strip()
        if not candidate:
            return True
        if _PUNCT_ONLY.match(candidate):
            return True
        if _NUMBER_ONLY.fullmatch(candidate) or _MARKER_ONLY.fullmatch(candidate):
            return True
        if self._name_only is not None and self._name_only.fullmatch(candidate):
            return True
        return False

    def has_annotation(self, text: str) -> bool:
        """判断文本里是否真的出现过可确认的系统标注（用于区分「残渣」与「短回复」）。"""
        candidate = str(text or "")
        if _MSG_ID.search(candidate) or _REPLIED_MARK.search(candidate):
            return True
        if _NUMBER_MARK.search(candidate) or _MARKER_ONLY.search(candidate):
            return True
        if self._ref is not None and self._ref.search(candidate):
            return True
        return any(
            self._strip_line(line) != line.lstrip()
            for line in candidate.split("\n")
        )

    def _strip_line(self, line: str) -> str:
        current = line.lstrip()
        for _ in range(_MAX_PREFIX_PASSES):
            before = current
            started_with_number = _NUMBER_PREFIX.match(current) is not None
            candidate = current
            if started_with_number:
                # 依次剥「编号」与「编号后的名字」两层，一层一轮，最多两类前缀
                candidate = self._strip_bare_number(candidate)
                if candidate == current and self._ref is not None:
                    candidate = self._ref.sub("", candidate, count=1)
            elif self._ref is not None:
                candidate = self._ref.sub("", candidate, count=1)
                # 削掉名字后可能露出「182: 」这类编号残渣
                if candidate != current:
                    candidate = self._strip_bare_number(candidate)
            current = candidate.lstrip()
            if current == before:
                break
        return current

    def _strip_bare_number(self, text: str) -> str:
        """削掉行首的裸编号，但只在这个编号确实是标注时才削。

        判定依据（少误伤优先）：编号后面紧跟已知发送者名字，或者整行就到此为止
        —— 「10: 30 见」「1: 你好」「1:0 这比分绝了」都不满足，因此原样保留。

        已知取舍：单独一句「192: 我是一条鱼」（编号后不是已知名字）不会被剥掉，
        因为与「1: 你好」这类正常带序号正文无法区分。实测脏输出总会在编号后带上
        发送者名字（模型模仿的正是历史里那套完整格式），漏掉的概率极低。
        """
        match = _NUMBER_PREFIX.match(text)
        if match is None:
            return text
        rest = text[match.end():]
        if not rest.strip():
            return ""
        head = rest.lstrip()
        if self._ref_after_head is not None and self._ref_after_head.match(head) is not None:
            return head
        return text


def _strip_think_blocks(text: str) -> str:
    """剥离 `<think>` 类标签内容；代码围栏内原样保留。"""
    if "<" not in text:
        return text
    parts = _FENCE_SPLIT.split(text)
    for index in range(0, len(parts), 2):
        part = parts[index]
        if not part or "<" not in part:
            continue
        # 非贪婪逐个删除：嵌套时也能把整块连同内层标签一起吃掉
        cleaned = part
        for _ in range(_MAX_THINK_BLOCK_PASSES):
            updated = _THINK_BLOCK.sub("", cleaned)
            if updated == cleaned:
                break
            cleaned = updated
        # 未闭合的 <think>：其后全部视为思考内容（模型被截断时会这样）。
        # 只在**行首**才认定为泄漏：模型写草稿时标签总在行首，而正文里提到
        # "<think> 这个标签" 属于正常聊天，不该被砍掉半句话。
        # 只认「行首的标签」：模型写草稿时标签一定在行首，而正文里提到
        # "<think> 这个标签" 属于正常聊天 —— 正文中间的标签一律原样保留。
        match = _THINK_LINE_OPEN.search(cleaned)
        if match is not None and _THINK_CLOSE.search(cleaned, match.end()) is None:
            # 行首未闭合 ⇒ 其后全是草稿
            cleaned = cleaned[: match.start()]
        else:
            # 行首孤立的开标签（读到一半断了）才是残渣；文字里的标签不动
            cleaned = _THINK_LINE_OPEN.sub("", cleaned)
            cleaned = _THINK_LINE_CLOSE.sub("", cleaned)
        parts[index] = cleaned
    return "".join(parts)


def clean_text(
    text: str,
    *,
    known_sender_names: list[str] | tuple[str, ...] | None = None,
) -> str:
    """清洗待发送文本：剥离思维链标签与行首系统标注。

    幂等：对已清洗过的文本再调用不会继续变化。
    """
    stripper = _PrefixStripper(known_sender_names)
    current = _strip_think_blocks(str(text or ""))
    current = _MSG_ID.sub("", current)
    current = _REPLIED_MARK.sub("", current)
    if stripper.usable:
        current = stripper.strip_name_prefixes(current)
    current = stripper.strip_prefixes(current)
    lines = [line.rstrip() for line in current.split("\n")]
    return "\n".join(lines).strip()


def should_drop(
    original: str,
    cleaned: str,
    *,
    known_sender_names: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """判断一条消息是否已被清洗成「只剩标注残渣」而不该发送。

    必须同时满足两点，避免误伤 `666`、`...` 这类合法短回复：
    1. 原文里确实存在可确认的系统标注；
    2. 清洗后除了标点/数字/引号之类没有别的内容。
    """
    if str(cleaned or "").strip() == str(original or "").strip():
        return False
    stripper = _PrefixStripper(known_sender_names)
    if not stripper.has_annotation(str(original or "")):
        return False
    return stripper.is_annotation_only(str(cleaned or ""))


def clean_segments(
    segments: list[str] | tuple[str, ...] | None,
    *,
    known_sender_names: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """逐条清洗分句结果，丢弃清洗后为空或只剩残渣的条目。"""
    cleaned: list[str] = []
    for segment in segments or []:
        original = str(segment or "")
        text = clean_text(original, known_sender_names=known_sender_names)
        if not text or should_drop(original, text, known_sender_names=known_sender_names):
            continue
        cleaned.append(text)
    return cleaned

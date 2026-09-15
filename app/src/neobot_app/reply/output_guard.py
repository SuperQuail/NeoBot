"""发送前的输出兜底清洗（前缀标注 / 思维链标签）。

背景（这是一个真实缺陷，不是防御性编程）：

    user:      [msg_id=907583597] 193: .純屬虛構.: 少女
    assistant: [msg_id=-1789473219564212] 169: AAA大肥鱼: 我是一条鱼

模型被告知「assistant 消息就是你自己说过的话」，而历史里的 assistant 消息
**带着系统生成的 `编号: 发送者:` 前缀** —— 于是它把前缀当成了自己该输出的格式，
开始续写聊天记录；脏输出又经 `ReplySender._emit_self_sent_text` 写回历史，
下一轮模仿得更起劲，形成正反馈。

提示词与工具描述已按根因修好（不再把标注渲染进 assistant 消息、并明确禁止
行首标注），本模块对已识别的标注提供发送前兜底；未知格式与无标签草稿仍可能漏检。
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

# 思维链标签：本体从不读取 reasoning_content，也不剥离这些标签，模型真按
# <cot> 那段要求写就会原样发到群里，所以这里统一剥掉。
_THINK_TAGS = ("think", "thinking", "reasoning", "cot", "analysis")
_TAG_ALTERNATION = "|".join(_THINK_TAGS)
_THINK_OPEN = re.compile(r"<\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE)
#: 整条消息就是 `<think>...</think>`（用于「只剩残渣」判定）
_THINK_WHOLE_LINE = re.compile(
    r"\A[ \t]*<\s*(?:" + _TAG_ALTERNATION + r")\s*>.*<\s*/\s*(?:"
    + _TAG_ALTERNATION
    + r")\s*>[ \t]*\Z",
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
#: 行首的 `发送者名字: ` 引用（名字由调用方给出，见 clean_text）。
_MAX_NAME_CHARS = 40

# Fences may be unfinished, longer than three characters, or use tildes.
_FENCE_TOKEN = re.compile(r"`{3,}|~{3,}")
_THINK_TOKEN = re.compile(
    r"<\s*(?P<closing>/)?\s*(?:" + _TAG_ALTERNATION + r")\s*>", re.IGNORECASE
)


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
        """判断（已剥过前缀的）文本是否只剩标注本身。

        刻意**不**把「只剩标点」当残渣：`？？？`、`。。。`、`(^_^)` 都是正常回复，
        带不带前缀都该照发。判定只认确证是标注的形态：空、裸编号、方括号标注、
        孤立的发送者名字、以及行首一整块被剥离的思维链。
        """
        candidate = text.strip()
        if not candidate:
            return True
        if _NUMBER_ONLY.fullmatch(candidate) or _MARKER_ONLY.fullmatch(candidate):
            return True
        if self._name_only is not None and self._name_only.fullmatch(candidate):
            return True
        # 整条就是一行 <think>...</think>（剥完只剩空/空白）
        return bool(_THINK_WHOLE_LINE.fullmatch(candidate))

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
        """剥掉行首的系统标注；**没有标注时原样返回该行**（含缩进）。

        注意不能无条件 lstrip：正文里的 markdown 代码块、嵌套列表、缩进引用
        都靠行首空白，压平了等于毁内容（send_long_reply 的存在意义就是代码块/
        表格）。只有确实削掉了标注，才连带吃掉标注占据的那段空白。
        """
        current = line
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
            if candidate == before:
                break
            # 只有真的削掉了东西，才把标注留下的行首空白一并去掉
            current = candidate.lstrip(" \t")
        return current

    def _strip_bare_number(self, text: str) -> str:
        """削掉行首的裸编号，但只在这个编号确实是标注时才削。

        判定依据（少误伤优先）：编号后面紧跟已知发送者名字，或者整行就到此为止
        —— 「10: 30 见」「1: 你好」「1:0 这比分绝了」都不满足，因此原样保留。

        已知取舍：单独一句「192: 我是一条鱼」（编号后不是已知名字）不会被剥掉，
        因为与「1: 你好」这类正常带序号正文无法区分。这是保留正常内容的取舍，
        不保证覆盖所有模型输出格式。
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


def _consume_leading_think(text: str, depth: int = 0) -> tuple[str, int]:
    """Consume leading reasoning with nesting, retaining depth across segments.

    Only a leading tag starts a block. Tags in prose/examples are literal.
    An unclosed leading block consumes the remainder (including later segments).
    """
    cursor = 0
    while True:
        if depth == 0:
            leading = len(text[cursor:]) - len(text[cursor:].lstrip())
            opening = _THINK_OPEN.match(text, cursor + leading)
            if opening is None:
                return text[cursor:], 0
            cursor = opening.end()
            depth = 1
        for tag in _THINK_TOKEN.finditer(text, cursor):
            depth += -1 if tag.group("closing") else 1
            cursor = tag.end()
            if depth == 0:
                break
        else:
            return "", depth


def _strip_prefixes_outside_fences(
    text: str, stripper: _PrefixStripper, fence: str | None = None,
) -> tuple[str, str | None]:
    """Protect complete AND unfinished backtick/tilde fences from all cleanup."""
    def clean(part: str, start: int, *, followed_by_fence: bool = False) -> str:
        # Slicing must not invent a start/end of line around an inline fence.
        inline = start > 0 and text[start - 1] != "\n"
        if inline:
            part = "\0" + part
        if followed_by_fence:
            part += "\0"
        while True:
            before = part
            part = _MSG_ID.sub("", part)
            part = _REPLIED_MARK.sub("", part)
            part = stripper.strip_prefixes(part)
            if part == before:
                break
        if followed_by_fence:
            part = part[:-1]
        return part[1:] if inline else part

    parts: list[str] = []
    cursor = 0
    while True:
        if fence is None:
            opening = _FENCE_TOKEN.search(text, cursor)
            if opening is None:
                parts.append(clean(text[cursor:], cursor))
                return "".join(parts), None
            parts.append(clean(text[cursor:opening.start()], cursor, followed_by_fence=True))
            marker = opening.group()
            line_end = text.find("\n", opening.end())
            if line_end < 0:
                line_end = len(text)
            inline_close = next((
                token for token in _FENCE_TOKEN.finditer(text, opening.end(), line_end)
                if token.group() == marker
            ), None)
            if inline_close is not None:
                # Inline code is protected locally, never carried into later messages.
                parts.append(text[opening.start():inline_close.end()])
                cursor = inline_close.end()
                continue
            # Prefix removal may expose a real block opener ("Bot: ```text").
            # Decide from the cleaned line, before touching any fenced content.
            if "".join(parts).rsplit("\n", 1)[-1].strip():
                # A run inside prose is not an unfinished Markdown block fence.
                parts.append(marker)
                cursor = opening.end()
                continue
            fence = marker
            start, search_from = opening.start(), opening.end()
        else:
            start, search_from = cursor, cursor
        closing = next((
            token for token in _FENCE_TOKEN.finditer(text, search_from)
            if token.group()[0] == fence[0] and len(token.group()) >= len(fence)
            and not text[text.rfind("\n", 0, token.start()) + 1:token.start()].strip()
            and not text[token.end():].split("\n", 1)[0].strip()
        ), None)
        if closing is None:
            parts.append(text[start:])
            return "".join(parts), fence
        parts.append(text[start:closing.end()])
        cursor = closing.end()
        fence = None


def _clean_with_state(
    text: str, stripper: _PrefixStripper, depth: int = 0, fence: str | None = None,
) -> tuple[str, int, str | None]:
    current = str(text or "").strip()
    if depth:
        current, depth = _consume_leading_think(current, depth)
        if depth:
            return "", depth, None
    # Every changing pass deletes characters, so termination is bounded by the
    # input length, not an arbitrary cap that could leave a different second pass.
    while True:
        before = current
        current, next_fence = _strip_prefixes_outside_fences(current, stripper, fence)
        if fence is None:
            current, depth = _consume_leading_think(current)
        current = current.strip()
        if depth:
            return current, depth, None
        if current == before:
            return current, depth, next_fence


def clean_text(
    text: str,
    *,
    known_sender_names: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Remove leading reasoning and annotations; preserve fenced/inline examples.

    Cleanup reaches a fixed point, including whitespace exposed by deletions.
    Untagged reasoning cannot reliably be distinguished from ordinary prose.
    """
    cleaned, _, _ = _clean_with_state(text, _PrefixStripper(known_sender_names))
    return cleaned


def should_drop(
    original: str,
    cleaned: str,
    *,
    known_sender_names: list[str] | tuple[str, ...] | None = None,
) -> bool:
    """判断一条消息是否已被清洗成「只剩标注残渣」而不该发送。

    必须同时满足：原文中存在标注，且清洗后为空或仅剩标注。
    标点、数字与引号本身可以是正常回复，不按残渣删除。
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
    """清洗分句并跨分句保留思考块深度，避免正文段逃逸。"""
    cleaned: list[str] = []
    stripper = _PrefixStripper(known_sender_names)
    depth = 0
    fence = None
    for segment in segments or []:
        text, depth, fence = _clean_with_state(str(segment or ""), stripper, depth, fence)
        if text:
            cleaned.append(text)
    return cleaned

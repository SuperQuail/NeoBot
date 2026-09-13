from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EventContext:
    raw_event: dict[str, Any]
    consumed: bool = False
    skip_ai_reply: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    #: 插件消息处理器请求的「交主回复管线」意图（一次性；take 后即清除）
    agent_reply_intent: dict[str, Any] | None = None
    #: 标记是否已记录过意图（测试 / 诊断用，不清除）
    agent_reply_requested: bool = False

    @property
    def post_type(self) -> str | None:
        value = self.raw_event.get("post_type")
        return str(value) if value is not None else None

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True

    def agent_reply(
        self, background: str = "", *, preactivate: Sequence[str] = ()
    ) -> None:
        """把本轮交回主回复管线，并声明要预激活的技能包。

        与 CommandContext.sync_reply 同语义（spec(5) R13）：不发固定文本，把
        「事实 + 提示词」作为背景交给主回复管线，由模型组织回复；preactivate
        里列出的技能名会在**本轮**回复构建工具表时被激活，使对应的
        {plugin}__{tool} 立即可以调用。登记是**一次性**的（take 时清除）。
        """
        text = str(background or "")
        names: list[str] = []
        for item in preactivate or ():
            name = str(item or "").strip()
            if name and name not in names:
                names.append(name)
        if not text and not names:
            return
        self.agent_reply_intent = {"background": text, "preactivate": tuple(names)}
        self.agent_reply_requested = True

    def take_agent_reply_intent(self) -> dict[str, Any] | None:
        """取出并清除本轮意图（一次性消费；重复调用返回 None）。"""
        intent = self.agent_reply_intent
        self.agent_reply_intent = None
        return intent

    def has_agent_reply_intent(self) -> bool:
        return self.agent_reply_intent is not None

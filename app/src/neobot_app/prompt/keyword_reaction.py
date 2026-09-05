from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from neobot_contracts.ports.logging import Logger, NullLogger

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import KeyWordRule
    from neobot_app.message.queue import MessageQueue


@dataclass(frozen=True, slots=True)
class KeywordReactionItem:
    rule_index: int
    prompt_index: int
    matched_keywords: tuple[str, ...]
    matched_depths: tuple[int, ...]
    prompt_text: str


class KeywordReactionBuilder:
    def __init__(self, rules: list["KeyWordRule"] | None, logger: Logger | None = None) -> None:
        self._rules = rules or []
        self._logger = logger or NullLogger()
        # 预计算:规则关键词的 casefold 结果(匹配热路径避免逐消息重复 casefold)
        self._prepared_rules: list[dict] = []
        for rule in self._rules:
            keywords = [str(item).strip() for item in rule.get("keywords", []) if str(item).strip()]
            self._prepared_rules.append(
                {
                    "rule": rule,
                    "keywords": keywords,
                    "casefold_keywords": [k.casefold() for k in keywords],
                }
            )

    def build(
        self,
        *,
        queue: "MessageQueue",
        queue_key: str,
        conversation_type: str,
    ) -> str:
        items = self.collect(queue=queue, queue_key=queue_key)
        if not items:
            return ""

        self._logger.info(
            "关键词提示词触发",
            conversation_type=conversation_type,
            conversation_id=queue_key,
            triggered_count=len(items),
            matched_keywords=" | ".join("、".join(item.matched_keywords) for item in items),
            matched_depths=" | ".join(",".join(str(depth) for depth in item.matched_depths) for item in items),
        )
        return "\n".join(
            f"<追加信息_{index}>对于\"{'、'.join(item.matched_keywords)}\",{item.prompt_text}</追加信息_{index}>"
            for index, item in enumerate(items, start=1)
        )

    def collect(
        self,
        *,
        queue: "MessageQueue",
        queue_key: str,
    ) -> list[KeywordReactionItem]:
        try:
            recent_messages = list(queue.iterate_from_newest(queue_key))
        except KeyError:
            return []

        # 跳过 bot 自己发出的消息(语音/长回复等自推消息也会进队列),
        # 避免关键词规则因 bot 自己的发言自触发
        bot_account = getattr(queue, "bot_account", None)
        if bot_account:
            try:
                bot_account = int(bot_account)
            except (TypeError, ValueError):
                bot_account = None
        if bot_account:
            recent_messages = [
                message
                for message in recent_messages
                if _safe_user_id(message) != bot_account
            ]

        message_texts = [self._render_message_text(message) for message in recent_messages]
        # 统一 casefold 一次(匹配热路径直接复用,避免每规则每消息重复计算)
        casefolded_texts = [text.casefold() for text in message_texts]
        items: list[KeywordReactionItem] = []

        for rule_index, prepared in enumerate(self._prepared_rules, start=1):
            rule = prepared["rule"]
            if not rule.get("enabled", False):
                continue

            normalized_keywords = prepared["keywords"]
            if not normalized_keywords:
                continue

            prompt_texts = self._rule_prompt_texts(rule)
            if not prompt_texts:
                continue

            ignore_case = rule.get("ignore_case", True)
            match_mode = str(rule.get("match_mode", "any")).strip().lower() or "any"
            min_depth = self._normalize_depth(rule.get("min_depth", -1))
            max_depth = self._normalize_depth(rule.get("max_depth", -1))

            matches = self._match_rule(
                keywords=normalized_keywords,
                casefold_keywords=prepared["casefold_keywords"],
                message_texts=message_texts,
                casefolded_texts=casefolded_texts,
                ignore_case=ignore_case,
                match_mode=match_mode,
                min_depth=min_depth,
                max_depth=max_depth,
            )
            if not matches:
                continue

            matched_keywords = tuple(item[0] for item in matches)
            matched_depths = tuple(item[1] for item in matches)
            for prompt_index, prompt_text in enumerate(prompt_texts, start=1):
                items.append(
                    KeywordReactionItem(
                        rule_index=rule_index,
                        prompt_index=prompt_index,
                        matched_keywords=matched_keywords,
                        matched_depths=matched_depths,
                        prompt_text=prompt_text,
                    )
                )

        return items

    @staticmethod
    def _rule_prompt_texts(rule: "KeyWordRule") -> list[str]:
        prompts = [str(item).strip() for item in rule.get("prompt_list", []) if str(item).strip()]
        if prompts:
            return prompts

        description = str(rule.get("description", "")).strip()
        return [description] if description else []

    @staticmethod
    def _normalize_depth(value: object) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return -1

    def _match_rule(
        self,
        *,
        keywords: list[str],
        casefold_keywords: list[str],
        message_texts: list[str],
        casefolded_texts: list[str],
        ignore_case: bool,
        match_mode: str,
        min_depth: int,
        max_depth: int,
    ) -> list[tuple[str, int]]:
        matches: list[tuple[str, int]] = []
        matched_map: dict[str, int] = {}

        for depth, text in enumerate(casefolded_texts if ignore_case else message_texts):
            if min_depth != -1 and depth < min_depth:
                continue
            if max_depth != -1 and depth > max_depth:
                continue

            for keyword_index, keyword in enumerate(keywords):
                if keyword in matched_map:
                    continue
                normalized_keyword = (
                    casefold_keywords[keyword_index] if ignore_case else keyword
                )
                if normalized_keyword and normalized_keyword in text:
                    matched_map[keyword] = depth
                    if match_mode == "any":
                        return [(keyword, depth)]

        if match_mode == "all":
            if all(keyword in matched_map for keyword in keywords):
                matches.extend((keyword, matched_map[keyword]) for keyword in keywords)
            return matches

        if matched_map:
            first_keyword = next(iter(matched_map))
            return [(first_keyword, matched_map[first_keyword])]
        return []

    @staticmethod
    def _render_message_text(message: object) -> str:
        segments = getattr(message, "message", None)
        if segments:
            parts: list[str] = []
            for segment in segments:
                segment_type = getattr(segment, "type", None)
                if hasattr(segment_type, "value"):
                    segment_type = segment_type.value
                raw_data = getattr(segment, "data", None)
                if isinstance(raw_data, dict):
                    data = raw_data
                elif hasattr(raw_data, "model_dump"):
                    data = raw_data.model_dump(exclude_none=True)
                else:
                    data = {}

                if str(segment_type) == "text":
                    parts.append(str(data.get("text") or ""))
                elif str(segment_type) == "at":
                    parts.append(f"@{data.get('name') or data.get('qq') or 'unknown'}")
                elif str(segment_type) == "reply":
                    parts.append("[reply]")
                elif str(segment_type):
                    parts.append(f"[{segment_type}]")
            return "".join(parts).strip()

        return str(getattr(message, "raw_message", "") or "").strip()


def _safe_user_id(message: object) -> int | None:
    """归一化消息 user_id 为 int(防御字符串/None 输入)。"""
    raw = getattr(message, "user_id", None)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None

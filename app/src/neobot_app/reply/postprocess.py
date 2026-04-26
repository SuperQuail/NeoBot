"""Post-process LLM replies before sending."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
import re
from typing import Any


DEFAULT_LONG_REPLY_FALLBACK_TEMPLATE = "{bot_name}懒得和你说道理，你不配听"
DEFAULT_MAX_REPLY_LENGTH = 200
DEFAULT_MAX_SENTENCE_COUNT = 8


@dataclass(frozen=True, slots=True)
class ReplyPostProcessResult:
    original_text: str
    cleaned_text: str
    messages: list[str]
    fallback_used: bool = False
    reason: str | None = None


def process_reply_text(
    text: str,
    *,
    bot_name: str,
    fallback_template: str = DEFAULT_LONG_REPLY_FALLBACK_TEMPLATE,
    max_length: int = DEFAULT_MAX_REPLY_LENGTH,
    max_sentence_count: int = DEFAULT_MAX_SENTENCE_COUNT,
) -> ReplyPostProcessResult:
    original = str(text or "")
    protected_text, kaomoji_mapping = protect_kaomoji(original.strip())
    cleaned_text = _remove_bracketed_notes(protected_text).strip()
    if not cleaned_text:
        cleaned_text = protected_text.strip()

    if len(cleaned_text) > max_length and not is_western_paragraph(cleaned_text):
        fallback = _fallback_text(fallback_template, bot_name)
        return ReplyPostProcessResult(
            original_text=original,
            cleaned_text=cleaned_text,
            messages=[fallback],
            fallback_used=True,
            reason=f"回复过长（{len(cleaned_text)} 字符）",
        )

    split_messages = split_into_sentences_w_remove_punctuation(
        cleaned_text,
        rng=random.Random(_stable_seed(cleaned_text)),
    )
    split_messages = recover_kaomoji(split_messages, kaomoji_mapping)
    split_messages = [message.strip() for message in split_messages if message.strip()]

    if len(split_messages) > max_sentence_count:
        fallback = _fallback_text(fallback_template, bot_name)
        return ReplyPostProcessResult(
            original_text=original,
            cleaned_text=cleaned_text,
            messages=[fallback],
            fallback_used=True,
            reason=f"切分后消息数量过多（{len(split_messages)} 条）",
        )

    return ReplyPostProcessResult(
        original_text=original,
        cleaned_text=recover_kaomoji([cleaned_text], kaomoji_mapping)[0],
        messages=split_messages or [original.strip()],
    )


def split_into_sentences_w_remove_punctuation(text: str, *, rng: Any = random) -> list[str]:
    raw_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    hard_parts = [part.strip() for part in re.split(r"\n+", raw_text) if part.strip()]
    if len(hard_parts) > 1:
        messages: list[str] = []
        for part in hard_parts:
            messages.extend(split_into_sentences_w_remove_punctuation(part, rng=rng))
        return messages

    text = re.sub(r"\n\s*\n+", "\n", str(text or ""))
    text = re.sub(r"\n\s*([，,。;\s])", r"\1", text)
    text = re.sub(r"([，,。;\s])\s*\n", r"\1", text)
    text = re.sub(r"([\u4e00-\u9fff])\n([\u4e00-\u9fff])", r"\1。\2", text)

    if len(text) < 3:
        return list(text) if text and rng.random() < 0.01 else ([text] if text else [])

    separators = {"，", ",", " ", "。", ";"}
    segments: list[tuple[str, str]] = []
    current_segment = ""

    for index, char in enumerate(text):
        if char not in separators:
            current_segment += char
            continue

        can_split = True
        if 0 < index < len(text) - 1:
            prev_char = text[index - 1]
            next_char = text[index + 1]
            if is_english_letter(prev_char) and is_english_letter(next_char):
                can_split = False

        if can_split:
            if current_segment:
                segments.append((current_segment, char))
            elif char == " ":
                segments.append(("", char))
            current_segment = ""
        else:
            current_segment += char

    if current_segment:
        segments.append((current_segment, ""))

    segments = [(content, sep) for content, sep in segments if content or sep]
    if not segments:
        return [text] if text else []

    text_length = len(text)
    if text_length < 12:
        split_strength = 0.2
    elif text_length < 32:
        split_strength = 0.6
    else:
        split_strength = 0.7
    merge_probability = 1.0 - split_strength

    merged_segments: list[tuple[str, str]] = []
    idx = 0
    while idx < len(segments):
        current_content, current_sep = segments[idx]
        if idx + 1 < len(segments) and rng.random() < merge_probability and current_content:
            next_content, next_sep = segments[idx + 1]
            merged_content = current_content + current_sep + next_content if next_content else current_content
            merged_segments.append((merged_content, next_sep))
            idx += 2
        else:
            merged_segments.append((current_content, current_sep))
            idx += 1

    return [content for content, _ in merged_segments if content.strip()]


def protect_kaomoji(sentence: str) -> tuple[str, dict[str, str]]:
    kaomoji_pattern = re.compile(
        r"("
        r"[(\[（【{<『]"
        r"(?:"
        r"[^\w\s一-龥\u3040-\u309F\u30A0-\u30FF]|"
        r"(?:[\w]?[^\w\s一-龥\u3040-\u309F\u30A0-\u30FF]+[\w]?)"
        r")+?"
        r"[)\]）】}>』]"
        r")"
        r"|"
        r"([・•ˇ‸∀´°Дﾟ︶〃―￣▽≧≦○人♂♀♪♫~…*]{2,15})"
    )
    placeholder_to_kaomoji: dict[str, str] = {}
    protected = sentence
    for idx, match in enumerate(kaomoji_pattern.findall(sentence)):
        kaomoji = match[0] if match[0] else match[1]
        placeholder = f"__KAOMOJI_{idx}__"
        protected = protected.replace(kaomoji, placeholder, 1)
        placeholder_to_kaomoji[placeholder] = kaomoji
    return protected, placeholder_to_kaomoji


def recover_kaomoji(sentences: list[str], placeholder_to_kaomoji: dict[str, str]) -> list[str]:
    recovered_sentences: list[str] = []
    for sentence in sentences:
        recovered = sentence
        for placeholder, kaomoji in placeholder_to_kaomoji.items():
            recovered = recovered.replace(placeholder, kaomoji)
        recovered_sentences.append(recovered)
    return recovered_sentences


def is_english_letter(char: str) -> bool:
    return "a" <= char.lower() <= "z"


def is_western_char(char: str) -> bool:
    return len(char.encode("utf-8")) <= 2


def is_western_paragraph(paragraph: str) -> bool:
    return all(is_western_char(char) for char in paragraph if char.isalnum())


def _remove_bracketed_notes(text: str) -> str:
    return re.compile(r"[\(\[（].*?[\)\]）]").sub("", text)


def _fallback_text(template: str, bot_name: str) -> str:
    effective_template = template.strip() or DEFAULT_LONG_REPLY_FALLBACK_TEMPLATE
    return effective_template.replace("{bot_name}", bot_name)


def _stable_seed(text: str) -> int:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return int(digest, 16)

"""spec(5) §4.1：/sleep /awake 提示词分区的默认值与兜底一致性（R2 / A4）。"""

from __future__ import annotations

from neobot_app.prompt.store import (
    DEFAULT_TEMPLATE_FILE,
    KNOWN_SECTIONS,
    _FALLBACK_SECTIONS,
    parse_prompt_file,
)
from neobot_app.runtime.sleep_service import (
    DEFAULT_AWAKE_CMD_PROMPT,
    DEFAULT_SLEEP_CMD_PROMPT,
)


def test_prompt_sections_are_registered() -> None:
    """新增分区必须进 KNOWN_SECTIONS，否则自定义文件里的同名分区会被忽略。"""
    assert "sleep_cmd" in KNOWN_SECTIONS
    assert "awake_cmd" in KNOWN_SECTIONS
    # 与既有 [wake_up] 的分工：三者并存，不合并
    assert "wake_up" in KNOWN_SECTIONS


def test_builtin_template_matches_source_defaults() -> None:
    """内置 prompts.toml 与源码默认值必须逐字一致（避免两处漂移）。"""
    sections = parse_prompt_file(DEFAULT_TEMPLATE_FILE)

    assert sections["sleep_cmd"]["template"] == DEFAULT_SLEEP_CMD_PROMPT
    assert sections["awake_cmd"]["template"] == DEFAULT_AWAKE_CMD_PROMPT
    assert _FALLBACK_SECTIONS["sleep_cmd"]["template"] == DEFAULT_SLEEP_CMD_PROMPT
    assert _FALLBACK_SECTIONS["awake_cmd"]["template"] == DEFAULT_AWAKE_CMD_PROMPT


def test_defaults_use_documented_placeholders() -> None:
    assert "{duration}" in DEFAULT_SLEEP_CMD_PROMPT
    assert "{wake_at}" in DEFAULT_SLEEP_CMD_PROMPT
    assert "{elapsed}" in DEFAULT_AWAKE_CMD_PROMPT
    # 默认模板末尾固定写「不要复述本条状态说明」，避免模型复述状态
    assert "不要复述本条状态说明" in DEFAULT_SLEEP_CMD_PROMPT
    assert "不要复述本条状态说明" in DEFAULT_AWAKE_CMD_PROMPT

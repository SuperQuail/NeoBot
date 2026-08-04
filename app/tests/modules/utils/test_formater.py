"""neobot_app.utils.formater safe_format 文本格式化测试。"""

from __future__ import annotations

import pytest

from neobot_app.utils.formater import safe_format


def test_safe_format_substitutes_provided_values() -> None:
    """Arrange: 模板含单占位符且提供值；Act: safe_format；Assert: 占位符被替换。"""
    template = "群名是{group_name}"

    result = safe_format(template, group_name="NeoBot 群")

    assert result == "群名是NeoBot 群"


def test_safe_format_keeps_missing_placeholder_untouched() -> None:
    """Arrange: 模板占位符未提供值；Act: safe_format；Assert: 占位符原样保留不抛错。"""
    template = "你好{user_name}，欢迎{place}"

    result = safe_format(template)

    assert result == "你好{user_name}，欢迎{place}"


def test_safe_format_mixes_present_and_missing() -> None:
    """Arrange: 模板部分占位符提供值；Act: safe_format；Assert: 只替换提供的值。"""
    result = safe_format("{a}与{b}与{c}", a="1", c="3")

    assert result == "1与{b}与3"


def test_safe_format_formats_non_string_values() -> None:
    """Arrange: 占位符值为整数/布尔；Act: safe_format；Assert: 自动转字符串。"""
    result = safe_format("年龄{age}，状态{ok}", age=18, ok=True)

    assert result == "年龄18，状态True"


def test_safe_format_raises_on_positional_placeholder() -> None:
    """Arrange: 位置式占位符 {0}（本函数只支持关键字）；Act: safe_format；Assert: 抛出 ValueError。"""
    with pytest.raises(ValueError):
        safe_format("{0}号成员")


def test_safe_format_raises_on_malformed_template() -> None:
    """Arrange: 模板含孤立左大括号；Act: safe_format；Assert: 抛出 ValueError（异常路径）。"""
    with pytest.raises(ValueError):
        safe_format("未闭合{占位符")

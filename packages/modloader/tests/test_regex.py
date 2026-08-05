from __future__ import annotations

import re
import unittest

from neobot_modloader.command_dsl import PatternError, RegexPattern
from neobot_modloader.message import Message


class RegexPatternTest(unittest.TestCase):
    def test_named_group_captures(self) -> None:
        pattern = RegexPattern(r"天气 (?P<city>\S+)")

        result = pattern.match(Message({"raw_message": "天气 北京"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values, {"city": "北京"})
        self.assertEqual(pattern.capture_names, ("city",))

    def test_no_match_returns_false_and_empty_values(self) -> None:
        pattern = RegexPattern(r"天气 (?P<city>\S+)")

        result = pattern.match(Message({"raw_message": "今天天气不错"}))

        self.assertFalse(result.matched)
        self.assertEqual(result.values, {})

    def test_optional_named_group_is_none_when_absent(self) -> None:
        pattern = RegexPattern(r"^天气(?: (?P<city>\S+))?$")

        result = pattern.match(Message({"raw_message": "天气"}))

        self.assertTrue(result.matched)
        self.assertIsNone(result.values["city"])

    def test_flags_make_matching_case_insensitive(self) -> None:
        pattern = RegexPattern(r"hello (?P<name>\S+)", flags=re.IGNORECASE)

        result = pattern.match(Message({"raw_message": "HELLO world"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values["name"], "world")

    def test_usage_returns_raw_pattern(self) -> None:
        pattern = RegexPattern(r"天气 (?P<city>\S+)")

        self.assertEqual(pattern.usage, r"天气 (?P<city>\S+)")

    def test_multiple_named_groups_all_injected(self) -> None:
        pattern = RegexPattern(r"(?P<year>\d{4})年(?P<month>\d{1,2})月")

        result = pattern.match(Message({"raw_message": "2026年8月"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values, {"year": "2026", "month": "8"})
        self.assertEqual(pattern.capture_names, ("month", "year"))

    def test_accepts_compiled_pattern(self) -> None:
        pattern = RegexPattern(re.compile(r"hi (?P<who>\S+)", re.IGNORECASE))

        result = pattern.match(Message({"raw_message": "HI there"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values["who"], "there")

    def test_flags_with_compiled_pattern_raise(self) -> None:
        with self.assertRaises(PatternError):
            RegexPattern(re.compile(r"hello"), flags=re.IGNORECASE)

    def test_empty_pattern_raises(self) -> None:
        for pattern in ("", "   ", re.compile("")):
            with self.subTest(pattern=pattern):
                with self.assertRaises(PatternError):
                    RegexPattern(pattern)

    def test_invalid_pattern_raises_pattern_error(self) -> None:
        for pattern in ("(", "*", r"(?P<broken>\d", "a{2,1}", "[a-"):
            with self.subTest(pattern=pattern):
                with self.assertRaises(PatternError) as ctx:
                    RegexPattern(pattern)
                self.assertIs(type(ctx.exception), PatternError)
                self.assertIsInstance(ctx.exception.__cause__, re.error)

    def test_invalid_flags_raise_pattern_error(self) -> None:
        for flags in (-1, re.LOCALE):
            with self.subTest(flags=flags):
                with self.assertRaises(PatternError):
                    RegexPattern("abc", flags=flags)

    def test_non_integer_flags_raise_pattern_error(self) -> None:
        for flags in ("i", None, [re.IGNORECASE]):
            with self.subTest(flags=flags):
                with self.assertRaises(PatternError):
                    RegexPattern("abc", flags=flags)

    def test_overflow_repetition_raises_pattern_error(self) -> None:
        for pattern in ("a{1,4294967296}", "a{2," + "9" * 30 + "}"):
            with self.subTest(pattern=pattern):
                with self.assertRaises(PatternError) as ctx:
                    RegexPattern(pattern)
                self.assertIs(type(ctx.exception), PatternError)
                self.assertIsInstance(ctx.exception.__cause__, OverflowError)

    def test_non_string_or_compiled_input_raises(self) -> None:
        for value in (42, None, b"abc", ["abc"], re.compile(b"abc")):
            with self.subTest(value=value):
                with self.assertRaises(PatternError):
                    RegexPattern(value)

    def test_no_named_groups_returns_empty_values(self) -> None:
        pattern = RegexPattern(r"^\d+$")

        result = pattern.match(Message({"raw_message": "42"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values, {})
        self.assertEqual(pattern.capture_names, ())

    def test_unnamed_groups_are_not_injected(self) -> None:
        pattern = RegexPattern(r"(\d+) (?P<word>\w+)")

        result = pattern.match(Message({"raw_message": "7 hello"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values, {"word": "hello"})
        self.assertEqual(pattern.capture_names, ("word",))

    def test_empty_message_text(self) -> None:
        self.assertFalse(
            RegexPattern(r"\S+").match(Message({"raw_message": ""})).matched
        )
        self.assertTrue(RegexPattern(r"^$").match(Message({"raw_message": ""})).matched)

    def test_multiline_flags_match_across_lines(self) -> None:
        pattern = RegexPattern(r"^第二行", flags=re.MULTILINE)

        result = pattern.match(Message({"raw_message": "第一行\n第二行"}))

        self.assertTrue(result.matched)


if __name__ == "__main__":
    unittest.main()

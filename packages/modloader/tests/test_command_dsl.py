from __future__ import annotations

import unittest

from neobot_modloader.command_dsl import MessagePattern, PatternError
from neobot_modloader.message import AtSegment, ImageSegment, Message


class CommandDslTest(unittest.TestCase):
    def test_command_required_and_optional_text_args(self) -> None:
        pattern = MessagePattern("weather [city]", command=True, aliases=("天气",))

        result = pattern.match(Message({"raw_message": "/天气 Beijing"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values["city"], "Beijing")

        missing = pattern.match(Message({"raw_message": "/weather"}))
        self.assertTrue(missing.matched)
        self.assertIsNone(missing.values["city"])

    def test_command_coerces_basic_types(self) -> None:
        pattern = MessagePattern("debug <enabled:bool> <count:int> <ratio:float>", command=True)

        result = pattern.match(Message({"raw_message": "/debug true 3 0.5"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values, {"enabled": True, "count": 3, "ratio": 0.5})

    def test_command_captures_image_segment(self) -> None:
        pattern = MessagePattern("识图 <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/识图"}},
                    {"type": "image", "data": {"file": "a.image", "url": "https://example/image.png"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertIsInstance(result.values["img"], ImageSegment)
        self.assertEqual(result.values["img"].url, "https://example/image.png")

    def test_message_pattern_captures_multiple_images(self) -> None:
        pattern = MessagePattern("识图 <imgs:list[image]>")
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "识图"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "image", "data": {"file": "b.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([img.file for img in result.values["imgs"]], ["a.image", "b.image"])

    def test_missing_required_image_reports_parse_error(self) -> None:
        pattern = MessagePattern("识图 <img:image>", command=True)

        result = pattern.match(Message({"raw_message": "/识图"}))

        self.assertFalse(result.matched)
        self.assertTrue(result.command_matched)
        self.assertIn("missing required image", result.error or "")

    def test_command_captures_at_segment(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertIsInstance(result.values["user"], AtSegment)
        self.assertEqual(result.values["user"].qq, "123")
        self.assertEqual(result.values["user"].name, "小明")

    def test_optional_at_returns_none_when_missing(self) -> None:
        pattern = MessagePattern("点名 [user:at]", command=True)

        result = pattern.match(Message({"raw_message": "/点名"}))

        self.assertTrue(result.matched)
        self.assertIsNone(result.values["user"])

    def test_missing_required_at_reports_parse_error(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)

        result = pattern.match(Message({"raw_message": "/点名"}))

        self.assertFalse(result.matched)
        self.assertTrue(result.command_matched)
        self.assertIn("missing required at", result.error or "")

    def test_captures_list_of_at_segments(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 111, "name": "甲"}},
                    {"type": "at", "data": {"qq": 222, "name": "乙"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111", "222"])

    def test_at_captures_across_surrounding_text(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名 请"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                    {"type": "text", "data": {"text": " 来一下"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["user"].qq, "123")

    def test_at_and_image_coexist_in_same_pattern(self) -> None:
        pattern = MessagePattern("汇报 <user:at> <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["user"].qq, "123")
        self.assertIsInstance(result.values["img"], ImageSegment)

    def test_rejects_unknown_param_type(self) -> None:
        with self.assertRaises(PatternError):
            MessagePattern("demo <x:unknown>", command=True)


if __name__ == "__main__":
    unittest.main()

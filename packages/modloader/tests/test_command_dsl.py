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

    def test_image_then_at_in_reverse_pattern_order(self) -> None:
        pattern = MessagePattern("汇报 <img:image> <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertIsInstance(result.values["img"], ImageSegment)
        self.assertEqual(result.values["user"].qq, "123")

    def test_optional_at_before_image_does_not_swallow_image(self) -> None:
        pattern = MessagePattern("汇报 [user:at] <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 123}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertIsNone(result.values["user"])
        self.assertIsInstance(result.values["img"], ImageSegment)
        self.assertEqual(result.values["img"].file, "a.image")

    def test_required_at_before_image_stops_at_image(self) -> None:
        pattern = MessagePattern("汇报 <user:at> <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 123}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_optional_at_followed_by_text_param(self) -> None:
        pattern = MessagePattern("汇报 [user:at] <msg:str>", command=True)

        without_at = pattern.match(Message({"raw_message": "/汇报 你好"}))
        with_at = pattern.match(
            Message(
                {
                    "message": [
                        {"type": "text", "data": {"text": "/汇报"}},
                        {"type": "at", "data": {"qq": 123}},
                        {"type": "text", "data": {"text": " 你好"}},
                    ]
                }
            )
        )

        self.assertTrue(without_at.matched)
        self.assertIsNone(without_at.values["user"])
        self.assertEqual(without_at.values["msg"], "你好")
        self.assertTrue(with_at.matched)
        self.assertEqual(with_at.values["user"].qq, "123")
        self.assertEqual(with_at.values["msg"], "你好")

    def test_optional_at_then_literal_then_image(self) -> None:
        pattern = MessagePattern("汇报 [user:at] 快 <img:image>", command=True)

        with_at = pattern.match(
            Message(
                {
                    "message": [
                        {"type": "text", "data": {"text": "/汇报"}},
                        {"type": "at", "data": {"qq": 123}},
                        {"type": "text", "data": {"text": " 快"}},
                        {"type": "image", "data": {"file": "a.image"}},
                    ]
                }
            )
        )
        without_at = pattern.match(
            Message(
                {
                    "message": [
                        {"type": "text", "data": {"text": "/汇报 快"}},
                        {"type": "image", "data": {"file": "a.image"}},
                    ]
                }
            )
        )

        self.assertTrue(with_at.matched)
        self.assertEqual(with_at.values["user"].qq, "123")
        self.assertIsInstance(with_at.values["img"], ImageSegment)
        self.assertTrue(without_at.matched)
        self.assertIsNone(without_at.values["user"])
        self.assertIsInstance(without_at.values["img"], ImageSegment)

    def test_list_at_before_image_does_not_swallow_image(self) -> None:
        pattern = MessagePattern("汇报 <users:list[at]> <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "at", "data": {"qq": 111}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 222}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111"])
        self.assertIsInstance(result.values["img"], ImageSegment)
        self.assertEqual(result.values["img"].file, "a.image")

    def test_optional_list_at_missing_preserves_following_text(self) -> None:
        pattern = MessagePattern("点名 [users:list[at]] <msg:str>", command=True)

        result = pattern.match(Message({"raw_message": "/点名 你好"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values["users"], [])
        self.assertEqual(result.values["msg"], "你好")

    def test_optional_at_with_other_segments_present(self) -> None:
        pattern = MessagePattern("汇报 [user:at] <img:image>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertIsNone(result.values["user"])
        self.assertIsInstance(result.values["img"], ImageSegment)

    def test_list_at_skips_interleaved_text(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 111}},
                    {"type": "text", "data": {"text": " 和 "}},
                    {"type": "at", "data": {"qq": 222}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111", "222"])

    def test_optional_empty_list_at_returns_empty_list(self) -> None:
        pattern = MessagePattern("点名 [users:list[at]]", command=True)

        result = pattern.match(Message({"raw_message": "/点名"}))

        self.assertTrue(result.matched)
        self.assertEqual(result.values["users"], [])

    def test_missing_required_list_at_reports_parse_error(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>", command=True)

        result = pattern.match(Message({"raw_message": "/点名"}))

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_rejects_unknown_param_type(self) -> None:
        with self.assertRaises(PatternError):
            MessagePattern("demo <x:unknown>", command=True)

    def test_single_at_captures_and_ignores_trailing_image(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["user"].qq, "123")

    def test_single_at_blocked_by_leading_image(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 123}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_list_at_stops_at_image_and_ignores_later_at(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 111}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 222}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111"])

    def test_list_at_blocked_by_leading_image(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 111}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_image_greedy_swallows_at_in_reversed_message(self) -> None:
        pattern = MessagePattern("汇报 <img:image> <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_list_image_then_list_at_forward_message(self) -> None:
        pattern = MessagePattern("汇报 <imgs:list[image]> <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "image", "data": {"file": "a.image"}},
                    {"type": "at", "data": {"qq": 123}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([img.file for img in result.values["imgs"]], ["a.image"])
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["123"])

    def test_list_image_then_list_at_reversed_message(self) -> None:
        pattern = MessagePattern("汇报 <imgs:list[image]> <users:list[at]>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/汇报"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")

    def test_non_command_pattern_captures_at(self) -> None:
        pattern = MessagePattern("点名 <user:at>")
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "点名"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertFalse(result.command_matched)
        self.assertEqual(result.values["user"].qq, "123")
        self.assertEqual(result.values["user"].name, "小明")

    def test_non_command_optional_at_missing(self) -> None:
        pattern = MessagePattern("点名 [user:at]")

        result = pattern.match(Message({"raw_message": "点名"}))

        self.assertTrue(result.matched)
        self.assertIsNone(result.values["user"])

    def test_non_command_list_at_captures(self) -> None:
        pattern = MessagePattern("点名 <users:list[at]>")
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "点名"}},
                    {"type": "at", "data": {"qq": 111}},
                    {"type": "text", "data": {"text": " 和 "}},
                    {"type": "at", "data": {"qq": 222}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111", "222"])

    def test_non_command_at_stops_at_image(self) -> None:
        pattern = MessagePattern("点名 <user:at>")
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "点名"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "image", "data": {"file": "a.image"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["user"].qq, "123")

    def test_optional_list_at_with_ats_present_returns_them(self) -> None:
        pattern = MessagePattern("点名 [users:list[at]] <msg:str>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 111}},
                    {"type": "at", "data": {"qq": 222}},
                    {"type": "text", "data": {"text": " 你好"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual([at_segment.qq for at_segment in result.values["users"]], ["111", "222"])
        self.assertEqual(result.values["msg"], "你好")

    def test_at_then_rest_captures_trailing_text(self) -> None:
        pattern = MessagePattern("点名 <user:at> <msg:rest>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "text", "data": {"text": " 你好 世界"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["user"].qq, "123")
        self.assertEqual(result.values["msg"], "你好 世界")

    def test_rest_before_at_consumes_it_by_design(self) -> None:
        pattern = MessagePattern("点名 <msg:rest> [user:at]", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 123}},
                    {"type": "text", "data": {"text": " 你好"}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertTrue(result.matched)
        self.assertEqual(result.values["msg"], "你好")
        self.assertIsNone(result.values["user"])

    def test_at_capture_stops_at_unknown_segment_type(self) -> None:
        pattern = MessagePattern("点名 <user:at>", command=True)
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "face", "data": {"id": 1}},
                    {"type": "at", "data": {"qq": 123}},
                ]
            }
        )

        result = pattern.match(message)

        self.assertFalse(result.matched)
        self.assertIn("missing required at", result.error or "")


if __name__ == "__main__":
    unittest.main()

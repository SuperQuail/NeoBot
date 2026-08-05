from __future__ import annotations

import unittest

from neobot_modloader.message import AtSegment, ImageSegment, Message, MessageChain, MessageSegment, at, image, normalize_message_payload, text


class MessageTest(unittest.TestCase):
    def test_normalizes_message_segments_and_images(self) -> None:
        message = Message(
            {
                "raw_message": "ignored when message is present",
                "message": [
                    {"type": "text", "data": {"text": "识图"}},
                    {"type": "image", "data": {"file": "a.image", "url": "https://example/image.png"}},
                ],
            }
        )

        self.assertEqual(message.text, "识图")
        self.assertTrue(message.has_image)
        self.assertIsInstance(message.first_image, ImageSegment)
        assert message.first_image is not None
        self.assertEqual(message.first_image.file, "a.image")
        self.assertEqual(message.first_image.url, "https://example/image.png")

    def test_falls_back_to_raw_message(self) -> None:
        message = Message({"raw_message": "hello"})

        self.assertEqual(message.text, "hello")
        self.assertEqual(message.to_list(), [{"type": "text", "data": {"text": "hello"}}])

    def test_message_chain_builder_and_payload_normalization(self) -> None:
        chain = MessageChain().text("hello").image(url="https://example/image.png")

        payload = normalize_message_payload(chain)

        self.assertEqual(
            payload,
            [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "image", "data": {"url": "https://example/image.png"}},
            ],
        )
        self.assertEqual(normalize_message_payload(text("x")), [{"type": "text", "data": {"text": "x"}}])
        self.assertEqual(normalize_message_payload(image(file="a.image")), [{"type": "image", "data": {"file": "a.image"}}])

    def test_from_raw_builds_at_segment(self) -> None:
        segment = MessageSegment.from_raw({"type": "at", "data": {"qq": 888}})

        self.assertIsInstance(segment, AtSegment)
        self.assertEqual(segment.qq, "888")

    def test_at_factory_supports_all(self) -> None:
        segment = at(qq="all")

        self.assertIsInstance(segment, AtSegment)
        self.assertTrue(segment.is_all)
        self.assertEqual(segment.qq, "all")

    def test_message_exposes_at_segments(self) -> None:
        message = Message(
            {
                "message": [
                    {"type": "text", "data": {"text": "点名"}},
                    {"type": "at", "data": {"qq": 123, "name": "小明"}},
                    {"type": "at", "data": {"qq": "all"}},
                ]
            }
        )

        self.assertTrue(message.has_at)
        self.assertEqual(len(message.ats), 2)
        assert message.first_at is not None
        self.assertEqual(message.first_at.qq, "123")
        self.assertEqual(message.first_at.name, "小明")
        self.assertTrue(message.ats[1].is_all)

    def test_message_without_at_has_no_at_segments(self) -> None:
        message = Message({"raw_message": "hello"})

        self.assertFalse(message.has_at)
        self.assertIsNone(message.first_at)
        self.assertEqual(message.ats, [])

    def test_message_chain_appends_at_segment(self) -> None:
        chain = MessageChain().text("点名").at(qq="123", name="小明")

        self.assertEqual(
            chain.to_list(),
            [
                {"type": "text", "data": {"text": "点名"}},
                {"type": "at", "data": {"qq": "123", "name": "小明"}},
            ],
        )

    def test_at_send_does_not_require_name(self) -> None:
        chain = MessageChain().at(qq="888")

        self.assertEqual(chain.to_list(), [{"type": "at", "data": {"qq": "888"}}])

    def test_at_accepts_positional_qq(self) -> None:
        chain = MessageChain().at("888")
        segment = at("all")

        self.assertEqual(chain.to_list(), [{"type": "at", "data": {"qq": "888"}}])
        self.assertTrue(segment.is_all)

    def test_at_coerces_int_qq_to_str(self) -> None:
        segment = at(888)

        self.assertEqual(segment.qq, "888")

    def test_at_zero_qq_coerced_to_str(self) -> None:
        segment = at(0)

        self.assertEqual(segment.qq, "0")
        self.assertFalse(segment.is_all)

    def test_at_factory_explicit_args_win_over_data(self) -> None:
        segment = at(qq="1", name="甲", extra="x")

        self.assertEqual(segment.data, {"qq": "1", "name": "甲", "extra": "x"})

    def test_at_factory_accepts_data_only_keys(self) -> None:
        segment = at(**{"qq": "all"})

        self.assertTrue(segment.is_all)
        self.assertEqual(segment.data, {"qq": "all"})

    def test_message_chain_at_preserves_extra_data(self) -> None:
        chain = MessageChain().at(qq="123", extra="x")

        self.assertEqual(chain.to_list(), [{"type": "at", "data": {"qq": "123", "extra": "x"}}])

    def test_from_raw_at_without_data(self) -> None:
        segment = MessageSegment.from_raw({"type": "at"})

        self.assertIsInstance(segment, AtSegment)
        self.assertIsNone(segment.qq)

    def test_from_raw_at_with_non_mapping_data(self) -> None:
        segment = MessageSegment.from_raw({"type": "at", "data": "broken"})

        self.assertIsInstance(segment, AtSegment)
        self.assertEqual(segment.data, {})

    def test_from_raw_at_with_none_data(self) -> None:
        segment = MessageSegment.from_raw({"type": "at", "data": None})

        self.assertIsInstance(segment, AtSegment)
        self.assertEqual(segment.data, {})
        self.assertIsNone(segment.qq)

    def test_from_raw_at_with_nested_data_is_safe(self) -> None:
        segment = MessageSegment.from_raw({"type": "at", "data": {"nested": {"qq": 1}}})

        self.assertIsInstance(segment, AtSegment)
        self.assertEqual(segment.data, {"nested": {"qq": 1}})
        self.assertIsNone(segment.qq)

    def test_at_empty_string_qq_is_not_all(self) -> None:
        segment = at(qq="")

        self.assertEqual(segment.qq, "")
        self.assertFalse(segment.is_all)

    def test_at_empty_name_is_preserved(self) -> None:
        segment = at(name="")

        self.assertEqual(segment.name, "")
        self.assertEqual(segment.data, {"name": ""})

    def test_chain_at_coerces_zero_qq(self) -> None:
        chain = MessageChain().at(0)

        self.assertEqual(chain.to_list(), [{"type": "at", "data": {"qq": "0"}}])

    def test_chain_at_supports_all(self) -> None:
        segment = MessageChain().at(qq="all").segments[0]

        self.assertIsInstance(segment, AtSegment)
        self.assertTrue(segment.is_all)

    def test_chain_at_passes_name_and_extra_data(self) -> None:
        chain = MessageChain().at(qq="1", name="甲", extra="x")

        self.assertEqual(
            chain.to_list(), [{"type": "at", "data": {"qq": "1", "name": "甲", "extra": "x"}}]
        )

    def test_at_factory_key_order_data_then_explicit(self) -> None:
        segment = at(qq="1", name="甲", extra="x")

        self.assertEqual(list(segment.data), ["extra", "qq", "name"])

    def test_at_factory_qq_none_omits_key(self) -> None:
        self.assertEqual(at().data, {})
        self.assertEqual(at(qq=None).data, {})
        self.assertIsNone(at(qq=None).qq)

    def test_at_segment_qq_coerces_all_boundaries(self) -> None:
        self.assertEqual(AtSegment({"qq": 0}).qq, "0")
        self.assertFalse(AtSegment({"qq": 0}).is_all)
        self.assertEqual(AtSegment({"qq": False}).qq, "False")
        self.assertFalse(AtSegment({"qq": False}).is_all)
        self.assertEqual(AtSegment({"qq": ""}).qq, "")
        self.assertFalse(AtSegment({"qq": ""}).is_all)
        self.assertIsNone(AtSegment({"qq": None}).qq)
        self.assertIsNone(AtSegment({}).qq)

    def test_at_segment_qq_str_coerces_mapping_value(self) -> None:
        segment = AtSegment({"qq": {"nested": 1}})

        self.assertIsInstance(segment.qq, str)
        self.assertIn("nested", segment.qq or "")
        self.assertFalse(segment.is_all)

    def test_from_raw_at_zero_qq(self) -> None:
        segment = MessageSegment.from_raw({"type": "at", "data": {"qq": 0}})

        self.assertIsInstance(segment, AtSegment)
        self.assertEqual(segment.qq, "0")
        self.assertFalse(segment.is_all)


if __name__ == "__main__":
    unittest.main()

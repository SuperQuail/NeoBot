from __future__ import annotations

import unittest

from neobot_modloader.message import ImageSegment, Message, MessageChain, image, normalize_message_payload, text


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


if __name__ == "__main__":
    unittest.main()

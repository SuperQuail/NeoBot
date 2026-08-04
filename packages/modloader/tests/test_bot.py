from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from neobot_contracts.models import ConversationRef

from neobot_modloader.bot import Bot


class TestBot(unittest.IsolatedAsyncioTestCase):
    """Bot 包装类的 TDD 测试。"""

    def setUp(self) -> None:
        """为每个测试创建假 adapter 与 Bot 实例。"""
        self.adapter = MagicMock()
        self.adapter.send = AsyncMock()
        self.adapter.send_private_msg = AsyncMock()
        self.adapter.send_group_msg = AsyncMock()
        self.adapter.self_id = 12345

        self.bot = Bot(self.adapter)

    # ── test_bot_send_delegates ─────────────────────────────────────

    async def test_bot_send_delegates(self) -> None:
        """Bot.send 委托给 adapter.send。"""
        conv = ConversationRef(kind="private", id="test_conv")
        msg = {"type": "text", "data": {"text": "hello"}}

        await self.bot.send(conv, msg)

        self.adapter.send.assert_awaited_once_with(conv, msg)

    # ── test_bot_self_id ────────────────────────────────────────────

    def test_bot_self_id(self) -> None:
        """Bot.self_id 返回 adapter.self_id。"""
        self.assertEqual(self.bot.self_id, 12345)

    def test_bot_self_id_none(self) -> None:
        """adapter 无 self_id 时 Bot.self_id 返回 None。"""
        adapter_no_id = MagicMock(spec=[])
        bot_no_id = Bot(adapter_no_id)
        self.assertIsNone(bot_no_id.self_id)

    # ── test_bot_send_private ───────────────────────────────────────

    async def test_bot_send_private(self) -> None:
        """Bot.send_private 委托给 adapter.send_private_msg。"""
        await self.bot.send_private(100, "hi")

        self.adapter.send_private_msg.assert_awaited_once_with(100, "hi")

    # ── test_bot_send_group ─────────────────────────────────────────

    async def test_bot_send_group(self) -> None:
        """Bot.send_group 委托给 adapter.send_group_msg。"""
        await self.bot.send_group(200, "hello")

        self.adapter.send_group_msg.assert_awaited_once_with(200, "hello")

    # ── test_bot_return_value ───────────────────────────────────────

    async def test_bot_send_returns_adapter_result(self) -> None:
        """Bot.send 返回 adapter.send 的结果。"""
        self.adapter.send.return_value = {"message_id": 42}
        conv = ConversationRef(kind="private", id="test_conv")

        result = await self.bot.send(conv, "hello")

        self.assertEqual(result, {"message_id": 42})

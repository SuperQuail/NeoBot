from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from neobot_adapter.model.response import GroupMemberData, StrangerInfoData
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.runtime import PluginRuntime


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeLoggerFactory:
    def get_logger(self, name: str) -> Any:
        return FakeLogger()


class DispatchCtx:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class FakeAgentRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    @property
    def names(self) -> list[str]:
        return list(self.agents)

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        return self.agents.pop(name, None)

    async def delegate(self, agent: str, task: str, context: str = "") -> str:
        result = await self.agents[agent].invoke(
            {
                "messages": [{"role": "user", "content": task}],
                "_delegate_context": context,
            }
        )
        return str(result["messages"][-1]["content"])


class IntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin_dir = Path(self.tmp.name) / "plugins"
        self.data_dir = Path(self.tmp.name) / "data"
        self.plugin_dir.mkdir()
        self.data_dir.mkdir()

        self.mock_adapter = AsyncMock()
        self.hook_bus = PluginHookBus()
        self.agent_registry = FakeAgentRegistry()
        self.runtime = PluginRuntime(
            plugin_dir=self.plugin_dir,
            data_dir=self.data_dir,
            adapter=self.mock_adapter,
            logger_factory=FakeLoggerFactory(),
            hook_bus=self.hook_bus,
            agent_registry=self.agent_registry,
        )

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _write_pkg(self, name: str, init_py: str, manifest: str | None = None) -> None:
        package = self.plugin_dir / name
        package.mkdir()
        if manifest is not None:
            (package / "plugin.toml").write_text(manifest, encoding="utf-8")
        (package / "__init__.py").write_text(init_py, encoding="utf-8")

    async def _dispatch(self, raw_event: dict[str, Any]) -> DispatchCtx:
        ctx = DispatchCtx(raw_event)
        await self.hook_bus.dispatch(ctx)
        return ctx

    async def test_e2e_command_with_image_segment(self) -> None:
        self._write_pkg(
            "vision",
            textwrap.dedent(
                """\
                from neobot_modloader import ImageSegment, Plugin, Reply

                plugin = Plugin("vision")

                @plugin.command("识图 <img:image>")
                async def vision(img: ImageSegment, reply: Reply):
                    await reply.send(img)
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": [
                    {"type": "text", "data": {"text": "/识图"}},
                    {"type": "image", "data": {"url": "https://example/image.png"}},
                ],
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], [{"type": "image", "data": {"url": "https://example/image.png"}}])

    async def test_e2e_command_with_at_segment(self) -> None:
        self._write_pkg(
            "callout",
            textwrap.dedent(
                """\
                from neobot_modloader import AtSegment, Plugin, Reply

                plugin = Plugin("callout")

                @plugin.command("点名 <user:at>")
                async def callout(user: AtSegment, reply: Reply):
                    await reply.send(f"@{user.qq}")
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": [
                    {"type": "text", "data": {"text": "/点名"}},
                    {"type": "at", "data": {"qq": 888, "name": "小明"}},
                ],
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "@888")

    async def test_e2e_non_command_at_segment(self) -> None:
        self._write_pkg(
            "callout2",
            textwrap.dedent(
                """\
                from neobot_modloader import AtSegment, Plugin, Reply

                plugin = Plugin("callout2")

                @plugin.message(pattern="点名 <user:at>")
                async def callout(user: AtSegment, reply: Reply):
                    await reply.send(f"@{user.qq}")
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": [
                    {"type": "text", "data": {"text": "点名"}},
                    {"type": "at", "data": {"qq": 888, "name": "小明"}},
                ],
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "@888")

    async def test_e2e_users_from_event_without_api_calls(self) -> None:
        self._write_pkg(
            "cardname",
            textwrap.dedent(
                """\
                from neobot_modloader import Plugin, Reply

                plugin = Plugin("cardname")

                @plugin.message(text="whoami")
                async def whoami(event, ctx, reply):
                    await reply.send(ctx.users.from_event(event).display_name)
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 10,
                "user_id": 42,
                "raw_message": "whoami",
                "sender": {"user_id": 42, "nickname": "昵称", "card": "群名片"},
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "群名片")
        self.mock_adapter.get_group_member_info.assert_not_called()
        self.mock_adapter.get_group_member_list.assert_not_called()
        self.mock_adapter.get_stranger_info.assert_not_called()

    async def test_e2e_users_display_name_queries_group_member(self) -> None:
        self.mock_adapter.get_group_member_info.return_value = SimpleNamespace(
            data=GroupMemberData(group_id=10, user_id=42, nickname="昵称", card="群名片")
        )
        self._write_pkg(
            "groupname",
            textwrap.dedent(
                """\
                from neobot_modloader import Plugin, Reply

                plugin = Plugin("groupname")

                @plugin.message(text="groupwho")
                async def groupwho(event, ctx, reply):
                    name = await ctx.users.display_name(
                        event["user_id"], group_id=event.get("group_id")
                    )
                    await reply.send(f"你是: {name}")
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 10,
                "user_id": 42,
                "raw_message": "groupwho",
                "sender": {"user_id": 42, "nickname": "昵称"},
            }
        )

        self.mock_adapter.get_group_member_info.assert_called_once_with(10, 42)
        self.mock_adapter.get_stranger_info.assert_not_called()
        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "你是: 群名片")

    async def test_e2e_users_get_many_uses_member_list_with_fallback(self) -> None:
        self.mock_adapter.get_group_member_list.return_value = SimpleNamespace(
            data=[
                GroupMemberData(group_id=10, user_id=1, nickname="甲", card="甲卡"),
                GroupMemberData(group_id=10, user_id=2, nickname="乙", card="乙卡"),
            ]
        )
        self.mock_adapter.get_group_member_info.return_value = SimpleNamespace(data=None)
        self.mock_adapter.get_stranger_info.return_value = SimpleNamespace(
            data=StrangerInfoData(user_id=3, nickname="丙")
        )
        self._write_pkg(
            "multiname",
            textwrap.dedent(
                """\
                from neobot_modloader import Plugin, Reply

                plugin = Plugin("multiname")

                @plugin.message(text="wholist")
                async def wholist(event, ctx, reply):
                    profiles = await ctx.users.get_many(
                        [1, 2, 3], group_id=event.get("group_id")
                    )
                    await reply.send(
                        "/".join(p.display_name for p in profiles.values())
                    )
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 10,
                "user_id": 1,
                "raw_message": "wholist",
                "sender": {"user_id": 1, "nickname": "甲"},
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "甲卡/乙卡/丙")
        self.mock_adapter.get_group_member_list.assert_called_once_with(10)
        # 仅未命中 member list 的 uid 3 走逐人查询 + 陌生人兜底
        self.mock_adapter.get_group_member_info.assert_called_once_with(10, 3)
        self.mock_adapter.get_stranger_info.assert_called_once_with(3)

    async def test_e2e_regex_message_pattern(self) -> None:
        self._write_pkg(
            "regexweather",
            textwrap.dedent(
                """\
                from neobot_modloader import Plugin, Reply

                plugin = Plugin("regexweather")

                @plugin.regex(r"^天气 (?P<city>\\S+)")
                async def weather(city: str, reply: Reply):
                    await reply.send(f"上海{city}的天气")
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "天气 上海",
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "上海上海的天气")

    async def test_e2e_message_regex_filter(self) -> None:
        self._write_pkg(
            "msgregex",
            textwrap.dedent(
                """\
                from neobot_modloader import Plugin, Reply

                plugin = Plugin("msgregex")

                @plugin.message(regex=r"^天气关键词 (.+)$")
                async def keywords(reply: Reply):
                    await reply.send("命中关键词")
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "天气关键词 上海",
            }
        )
        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "raw_message": "随便说点什么",
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], "命中关键词")

    async def test_e2e_config_injection(self) -> None:
        self._write_pkg(
            "ping",
            textwrap.dedent(
                """\
                from pydantic import BaseModel
                from neobot_modloader import Plugin, Reply

                class Config(BaseModel):
                    reply: str

                plugin = Plugin("ping", version="1.0.0", config=Config)

                @plugin.command("ping")
                async def ping(reply: Reply, config: Config):
                    await reply.send(config.reply)
                """
            ),
            manifest='name = "ping"\nversion = "1.0.0"\n[config]\nreply = "pong"\n',
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()
        await self._dispatch({"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "/ping"})

        self.assertEqual(self.mock_adapter.send.call_args.args[1], "pong")

    async def test_e2e_agent_handler_registration(self) -> None:
        self._write_pkg(
            "helper",
            textwrap.dedent(
                """\
                from neobot_modloader import AgentRequest, Plugin

                plugin = Plugin("helper")

                @plugin.agent("echo", description="Echo delegated tasks")
                async def echo(task: str, request: AgentRequest):
                    return f"{request.delegate_context}: {task}"
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()

        self.assertIn("helper.echo", self.agent_registry.agents)
        result = await self.agent_registry.delegate("helper.echo", "hello", context="ctx")

        self.assertEqual(result, "ctx: hello")


if __name__ == "__main__":
    unittest.main()

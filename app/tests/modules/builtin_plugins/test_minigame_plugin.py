"""官方小游戏插件：命令面 / agent 工具 / 意图入口 / 卡片（A19-A35、A37）。

全部走真实 SQLite（临时目录）+ 真实 CommandService，**不联网**：
截图端口用替身捕获 HTML（浏览器缺失环境下同样可跑），
头像用替身注入 data URI（取不到时走首字母色块兜底）。
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.builtin_plugins import minigame
from neobot_app.builtin_plugins.minigame import games as games_pkg
from neobot_app.builtin_plugins.minigame.config import MinigameConfig
from neobot_app.builtin_plugins.minigame.games.checkin import READONLY_NOTICE
from neobot_app.builtin_plugins.minigame.games.fortune import (
    BAD_LUCK_LEVELS,
    FORTUNE_LEVELS,
    level_table,
    pick_level,
)
from neobot_app.commands.model import Command
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService
from neobot_app.runtime.event_context import EventContext
from neobot_app.screenshot import (
    RenderOptions,
    ScreenshotResult,
    ScreenshotUnavailable,
    UnavailableScreenshots,
)
from neobot_contracts.models import ConversationRef
from neobot_modloader.agent_intent import bind_event_context, reset_event_context
from neobot_modloader.context import PluginCommandRegistrar
from neobot_modloader.plugins.tools import PluginToolModule

BOT = 88888
SUB = 30000
USER = 2002
STRANGER = 40000
OTHER = 1001
PNG = b"\x89PNG\r\n\x1a\n" + b"card"
AVATAR_DATA_URI = "data:image/png;base64,AAAB"


# ── 替身 ─────────────────────────────────────────────────────────


class _NullLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None: ...
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...


class FakeServices:
    def __init__(self, mapping: dict[str, Any] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def get(self, name: str, default: Any = None) -> Any:
        return self._mapping.get(name, default)


class FakeHost:
    def __init__(self, services: FakeServices) -> None:
        self.services = services


class FakeScreenshots:
    """捕获 HTML 的截图替身（无需浏览器）。"""

    def __init__(self, *, data: bytes | None = PNG, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[str] = []

    async def render(self, *, html: str, options: RenderOptions, base_url: str | None = None):
        self.calls.append(html)
        if self.error is not None:
            raise self.error
        return ScreenshotResult(self.data or b"", "png", 720, 120, 720.0, 120.0, 1.0)


class FakeAvatarStore:
    """本体 AvatarStore 替身：只读表取值，绝不联网。"""

    def __init__(self, *, ready: bool = True) -> None:
        self.ready = ready
        self.refreshed: list[str] = []

    def get_data_uri(self, user_id: Any) -> str | None:
        return AVATAR_DATA_URI if self.ready else None

    def get_path(self, user_id: Any) -> str | None:
        return f"/avatars/{user_id}.png" if self.ready else None

    async def maybe_refresh(self, user_id: Any) -> bool:
        self.refreshed.append(str(user_id))
        return False


class FakePluginCtx:
    def __init__(
        self,
        *,
        registrar: PluginCommandRegistrar,
        services: FakeServices,
        screenshots: Any = None,
        logger: Any = None,
        config: Any = None,
    ) -> None:
        self.config = config if config is not None else {}
        self.app_commands = registrar
        self.plugin_host = FakeHost(services)
        self.screenshots = screenshots
        self.logger = logger or _NullLogger()
        self.sent_images: list[tuple[Any, bytes | None, str | None]] = []

    def agent_reply(self, background: str = "", *, preactivate: Any = ()) -> bool:
        """与 RuntimePluginContext.agent_reply 同语义（走同一条意图通路）。"""
        from neobot_modloader.agent_intent import request_agent_reply

        return request_agent_reply(background, preactivate=preactivate)

    def conversation_from_event(self, event: dict[str, Any]) -> ConversationRef:
        if event.get("group_id") is not None:
            return ConversationRef(kind="group", id=str(event["group_id"]))
        return ConversationRef(kind="private", id=str(event["user_id"]))

    async def send_image(
        self,
        conversation: ConversationRef,
        *,
        path: Any = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any:
        self.sent_images.append((conversation, data, filename))
        return SimpleNamespace(status="ok")


@dataclass
class FakeClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> None:
        self.value = self.value + timedelta(**kwargs)


class FakeMono:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@dataclass
class Harness:
    plugin: minigame.MinigamePlugin
    ctx: FakePluginCtx
    service: CommandService
    replies: list[str]
    registry: CommandRegistry
    db: Any
    screenshots: Any
    avatars: FakeAvatarStore
    clock: FakeClock
    mono: FakeMono

    async def send(self, text: str, *, user_id: int = USER, name: str = "小明", kind: str = "group", conv: str = "888") -> Any:
        message = make_message(text, user_id=user_id, name=name)
        return await self.service.handle_message(message, kind=kind, queue_key=conv)

    async def sql(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        assert self.plugin.service is not None
        return await self.plugin.service._all(query, params)

    async def tool(self, name: str, args: dict[str, Any]) -> str:
        """走真实工具绑定路径调用 agent 工具（_instance 指向本用例的运行时）。"""
        previous = minigame._instance
        minigame._instance = self.plugin
        try:
            return await call_tool(name, args, self.ctx)
        finally:
            minigame._instance = previous

    async def enter_game(self, game: str, *, user_id: int = USER, name: str = "小明") -> None:
        """模拟关键词入口建立交互上下文（工具通道认人靠它）。"""
        self.plugin.on_keyword(
            None,
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 888,
                "user_id": user_id,
                "sender": {"nickname": name},
                "raw_message": game,
                "message": [{"type": "text", "data": {"text": game}}],
            },
        )

    async def close(self) -> None:
        await self.db.close()


def make_message(text: str, *, user_id: int = USER, name: str = "小明", at_bot: bool = True) -> Any:
    segments: list[dict[str, Any]] = [{"type": "text", "data": {"text": text}}]
    if at_bot:
        segments.append({"type": "at", "data": {"qq": str(BOT)}})
    return SimpleNamespace(
        user_id=user_id,
        message=segments,
        sender=SimpleNamespace(nickname=name, card=""),
    )


def make_config(*, sub_admins: list[int] | None = None) -> Any:
    chat = SimpleNamespace(
        admin_accounts=[99999], sub_admin_accounts=list(sub_admins or [SUB])
    )
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


async def build(
    tmp_path: Path,
    *,
    config: MinigameConfig | None = None,
    screenshots: Any = None,
    avatar_ready: bool = True,
    seed: int = 20260913,
    registry: CommandRegistry | None = None,
    sub_admins: list[int] | None = None,
) -> Harness:
    db = minigame.create_database()
    await db.bind(tmp_path / "databases")
    registry = registry if registry is not None else CommandRegistry()
    registrar = PluginCommandRegistrar(
        plugin_name="minigame",
        registry=registry,
        record_cleanup=None,
        logger=_NullLogger(),
    )
    avatars = FakeAvatarStore(ready=avatar_ready)
    ctx = FakePluginCtx(
        registrar=registrar,
        services=FakeServices({"avatar_store": avatars}),
        screenshots=screenshots,
        config=config if config is not None else {},
    )
    clock = FakeClock(datetime(2026, 9, 13, 10, 0, 0))
    mono = FakeMono()
    plugin = minigame.MinigamePlugin()
    await plugin.load(
        ctx,
        database=db,
        clock=clock,
        rng=random.Random(seed),
        monotonic=mono,
    )
    replies: list[str] = []

    async def send_callback(kind: str, conv_id: str, text: str, at: int | None) -> None:
        replies.append(text)

    service = CommandService(
        config=make_config(sub_admins=sub_admins),
        registry=registry,
        register_builtins=False,
        send_callback=send_callback,
    )
    return Harness(
        plugin=plugin,
        ctx=ctx,
        service=service,
        replies=replies,
        registry=registry,
        db=db,
        screenshots=screenshots,
        avatars=avatars,
        clock=clock,
        mono=mono,
    )


TOOL_PACKAGES = {
    "bottle_write": "bottle",
    "bottle_pick": "bottle",
    "checkin": "checkin",
    "fortune": "fortune",
    "chengyu_submit": "chengyu",
    "points": "base",
    "help": "base",
}


async def call_tool(name: str, args: dict[str, Any], ctx: Any) -> str:
    """按工具包构造 PluginToolModule 并执行工具（走真实绑定路径）。"""
    registrations = [
        registration
        for registration in minigame.plugin._tool_registrations
        if registration.name == name
    ]
    assert registrations, f"工具未注册: {name}"
    module = PluginToolModule(
        minigame.plugin, ctx, registrations=registrations, package=TOOL_PACKAGES[name]
    )
    return await module.execute(name, args)


def scan_unsafe_tags(html: str) -> list[str]:
    """标签级扫描：事件属性 / 危险 URL（用户可控文本永远不该出现在这里）。"""
    bad: list[str] = []
    for tag in re.findall(r"<[^>]*>", html):
        if re.search(r"(?i)\son[a-z]+\s*=", tag):
            bad.append(f"event-attr:{tag}")
        if re.search(r"(?i)(href|src)\s*=\s*\"[^\"]*(javascript|vbscript):", tag):
            bad.append(f"danger-url:{tag}")
    return bad


# ── A19：双通道（格式正确 -> 直接执行并回图；格式错/缺参 -> 交互路径）──


async def test_valid_explicit_command_executes_and_returns_card(tmp_path: Path) -> None:
    """A19：/mg 瓶 丢 <正文> 参数完整 -> 程序执行 + 渲染卡片图（确定性）。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        result = await harness.send("/mg 瓶 丢 今天也要开心")

        assert result.consumed is True
        assert result.background is None
        assert harness.replies == []
        assert len(harness.ctx.sent_images) == 1
        _conversation, data, filename = harness.ctx.sent_images[0]
        assert data == PNG and filename == "bottle.png"
        rows = await harness.sql("SELECT * FROM mg_bottle")
        assert len(rows) == 1 and rows[0]["content"] == "今天也要开心"
    finally:
        await harness.close()


async def test_wrong_format_goes_to_agent_pipeline(tmp_path: Path) -> None:
    """A19：格式错 / 缺参数 -> ctx.sync_reply + 主管线被调用（无固定文案、不写库）。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        result = await harness.send("/mg 瓶 丢")

        assert result.consumed is True
        assert result.background, "必须把结果交给主管线"
        assert "事实" in result.background and "瓶" in result.background
        assert harness.replies == [], "命令层不得发固定文案"
        assert harness.ctx.sent_images == []
        assert screenshots.calls == []
        assert await harness.sql("SELECT * FROM mg_bottle") == []
    finally:
        await harness.close()


async def test_unknown_game_or_natural_language_goes_to_agent(tmp_path: Path) -> None:
    """A19：用户只以自然语言表达意图（/mg 我想玩漂流瓶）-> 交互路径。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.send("/mg 我想玩漂流瓶")

        assert result.background
        assert "自然语言" in result.background or "不是已启用的玩法名" in result.background
        assert harness.replies == []
    finally:
        await harness.close()


async def test_pure_tool_commands_stay_deterministic(tmp_path: Path) -> None:
    """§7：/mg、/mg 积分、/mg rank、/mg help 保持确定性文本输出（不走 agent）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        menu = await harness.send("/mg")
        assert menu.background is None
        assert "可用玩法" in harness.replies[-1] and "漂流瓶" in harness.replies[-1]

        await harness.send("/mg 积分")
        assert harness.replies[-1].startswith("当前积分：")

        await harness.send("/mg rank")
        assert "排行榜" in harness.replies[-1]

        await harness.send("/mg help 瓶")
        assert "漂流瓶" in harness.replies[-1] and "每日上限" in harness.replies[-1]

        # 别名 /游戏 同样可用
        await harness.send("/游戏")
        assert "可用玩法" in harness.replies[-1]
        assert all(background is None for background in [menu.background])
    finally:
        await harness.close()


async def test_rank_bad_page_goes_to_agent(tmp_path: Path) -> None:
    """格式错误（页码非整数）同样必须交 agent，而不是回固定错误文案。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.send("/mg rank abc")
        assert result.background, "页码非法必须走 sync_reply"
        assert harness.replies == []
    finally:
        await harness.close()


# ── A20：关键词 / 意图入口 ────────────────────────────────────────


async def test_keyword_enters_agent_path_without_executing_action(tmp_path: Path) -> None:
    """A20：关键词触发交互路径（agent 主动开场）且**不**执行游戏动作。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        event = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 888,
            "user_id": USER,
            "sender": {"nickname": "小明"},
            "raw_message": "我想玩漂流瓶",
            "message": [{"type": "text", "data": {"text": "我想玩漂流瓶"}}],
        }
        event_ctx = EventContext(raw_event=event)
        token = bind_event_context(event_ctx)
        try:
            guidance = harness.plugin.on_keyword(harness.ctx, event)
        finally:
            reset_event_context(token)

        assert "漂流瓶" in guidance
        # 两个分支都写在引导块里（提出者裁决）
        assert "询问确认" in guidance
        assert "不要**直接执行游戏动作" in guidance
        assert "直接调用" in guidance and "对应工具执行" in guidance
        # 意图已登记，并**按玩法**预激活
        intent = event_ctx.take_agent_reply_intent()
        assert intent is not None
        assert intent["preactivate"] == ("minigame_bottle", "minigame_base")
        assert "minigame__bottle_write" in intent["background"]
        # 不执行任何游戏动作
        assert await harness.sql("SELECT * FROM mg_bottle") == []
        assert harness.ctx.sent_images == []
    finally:
        await harness.close()


async def test_keyword_miss_does_not_trigger(tmp_path: Path) -> None:
    """A20：未命中关键词时不触发（无意向、无动作）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        event = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 888,
            "user_id": USER,
            "raw_message": "今天的天气不错",
            "message": [{"type": "text", "data": {"text": "今天的天气不错"}}],
        }
        event_ctx = EventContext(raw_event=event)
        token = bind_event_context(event_ctx)
        try:
            guidance = harness.plugin.on_keyword(harness.ctx, event)
        finally:
            reset_event_context(token)

        assert guidance == ""
        assert event_ctx.has_agent_reply_intent() is False
        assert harness.plugin._keyword_hits == []
        assert await harness.sql("SELECT * FROM mg_bottle") == []
    finally:
        await harness.close()


async def test_command_message_does_not_trigger_keyword_entry(tmp_path: Path) -> None:
    """命令消息不走关键词入口（/mg 漂流瓶 有自己的命令路径）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        assert harness.plugin.on_keyword(None, {"raw_message": "/mg 漂流瓶"}) == ""
        assert harness.plugin._keyword_hits == []
    finally:
        await harness.close()


async def test_command_intent_preactivates_game_package(tmp_path: Path) -> None:
    """/mg <游戏> 消息只声明预激活（背景仍由命令结果提供）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        event = {"raw_message": "/mg 成语接龙", "message": [{"type": "text", "data": {"text": "/mg 成语接龙"}}]}
        event_ctx = EventContext(raw_event=event)
        token = bind_event_context(event_ctx)
        try:
            harness.plugin.on_command_intent(harness.ctx, event)
        finally:
            reset_event_context(token)

        intent = event_ctx.take_agent_reply_intent()
        assert intent is not None
        assert intent["background"] == ""
        assert intent["preactivate"] == ("minigame_chengyu", "minigame_base")
    finally:
        await harness.close()


# ── A21：每个玩法都有说明与工具 ───────────────────────────────────


def test_every_game_has_description_and_tools() -> None:
    """A21：工具表 + 每个玩法的 agent 说明文本（R15）。"""
    registrations = {item.name: item for item in minigame.plugin._tool_registrations}
    assert set(registrations) == set(TOOL_PACKAGES)
    for registration in registrations.values():
        assert registration.description.strip(), registration.name
        assert registration.package in {"bottle", "chengyu", "checkin", "fortune", "base"}

    configured = set(MinigameConfig().enabled_game_ids)
    for game in minigame.build_games():
        assert game.id in configured
        assert game.describe().strip()
        assert game.summary.strip()
        assert game.help_text().strip()
        assert game.tool_names, f"{game.id} 必须有 agent 可调用工具"
        for tool_name in game.tool_names:
            assert tool_name in registrations

    declared = set(minigame.plugin._tool_packages)
    assert declared == {"bottle", "chengyu", "checkin", "fortune", "base"}
    for game in minigame.build_games():
        assert game.describe() in minigame.plugin._tool_packages[game.id].instructions


def test_tool_package_skill_names_are_stable() -> None:
    """技能包名 = minigame_<玩法>，工具最终名仍是 minigame__<tool>。"""
    assert minigame.skill_name_for("bottle") == "minigame_bottle"
    assert minigame.preactivate_for("bottle") == ("minigame_bottle", "minigame_base")
    assert minigame.preactivate_for("unknown") == ("minigame_base",)
    assert minigame.TOOL_PREFIX == "minigame"


# ── A22：生命周期与重名 ───────────────────────────────────────────


async def test_commands_disappear_after_unregister_all(tmp_path: Path) -> None:
    """A22：停用 / 卸载后 /mg 与 /游戏 均不再注册。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        assert harness.registry.get("mg") is not None
        assert harness.registry.get("游戏") is not None
        command = harness.registry.get("mg")
        assert command is not None and command.source == "minigame"
        assert "[来源: minigame]" in command.help_line

        harness.ctx.app_commands.unregister_all()

        assert harness.registry.get("mg") is None
        assert harness.registry.get("游戏") is None
        result = await harness.send("/mg")
        assert result.consumed is False
    finally:
        await harness.close()


async def test_conflicting_command_is_prefixed(tmp_path: Path) -> None:
    """A22：预置同名命令时自动变 minigame__mg，且来源标记仍是 minigame。"""
    registry = CommandRegistry()

    async def _existing(_ctx: Any) -> str:
        return "本体命令"

    registry.register(Command(name="mg", description="本体已有的 mg", handler=_existing))

    harness = await build(tmp_path, screenshots=FakeScreenshots(), registry=registry)
    try:
        assert registry.get("mg") is not None
        renamed = registry.get("minigame__mg")
        assert renamed is not None and renamed.source == "minigame"
        renames = harness.ctx.app_commands.renames()
        assert ("mg", "minigame__mg") in renames
        result = await harness.send("/minigame__mg")
        assert result.consumed is True
    finally:
        await harness.close()


async def test_tools_are_registered_only_via_plugin_declaration() -> None:
    """A22：工具由插件声明 + 宿主绑定（停用时随技能注销，见 modloader 用例）。"""
    assert minigame.plugin.name == "minigame"
    names = {item.name for item in minigame.plugin._tool_registrations}
    assert "bottle_write" in names and "bottle_pick" in names


# ── A23：普通 vs 匿名卡片 ─────────────────────────────────────────


async def test_normal_card_shows_qq_nickname_and_avatar(tmp_path: Path) -> None:
    """A23：普通发瓶卡片含头像 / 昵称 / QQ / 正文。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 瓶 丢 普通模式的正文")
        html = screenshots.calls[0]

        assert "小明" in html
        assert str(USER) in html
        assert "普通模式的正文" in html
        assert 'class="mg-avatar"' in html and AVATAR_DATA_URI in html
        assert "QQ 号、昵称与头像会随瓶子一起展示" in html
    finally:
        await harness.close()


async def test_anonymous_card_hides_qq_and_nickname_but_keeps_avatar(tmp_path: Path) -> None:
    """A23：匿名卡片不出现 QQ 与真实昵称、显示「神秘的人」、头像仍然渲染。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 瓶 匿名 匿名模式的正文")
        html = screenshots.calls[0]

        assert "神秘的人" in html
        assert str(USER) not in html
        assert "小明" not in html
        assert "匿名模式的正文" in html
        assert 'class="mg-avatar"' in html and AVATAR_DATA_URI in html
        assert "只显示头像与「神秘的人」" in html
    finally:
        await harness.close()


async def test_avatar_fallback_initial_block_still_renders(tmp_path: Path) -> None:
    """A36（头像部分）：取不到 data URI 时用首字母色块兜底，仍然出图。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots, avatar_ready=False)
    try:
        await harness.send("/mg 瓶 丢 没有头像也要出图")
        html = screenshots.calls[0]

        assert "mg-avatar-fallback" in html
        assert AVATAR_DATA_URI not in html
        assert "小" in html  # 昵称首字母
    finally:
        await harness.close()


# ── A24 / A27：每日上限（两模式共用）与无冷却 ─────────────────────


async def test_send_limit_is_shared_between_modes(tmp_path: Path) -> None:
    """A24：匿名 3 次 + 普通 2 次后，第 6 次（任一模式）被拒且不写库。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        for index in range(3):
            result = await harness.send(f"/mg 瓶 匿名 匿名第 {index} 条")
            assert result.background is None
        for index in range(2):
            result = await harness.send(f"/mg 瓶 丢 普通第 {index} 条")
            assert result.background is None
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 5

        rejected = await harness.send("/mg 瓶 匿名 第六条")
        assert rejected.background, "超限必须交 agent 说明，而不是回固定文案"
        assert "每日上限" in rejected.background
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 5

        rejected_normal = await harness.send("/mg 瓶 丢 第六条普通")
        assert rejected_normal.background
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 5
        daily = await harness.sql(
            "SELECT plays FROM mg_daily WHERE game_id = 'bottle:send' AND user_id = :uid",
            {"uid": str(USER)},
        )
        assert daily[0]["plays"] == 5, "第 6 次不得写库"
    finally:
        await harness.close()


async def test_pick_limit_and_no_cooldown(tmp_path: Path) -> None:
    """A27：第 6 次捞瓶被拒且不写库；未达上限时连续捞取均被允许（无冷却）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        for index in range(6):
            await harness.plugin.service.add_bottle(
                sender_id=f"90{index:02d}",
                sender_name=f"发送者{index}",
                sender_avatar="",
                content=f"第 {index} 个瓶子",
                anonymous=False,
            )

        for index in range(5):
            result = await harness.send("/mg 瓶 捞")
            assert result.background is None, f"第 {index + 1} 次捞取应当成功"
            assert len(harness.ctx.sent_images) == index + 1

        rejected = await harness.send("/mg 瓶 捞")
        assert rejected.background and "每日上限" in rejected.background
        assert len(harness.ctx.sent_images) == 5
        daily = await harness.sql(
            "SELECT plays FROM mg_daily WHERE game_id = 'bottle:pick' AND user_id = :uid",
            {"uid": str(USER)},
        )
        assert daily[0]["plays"] == 5
    finally:
        await harness.close()


# ── A28：捞瓶排除与回落 ──────────────────────────────────────────


async def test_pick_excludes_self_and_falls_back_with_hint(tmp_path: Path) -> None:
    """A28：排除自己；因排除而无瓶时回落普通随机并在卡片里提示。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        # 自己的瓶 + 同一发送者的两个瓶
        await harness.plugin.service.add_bottle(
            sender_id=str(USER), sender_name="自己", sender_avatar="",
            content="我自己的瓶子", anonymous=False,
        )
        await harness.plugin.service.add_bottle(
            sender_id="1001", sender_name="甲", sender_avatar="",
            content="甲的第一瓶", anonymous=False,
        )
        await harness.plugin.service.add_bottle(
            sender_id="1001", sender_name="甲", sender_avatar="",
            content="甲的第二瓶", anonymous=False,
        )

        first = await harness.send("/mg 瓶 捞")
        assert first.background is None
        html_first = screenshots.calls[-1]
        assert "我自己的瓶子" not in html_first

        # 现在池里只剩同一发送者的瓶；它已在最近 3 次排除名单里 -> 回落普通随机 + 提示
        second = await harness.send("/mg 瓶 捞")
        assert second.background is None
        html_second = screenshots.calls[-1]
        assert "回落普通随机" in html_second
    finally:
        await harness.close()


async def test_empty_pool_goes_to_agent(tmp_path: Path) -> None:
    """空池：交 agent 说明（不回固定文案，也不写库）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.send("/mg 瓶 捞")
        assert result.background and "池" in result.background
        assert harness.replies == []
        assert len(harness.ctx.sent_images) == 0
    finally:
        await harness.close()


# ── A29：正文长度 / 纯链接 / Markdown / 注入 ──────────────────────


async def test_content_length_boundary(tmp_path: Path) -> None:
    """A29：500 字通过、501 字被拒（且不写库）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        ok = await harness.send("/mg 瓶 丢 " + "字" * 500)
        assert ok.background is None
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 1

        too_long = await harness.send("/mg 瓶 丢 " + "字" * 501)
        assert too_long.background and "501" in too_long.background
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 1
    finally:
        await harness.close()


async def test_pure_link_is_rejected(tmp_path: Path) -> None:
    """A29：纯链接被拒（分隔后每段都是 URL 形态）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        rejected = await harness.send("/mg 瓶 丢 https://example.com/a https://example.com/b")
        assert rejected.background and "纯链接" in rejected.background
        assert await harness.sql("SELECT * FROM mg_bottle") == []

        mixed = await harness.send("/mg 瓶 丢 看看这个 https://example.com/a")
        assert mixed.background is None, "链接 + 人话应当允许"
        assert len(await harness.sql("SELECT * FROM mg_bottle")) == 1
    finally:
        await harness.close()


def test_markdown_fragment_renders_lists_and_code_blocks() -> None:
    """A29：Markdown 生效（粗体 / 列表 / 代码块都渲染成对应标签）。

    命令文本由本体解析器按「单行命令」处理（换行会截断参数），因此多行语法
    直接在本插件自己的渲染入口上断言——这正是卡片里注入的那份 HTML。
    """
    fragment = games_pkg.render_markdown_fragment(
        "**粗体**\n\n- 甲\n- 乙\n\n```py\nx = 1\n```"
    )

    assert "<strong>" in fragment and "粗体" in fragment
    assert "<ul>" in fragment and "<li>" in fragment
    assert "<pre>" in fragment and "<code" in fragment
    assert games_pkg.error_html_scan(fragment) is False


async def test_markdown_is_rendered_in_card(tmp_path: Path) -> None:
    """A29：单行 Markdown（粗体 / 行内代码）出现在卡片 HTML 里。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 瓶 丢 **粗体** 与 `行内代码`")
        html = screenshots.calls[0]

        assert "<strong>粗体</strong>" in html
        assert "<code>行内代码</code>" in html
        assert games_pkg.error_html_scan(html) is False
    finally:
        await harness.close()


async def test_user_html_is_escaped_and_urls_sanitized(tmp_path: Path) -> None:
    """A29：正文含 <script>/<img onerror>/javascript: 时卡片 HTML 无用户可控标签与事件属性。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        payload = "<script>alert(1)</script> <img src=x onerror=alert(1)> [点我](javascript:alert(1))"
        await harness.send("/mg 瓶 丢 " + payload)
        html = screenshots.calls[0]

        assert "<script" not in html.lower()
        assert scan_unsafe_tags(html) == []
        assert "javascript:" not in html
        assert "&lt;script&gt;" in html, "原始 HTML 必须变成字面文本"
        # 用户输入没有带进任何标签/属性
        tag_text = chr(10).join(re.findall(r"<[^>]*>", html))
        assert "onerror=alert(1)" not in tag_text
    finally:
        await harness.close()


# ── A30：可见范围告知与「不可查询」 ───────────────────────────────


async def test_write_reply_states_visibility_per_mode(tmp_path: Path) -> None:
    """A30：发瓶回复按模式写明可见范围与「发出后不可查询、不可撤回」。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        await harness.send("/mg 瓶 丢 普通")
        normal = screenshots.calls[-1]
        assert "可见范围" in normal
        assert "QQ 号、昵称与头像会随瓶子一起展示" in normal
        assert "发出后不可查询、不可撤回" in normal

        await harness.send("/mg 瓶 匿名 匿名")
        anonymous = screenshots.calls[-1]
        assert "可见范围" in anonymous
        assert "只显示头像与「神秘的人」" in anonymous
        assert "发出后不可查询、不可撤回" in anonymous
    finally:
        await harness.close()


async def test_bottle_help_states_both_modes_and_no_lookup(tmp_path: Path) -> None:
    """A30：/mg 瓶 帮助 按模式写明可见范围与「不可查询、不可撤回」。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.send("/mg 瓶 帮助")
        help_text = harness.replies[-1]

        assert "普通模式" in help_text and "匿名模式" in help_text
        assert "QQ 号、昵称与头像会随瓶子一起展示" in help_text
        assert "只显示头像与「神秘的人」" in help_text
        assert "发出后不可查询、不可撤回" in help_text
    finally:
        await harness.close()


async def test_no_bottle_lookup_entry_points(tmp_path: Path) -> None:
    """A30：不存在任何查询入口（命令表 / 工具表断言）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        command_names = {command.name for command in harness.registry.commands()}
        assert command_names == {"mg"}
        assert harness.registry.get("游戏") is not None, "别名 /游戏 必须注册"
        tool_names = {item.name for item in minigame.plugin._tool_registrations}
        assert not [name for name in tool_names if "mine" in name or "list" in name]
        assert tool_names == set(TOOL_PACKAGES)

        for text in ("/mg 瓶 我的", "/mg 瓶 列表", "/mg 瓶 查询"):
            result = await harness.send(text)
            assert result.background, "没有查询入口：这类输入一律走 agent 追问"
            assert "bottle_mine" not in result.background
    finally:
        await harness.close()


# ── A31：成语接龙（目标 N / 任意字符串 / 10 步 / 60 秒）────────────


async def test_chengyu_target_is_in_range(tmp_path: Path) -> None:
    """A31：目标 N ∈ [3,10]（可配置）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        game = harness.plugin.game_by_id("chengyu")
        assert game is not None
        targets: list[int] = []
        for seed in range(40):
            harness.plugin._rng = random.Random(seed)
            request = harness.plugin.command_request(
                None, user_id=USER, user_name="小明", kind="group", conversation_id="888"
            )
            session = game.start_session(request)
            targets.append(session.target)
            harness.plugin.chengyu_sessions.clear()
        assert all(3 <= target <= 10 for target in targets)
        assert len(set(targets)) > 1
    finally:
        await harness.close()


async def test_chengyu_target_respects_config(tmp_path: Path) -> None:
    """目标区间可配。"""
    config = MinigameConfig(chengyu_target_min=7, chengyu_target_max=7)
    harness = await build(tmp_path, screenshots=FakeScreenshots(), config=config)
    try:
        game = harness.plugin.game_by_id("chengyu")
        assert game is not None
        request = harness.plugin.command_request(
            None, user_id=USER, user_name="小明", kind="group", conversation_id="888"
        )
        assert game.start_session(request).target == 7
    finally:
        await harness.close()


async def test_chengyu_start_goes_to_agent_with_target(tmp_path: Path) -> None:
    """A31：开始一局由程序给 N，并交 agent 开场（程序不发固定文案）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.send("/mg 成语接龙")
        assert result.background and "目标" in result.background
        assert harness.replies == []
        session = harness.plugin.chengyu_sessions.get("888")
        assert session is not None and 3 <= session.target <= 10
        assert f"目标 {session.target} 条" in result.background
    finally:
        await harness.close()


async def test_chengyu_submit_accepts_any_string(tmp_path: Path) -> None:
    """A31：submit 对任意字符串都接受（不校验内容），只记账 + 计步。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.send("/mg 成语接龙")
        await harness.enter_game("成语接龙")

        first = await harness.tool("chengyu_submit", {"word": "!!!"})
        assert "已记录" in first and "第 1/" in first
        second = await harness.tool("chengyu_submit", {"word": "  "})
        assert "第 2/" in second

        records = await harness.sql("SELECT * FROM mg_record WHERE game_id = 'chengyu'")
        assert len(records) == 2
        assert all(row["score"] == 1 for row in records)
        assert await harness.plugin.service.points(USER) == 2
    finally:
        await harness.close()


async def test_chengyu_max_steps_ends_session(tmp_path: Path) -> None:
    """A31：单局最多 N 步（用满即结束本局）。"""
    config = MinigameConfig(chengyu_max_steps=3, chengyu_target_min=10, chengyu_target_max=10)
    harness = await build(tmp_path, screenshots=FakeScreenshots(), config=config)
    try:
        await harness.send("/mg 成语接龙")
        await harness.enter_game("成语接龙")

        results = [
            await harness.tool("chengyu_submit", {"word": f"词{index}"}) for index in range(3)
        ]
        assert "已用满" in results[-1] or "已经用满" in results[-1]
        assert harness.plugin.chengyu_sessions == {}
        assert harness.plugin._closed_sessions[-1]["reason"] == "steps_exhausted"
        # 未达成目标不扣分：3 步各 +1
        assert await harness.plugin.service.points(USER) == 3
    finally:
        await harness.close()


async def test_chengyu_step_timeout_ends_session(tmp_path: Path) -> None:
    """A31：每条 60 秒，超时后本局结束（不扣分）。"""
    config = MinigameConfig(chengyu_step_timeout_seconds=60)
    harness = await build(tmp_path, screenshots=FakeScreenshots(), config=config)
    try:
        await harness.send("/mg 成语接龙")
        await harness.enter_game("成语接龙")
        await harness.tool("chengyu_submit", {"word": "一见钟情"})
        assert await harness.plugin.service.points(USER) == 1

        harness.mono.advance(61)
        expired = await harness.tool("chengyu_submit", {"word": "情投意合"})
        assert "没有进行中" in expired
        assert harness.plugin.chengyu_sessions == {}
        assert harness.plugin._closed_sessions[-1]["reason"] == "timeout"
        assert await harness.plugin.service.points(USER) == 1, "超时不得扣分，也不得计新分"
    finally:
        await harness.close()


async def test_chengyu_reaching_target_adds_bonus(tmp_path: Path) -> None:
    """A31：达成目标 N 额外 +N，并结束本局。"""
    config = MinigameConfig(chengyu_target_min=3, chengyu_target_max=3)
    harness = await build(tmp_path, screenshots=FakeScreenshots(), config=config)
    try:
        await harness.send("/mg 成语接龙")
        await harness.enter_game("成语接龙")

        last = ""
        for index in range(3):
            last = await harness.tool("chengyu_submit", {"word": f"成语{index}"})
        assert "达成目标" in last and "额外 +3" in last
        assert harness.plugin.chengyu_sessions == {}
        assert await harness.plugin.service.points(USER) == 6
    finally:
        await harness.close()


async def test_chengyu_submit_without_session_is_guided(tmp_path: Path) -> None:
    """没有进行中的一局时，工具返回引导而不是报错。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.enter_game("成语接龙")
        result = await harness.tool("chengyu_submit", {"word": "无中生有"})
        assert "没有进行中" in result
    finally:
        await harness.close()


async def test_stop_command_permission(tmp_path: Path) -> None:
    """/mg stop：发起者或次级管理员；其它人只得到一句确定性说明。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.send("/mg 成语接龙", user_id=USER)
        assert "888" in harness.plugin.chengyu_sessions

        await harness.send("/mg stop", user_id=STRANGER)
        assert "发起者" in harness.replies[-1]
        assert "888" in harness.plugin.chengyu_sessions

        await harness.send("/mg stop", user_id=USER)
        assert "已结束" in harness.replies[-1]
        assert harness.plugin.chengyu_sessions == {}

        await harness.send("/mg 成语接龙", user_id=USER)
        await harness.send("/mg stop", user_id=SUB)
        assert "已结束" in harness.replies[-1]

        # 没有进行中的一局时也是确定性输出
        await harness.send("/mg stop", user_id=USER)
        assert "没有进行中" in harness.replies[-1]
    finally:
        await harness.close()


# ── A32 / A33 / A34：签到、无提醒、只读积分 ───────────────────────


async def test_checkin_goes_to_agent_and_is_idempotent(tmp_path: Path) -> None:
    """A32：签到交 agent 组织文案；同日重复签到不加分并告知既有结果。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        first = await harness.send("/mg 签到")
        assert first.background and "签到成功" in first.background
        assert harness.replies == [], "程序不发固定文案"
        assert len(harness.ctx.sent_images) == 1, "签到仍然出图"
        rows = await harness.sql("SELECT * FROM mg_checkin")
        assert len(rows) == 1
        score = int(rows[0]["score"])
        assert 1 <= score <= 10
        assert await harness.plugin.service.points(USER) == score

        second = await harness.send("/mg 签到")
        assert second.background and "已经签过" in second.background
        assert await harness.plugin.service.points(USER) == score, "重复签到不加分"
        assert len(await harness.sql("SELECT * FROM mg_checkin")) == 1
    finally:
        await harness.close()


async def test_checkin_tool_channel(tmp_path: Path) -> None:
    """agent 工具通道：minigame__checkin 返回事实文本（供模型转述）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.enter_game("签到")
        result = await harness.tool("checkin", {})
        assert "签到" in result and "积分" in result
        again = await harness.tool("checkin", {})
        assert "今天已经签过" in again or "已经签过" in again
    finally:
        await harness.close()


def test_no_proactive_reminder_path() -> None:
    """A33：不存在任何主动提醒 / 定时路径，也没有补签入口。"""
    assert minigame.plugin._startup_handlers == [], "不得注册启动期定时任务"
    root = Path(minigame.__file__).parent
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(root.rglob("*.py"))
    )
    for token in (
        "create_task",
        "call_later",
        "scheduled_task",
        "add_job",
        "IntervalTrigger",
        "asyncio.sleep",
    ):
        assert token not in source, f"不该出现定时 / 提醒相关代码: {token}"

    names = {item.name for item in minigame.plugin._tool_registrations}
    assert not [name for name in names if "remind" in name or "补签" in name]
    assert not [name for name in names if "makeup" in name]


async def test_points_are_read_only(tmp_path: Path) -> None:
    """A34：积分只有只读入口（/mg 积分 与 minigame__points），没有加/扣/兑换。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.send("/mg 积分")
        assert result.background is None
        assert READONLY_NOTICE in harness.replies[-1]

        await harness.enter_game("签到")
        tool_text = await harness.tool("points", {})
        assert READONLY_NOTICE in tool_text
        assert "当前积分" in tool_text

        tool_names = {item.name for item in minigame.plugin._tool_registrations}
        assert tool_names == set(TOOL_PACKAGES)
        for forbidden in ("add", "deduct", "spend", "exchange", "redeem", "buy"):
            assert not [name for name in tool_names if forbidden in name]
        command_names = {command.name for command in harness.registry.commands()}
        assert command_names == {"mg"}
    finally:
        await harness.close()


# ── A35：抽签 ─────────────────────────────────────────────────────


async def test_fortune_once_per_day_and_resends_same_result(tmp_path: Path) -> None:
    """A35：当日首次落库 + 出图；同日再请求不重抽但可重发同一张图；不产生积分。"""
    screenshots = FakeScreenshots()
    harness = await build(tmp_path, screenshots=screenshots)
    try:
        first = await harness.send("/mg 抽签")
        assert first.background and "运势" in first.background
        assert len(harness.ctx.sent_images) == 1
        html_first = screenshots.calls[0]

        second = await harness.send("/mg 抽签")
        assert second.background and "已经抽过" in second.background
        assert len(harness.ctx.sent_images) == 2
        assert screenshots.calls[1] == html_first, "必须重发同一结果的图"

        rows = await harness.sql("SELECT * FROM mg_fortune")
        assert len(rows) == 1
        assert await harness.plugin.service.points(USER) == 0, "抽签不附带积分"

        harness.clock.advance(days=1)
        await harness.send("/mg 抽签")
        assert len(await harness.sql("SELECT * FROM mg_fortune")) == 2
        assert len(harness.ctx.sent_images) == 3
    finally:
        await harness.close()


def test_fortune_levels_five_by_default_seven_with_bad_luck() -> None:
    """A35：默认五档不含凶；fortune_include_bad_luck=true 时七档。"""
    bad_keys = {level.key for level in BAD_LUCK_LEVELS}
    assert len(level_table(include_bad_luck=False)) == 5
    assert len(level_table(include_bad_luck=True)) == 7

    default_keys = {level.key for level in FORTUNE_LEVELS}
    assert not (default_keys & bad_keys)

    default_rng = random.Random(7)
    seen_default = {
        pick_level(default_rng, include_bad_luck=False).key for _ in range(2000)
    }
    assert seen_default == default_keys
    bad_rng = random.Random(7)
    seen_bad = {pick_level(bad_rng, include_bad_luck=True).key for _ in range(2000)}
    assert seen_bad == default_keys | bad_keys


async def test_fortune_bad_luck_config_reaches_seven_levels(tmp_path: Path) -> None:
    """fortune_include_bad_luck=true 时七档都可能出现（配置项生效）。"""
    harness = await build(
        tmp_path,
        screenshots=FakeScreenshots(),
        config=MinigameConfig(fortune_include_bad_luck=True),
    )
    try:
        game = harness.plugin.game_by_id("fortune")
        assert game is not None
        assert len(level_table(include_bad_luck=harness.plugin.config.fortune_include_bad_luck)) == 7
    finally:
        await harness.close()


# ── 降级与工具通道 ────────────────────────────────────────────────


async def test_render_unavailable_degrades_to_equivalent_text(tmp_path: Path) -> None:
    """渲染不可用（无浏览器）时回等价纯文本，命令不报错、用户一定有反馈。"""
    harness = await build(tmp_path, screenshots=UnavailableScreenshots())
    try:
        result = await harness.send("/mg 瓶 丢 降级也要有反馈")

        assert result.consumed is True
        assert result.background is None
        assert harness.ctx.sent_images == []
        assert harness.replies, "必须有文本降级"
        text = harness.replies[0]
        assert "漂流瓶已投出" in text
        assert "不可查询、不可撤回" in text
    finally:
        await harness.close()


async def test_render_exception_degrades_without_crash(tmp_path: Path) -> None:
    """渲染抛异常同样降级（绝不冒泡到命令层）。"""
    harness = await build(
        tmp_path, screenshots=FakeScreenshots(error=ScreenshotUnavailable("no chromium"))
    )
    try:
        result = await harness.send("/mg 瓶 丢 异常也要降级")
        assert result.background is None
        assert harness.replies and "漂流瓶已投出" in harness.replies[0]
    finally:
        await harness.close()


async def test_tool_channel_writes_and_returns_text(tmp_path: Path) -> None:
    """agent 工具通道：写作 / 捞取 / 抽签都返回给模型看的文本（不出图）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.enter_game("漂流瓶")
        written = await harness.tool("bottle_write", {"content": "来自工具通道", "anonymous": True})
        assert "神秘的人" in written or "匿名" in written
        assert "不可查询" in written
        rows = await harness.sql("SELECT * FROM mg_bottle")
        assert len(rows) == 1 and rows[0]["anonymous"] in (1, True)

        picked = await harness.tool("bottle_pick", {})
        assert "池" in picked, "自己的瓶被排除 => 空池提示"

        fortune = await harness.tool("fortune", {})
        assert "运势" in fortune
        help_text = await harness.tool("help", {"game": "bottle"})
        assert "漂流瓶" in help_text and "每日上限" in help_text
        assert harness.ctx.sent_images == [], "工具通道不出图"
    finally:
        await harness.close()


async def test_tool_without_identity_is_guided(tmp_path: Path) -> None:
    """工具没有入站事件：认不出用户时给出引导，而不是报错。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        result = await harness.tool("points", {})
        assert "无法确定是哪个用户" in result
    finally:
        await harness.close()


def test_plugin_manifest_matches_config_defaults() -> None:
    """工程契约：plugin.toml 的元数据与 [config] 默认值必须与配置模型一致。"""
    import tomllib

    manifest_path = Path(minigame.__file__).parent / "plugin.toml"
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["name"] == "minigame"
    assert manifest["version"] == "1.0.0"
    assert manifest["author"] == "NeoBot"
    assert manifest.get("tags") == ["official", "game"]
    assert manifest.get("hot_reload") is True
    assert manifest.get("config_hot_reload") is True
    assert manifest.get("dependencies", []) == [], "不依赖 dashboard"

    defaults = MinigameConfig().model_dump()
    table = manifest["config"]
    assert set(table) == set(defaults), "plugin.toml 与配置模型的键集合必须一致"
    for key, value in table.items():
        assert value == defaults[key], f"{key} 默认值不一致: {value!r} != {defaults[key]!r}"


def test_config_rejects_invalid_values() -> None:
    """配置校验：区间写反 / 未知玩法名都要被挡下或纠正。"""
    with pytest.raises(Exception):
        MinigameConfig(chengyu_target_min=9, chengyu_target_max=3)
    with pytest.raises(Exception):
        MinigameConfig(checkin_score_min=9, checkin_score_max=3)
    config = MinigameConfig(enabled_games=["bottle", "bottle", "  ", "nope"])
    assert config.enabled_games == ["bottle"]


async def test_tool_write_rejects_invalid_content_like_command(tmp_path: Path) -> None:
    """工具通道与命令通道共用同一套校验（501 字 / 纯链接都被拒且不写库）。"""
    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        await harness.enter_game("漂流瓶")
        too_long = await harness.tool("bottle_write", {"content": "字" * 501})
        assert "501" in too_long
        link = await harness.tool("bottle_write", {"content": "https://example.com/only"})
        assert "纯链接" in link
        assert await harness.sql("SELECT * FROM mg_bottle") == []
    finally:
        await harness.close()

# ── 玩法关键词 -> 跳过本体的 @ 提及等待 ───────────────────────────


async def test_load_registers_game_keywords_for_instant_reply(tmp_path: Path) -> None:
    """load 时把启用玩法的关键词登记进本体；unload 后按 owner 注销干净。"""
    from neobot_app.message import fast_reply_keywords

    harness = await build(tmp_path, screenshots=FakeScreenshots())
    try:
        registered = fast_reply_keywords.reply_trigger_keywords()
        assert "minigame" in registered
        assert set(registered["minigame"]) == set(minigame.KEYWORDS)
        assert fast_reply_keywords.match_reply_trigger_keyword("帮我签到一下") == "签到"
        assert (
            fast_reply_keywords.match_reply_trigger_keyword("想看看今日运势")
            == "今日运势"
        )

        await harness.plugin.unload()

        assert "minigame" not in fast_reply_keywords.reply_trigger_keywords()
        assert fast_reply_keywords.match_reply_trigger_keyword("帮我签到一下") == ""
    finally:
        await harness.close()


async def test_only_enabled_games_register_keywords(tmp_path: Path) -> None:
    """玩法下线后，它的关键词不再影响本体的 @ 提及行为。"""
    from neobot_app.message import fast_reply_keywords

    harness = await build(
        tmp_path,
        config=MinigameConfig(enabled_games=["bottle"]),
        screenshots=FakeScreenshots(),
    )
    try:
        registered = fast_reply_keywords.reply_trigger_keywords()["minigame"]
        assert set(registered) == {"漂流瓶", "丢瓶子", "捞瓶子"}
        assert fast_reply_keywords.match_reply_trigger_keyword("签到") == ""
        assert fast_reply_keywords.match_reply_trigger_keyword("丢瓶子") == "丢瓶子"
    finally:
        await harness.close()






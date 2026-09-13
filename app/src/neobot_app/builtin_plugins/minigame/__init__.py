"""NeoBot 官方小游戏插件（spec(5) §1.4-§1.8、§4.4-§4.8 / R12-R32）。

核心思路（R12）：**不对游戏的逻辑路径做约束**。程序只提供必须持久化 / 必须
限流的能力 —— 数据表、随机结果、每日上限、计分记账、头像、渲染；玩法与判定
按需调用模型，突出 AI 交互互动，而不是把规则写死在程序里。

两条入口（R15）：

1. **命令入口**：/mg（别名 /游戏）—— 格式完全正确时直接执行并回图；格式错误、
   缺参数、或用户只以自然语言表达意图时置 ctx.sync_reply = True，把「事实 +
   提示词」交给主管线，由模型组织回复（与 /sleep 同一机制，不新造管线）。
2. **agent 入口**：插件工具 `minigame__bottle_write` 等（框架自动加
   {plugin}__ 前缀）与本模块给模型看的说明文本。

另有**关键词 / 意图入口**（R14 / D11）：插件消息处理器承接「漂流瓶」「签到」
「抽签」等关键词，进入 agent 交互路径（agent 主动开场），**不直接执行游戏动作**；
未命中关键词时完全不触发。

停用 / 卸载时命令随 ctx.app_commands.unregister_all() 摘除、工具由宿主随
插件技能注销；与本体或其它插件重名时按 spec(4) D21 自动变 minigame__<name>。
"""

from __future__ import annotations

import random
import re
import time
from typing import Any

from neobot_app.message.fast_reply_keywords import (
    register_reply_trigger_keywords,
    unregister_reply_trigger_keywords,
)
from neobot_modloader import Plugin, PluginDatabase
from neobot_modloader.message import Message

from .avatars import AvatarProvider
from .config import ALL_GAME_IDS, MinigameConfig
from .games import Game, GameRequest, build_games, find_game
from .games.checkin import format_points_text
from .migrations import DATABASE_FILENAME, build_migrations
from .models import Base
from .service import MinigameService
from .themes import (
    register_minigame_themes,
    resolve_theme,
    unregister_minigame_themes,
)

#: 最终工具名的前缀：框架按 {plugin}__{tool} 生成（插件名 = minigame）
TOOL_PREFIX = "minigame"

#: 关键词 -> 玩法 id（D11：插件消息处理器承接，不改造本体启动期关键词快照）
KEYWORDS: dict[str, str] = {
    "漂流瓶": "bottle",
    "丢瓶子": "bottle",
    "捞瓶子": "bottle",
    "成语接龙": "chengyu",
    "接龙": "chengyu",
    "签到": "checkin",
    "打卡": "checkin",
    "抽签": "fortune",
    "今日运势": "fortune",
    "运势": "fortune",
}

#: 交互上下文的有效期（秒）：工具通道没有入站事件，只能靠最近一次交互认人
INTERACTION_TTL_SECONDS = 300.0

#: 排行榜每页条数
RANK_PAGE_SIZE = 10

MENU_FOOTER = (
    "其他：/mg rank [页码] 排行榜 · /mg 积分 查积分 · /mg help <游戏> 规则 · "
    "/mg stop 结束当前会话局\n"
    "也可以直接对我说话（例如「我想玩漂流瓶」「签到」「抽签」），由我陪你玩。"
)


plugin = Plugin(
    "minigame",
    version="1.0.0",
    description="NeoBot 官方小游戏：漂流瓶 / 成语接龙 / 签到与积分 / 抽签（AI 交互型）",
    author="NeoBot",
    config=MinigameConfig,
    dependencies=(),
    hot_reload=True,
    config_hot_reload=True,
)


def create_database(filename: str = DATABASE_FILENAME) -> PluginDatabase:
    """构造本插件的独立数据库对象（测试可用它建临时库，与下面的注册实例互不影响）。"""
    return PluginDatabase(
        "minigame",
        "main",
        filename=filename,
        metadata=Base.metadata,
        migrations=build_migrations(),
    )


#: 插件独立库（plugins_data/minigame/databases/minigame.db），随插件加载自动 bind + 迁移
database = plugin.sqlite_database(
    "main",
    filename=DATABASE_FILENAME,
    metadata=Base.metadata,
    migrations=build_migrations(),
)


#: 通用工具（规则查询 / 积分查询）所在的工具包名
PACKAGE_BASE = "base"


def skill_name_for(package: str) -> str:
    """工具包对应的技能名（SkillManager 里的名字，可与 skills__load_tools 一起用）。"""
    return f"{plugin.name}_{package}"


def preactivate_for(game_id: str) -> tuple[str, ...]:
    """某个玩法要预激活的技能包：玩法包 + 通用包。"""
    packages: list[str] = []
    if str(game_id) in ALL_GAME_IDS:
        packages.append(str(game_id))
    packages.append(PACKAGE_BASE)
    return tuple(skill_name_for(item) for item in packages)


def _declare_tool_packages() -> None:
    """声明工具包：description 进技能索引，instructions 是给模型看的玩法说明（R15）。

    一个插件拆成多个**可独立加载**的技能包（minigame_bottle 等），工具最终名仍是
    minigame__<tool>；命中某个玩法时可以只预激活那个包，而不是整套工具。
    """
    for game in build_games():
        plugin.tool_package(
            game.id,
            description=f"{game.name}：{game.summary}",
            instructions=game.describe(),
        )
    plugin.tool_package(
        PACKAGE_BASE,
        description="小游戏通用：查规则 / 查积分",
        instructions=(
            "小游戏通用工具：\n"
            "- minigame__help(game)：查看某个玩法的规则与边界"
            "（bottle / chengyu / checkin / fortune，也接受中文名）\n"
            "- minigame__points(user_id?)：查看积分与连续签到天数"
            "（只读；本期没有任何消费 / 兑换渠道）\n"
            "各玩法的完整说明在对应技能包里：minigame_bottle / minigame_chengyu / "
            "minigame_checkin / minigame_fortune。"
        ),
    )


_declare_tool_packages()


def _sender_name(message: Any) -> str:
    """从消息事件里尽力取昵称（取不到就回落空串）。"""
    sender = getattr(message, "sender", None)
    if sender is None and isinstance(message, dict):
        sender = message.get("sender")
    if sender is None:
        return ""
    if isinstance(sender, dict):
        return str(sender.get("card") or sender.get("nickname") or "")
    return str(
        getattr(sender, "card", None) or getattr(sender, "nickname", None) or ""
    )


def _event_text(event: Any) -> str:
    try:
        return str(Message(event).text or "")
    except Exception:
        if isinstance(event, dict):
            return str(event.get("raw_message") or "")
        return ""


class MinigamePlugin:
    """小游戏插件的运行时状态。"""

    def __init__(self) -> None:
        self.ctx: Any = None
        self.config: MinigameConfig | None = None
        self.service: MinigameService | None = None
        self.avatars: AvatarProvider | None = None
        self.games: list[Game] = []
        self.chengyu_sessions: dict[str, Any] = {}
        self._games_by_id: dict[str, Game] = {}
        self._latest: dict[str, Any] | None = None
        self._closed_sessions: list[dict[str, Any]] = []
        self._keyword_hits: list[str] = []
        self._rng = random.Random()
        # 卡片主题用独立的随机源：不消耗玩法本身的随机数（签到分数 / 抽签档位 / 接龙目标）
        self._theme_rng = random.Random()
        self._theme_memo: dict[str, str] = {}
        self._monotonic = time.monotonic
        self._logger: Any = None

    # ── 生命周期 ─────────────────────────────────────────────────

    async def load(
        self,
        ctx: Any,
        *,
        database: Any = None,
        clock: Any = None,
        rng: random.Random | None = None,
        monotonic: Any = None,
    ) -> None:
        self.ctx = ctx
        self._logger = getattr(ctx, "logger", None)
        # 卡片主题随插件一起注册 / 注销（内置主题由渲染器自己注册，这里只加本插件的）
        register_minigame_themes()
        raw = getattr(ctx, "config", None) or {}
        self.config = (
            raw
            if isinstance(raw, MinigameConfig)
            else MinigameConfig.model_validate(dict(raw))
        )
        if rng is not None:
            self._rng = rng
        if monotonic is not None:
            self._monotonic = monotonic
        self.avatars = AvatarProvider(
            ctx, cache_days=int(self.config.bottle_avatar_cache_days)
        )
        self.service = MinigameService(
            database=database if database is not None else globals()["database"],
            config=self.config,
            clock=clock,
            rng=self._rng,
            logger=self._logger,
            monotonic=self._monotonic,
        )
        self.games = [game for game in build_games() if game.id in self.config.enabled_game_ids]
        self._games_by_id = {game.id: game for game in self.games}
        # 玩法关键词：被 @ 命中即跳过本体的「收集上下文」等待，直接触发回复事件
        register_reply_trigger_keywords(plugin.name, self.reply_trigger_keywords())
        self.register_commands(ctx)

    def reply_trigger_keywords(self) -> tuple[str, ...]:
        """当前启用玩法的关键词（供「@ 命中即跳过等待」使用）。

        只登记已启用玩法的关键词：玩法下线后，它的关键词不该再影响本体的
        @ 提及行为。
        """
        enabled = (
            set(self.config.enabled_game_ids)
            if self.config is not None
            else set(ALL_GAME_IDS)
        )
        return tuple(
            keyword for keyword, game_id in KEYWORDS.items() if game_id in enabled
        )

    async def unload(self) -> None:
        self.chengyu_sessions.clear()
        self._latest = None
        self._theme_memo.clear()
        unregister_reply_trigger_keywords(plugin.name)
        unregister_minigame_themes()
        ctx = self.ctx
        registrar = getattr(ctx, "app_commands", None)
        if registrar is not None:
            try:
                registrar.unregister_all()
            except Exception:  # pragma: no cover - 注销失败不影响卸载
                pass
        self.games = []
        self._games_by_id = {}

    # ── 基础访问 ─────────────────────────────────────────────────

    def monotonic(self) -> float:
        return float(self._monotonic())

    def rng(self) -> random.Random:
        return self._rng

    def game_by_id(self, game_id: str) -> Game | None:
        return self._games_by_id.get(str(game_id))

    # ── 卡片主题 ─────────────────────────────────────────────────

    def pick_card_theme(self, game_id: str, *, cache_key: str = "") -> str:
        """选出本次卡片的主题并记日志。

        - random（默认）：从该玩法的候选主题池随机；
        - fixed：固定用配置 theme，留空则用该玩法的默认主题；
        - cache_key 非空时结果会被记住（同一结果的卡片重发用同一主题，
          例如当天重复请求抽签仍然是同一张图）。
        """
        config = self.config
        mode = str(getattr(config, "theme_mode", "random") or "random")
        configured = str(getattr(config, "theme", "") or "")
        memo_key = f"{game_id}|{cache_key}" if cache_key else ""
        if memo_key:
            cached = self._theme_memo.get(memo_key)
            if cached:
                return cached
        theme = resolve_theme(
            game_id, mode=mode, theme=configured, rng=self._theme_rng
        )
        if memo_key:
            if len(self._theme_memo) >= 64:
                self._theme_memo.pop(next(iter(self._theme_memo)))
            self._theme_memo[memo_key] = theme
        logger = self._logger
        info = getattr(logger, "info", None)
        if callable(info):
            try:
                info(
                    f"小游戏卡片主题：玩法 {game_id}，模式 {mode}，本次使用 {theme}"
                )
            except Exception:  # pragma: no cover - 日志失败不影响出图
                pass
        return theme

    # ── 渲染与发图（命令通道）─────────────────────────────────────

    async def render_card(self, html: str, *, timeout: float = 20.0) -> bytes | None:
        """渲染卡片 PNG；不可用 / 失败 / 超时一律返回 None（调用方降级纯文本）。"""
        from neobot_app.runtime.html_card import render_card_image

        return await render_card_image(
            html, timeout=timeout, screenshots=getattr(self.ctx, "screenshots", None)
        )

    async def send_card(self, command_ctx: Any, png: bytes, *, filename: str) -> bool:
        """把 PNG 发到命令所在会话（工具通道没有入站事件，因此不发图）。"""
        if command_ctx is None:
            return False
        from neobot_modloader.reply import Reply

        kind = str(getattr(command_ctx, "kind", "") or "")
        conv_id = getattr(command_ctx, "conv_id", None)
        if kind == "group":
            event = {"message_type": "group", "group_id": conv_id}
        else:
            event = {"message_type": "private", "user_id": conv_id}
        try:
            await Reply(self.ctx, event).image(data=png, filename=filename)
            return True
        except Exception as exc:
            logger = self._logger
            if logger is not None:
                logger.warning(f"小游戏卡片发送失败，降级为纯文本: {exc}")
            return False

    def enabled(self, game_id: str) -> bool:
        return str(game_id) in self._games_by_id

    def note_session_closed(self, session: Any, *, reason: str) -> None:
        self._closed_sessions.append(
            {
                "conversation_id": getattr(session, "conversation_id", ""),
                "steps": getattr(session, "steps", 0),
                "target": getattr(session, "target", 0),
                "reason": reason,
            }
        )

    # ── 交互上下文（工具通道认人）─────────────────────────────────

    def remember_interaction(
        self,
        *,
        user_id: Any,
        user_name: str = "",
        kind: str = "group",
        conversation_id: Any = "",
        game: str = "",
    ) -> dict[str, Any]:
        record = {
            "user_id": int(user_id or 0),
            "user_name": str(user_name or ""),
            "kind": str(kind or "group"),
            "conversation_id": str(conversation_id or ""),
            "game": str(game or ""),
            "at": self.monotonic(),
        }
        self._latest = record
        return record

    def latest_interaction(self, *, max_age: float = INTERACTION_TTL_SECONDS) -> dict[str, Any] | None:
        record = self._latest
        if record is None:
            return None
        if (self.monotonic() - float(record.get("at") or 0.0)) > float(max_age):
            return None
        return record

    def resolve_user(self, user_id: Any = "", user_name: str = "") -> tuple[str, str]:
        """工具通道认人：显式参数优先，其次回落最近一次交互。"""
        explicit = str(user_id or "").strip()
        record = self.latest_interaction()
        if explicit:
            name = str(user_name or "").strip()
            if not name and record is not None and str(record.get("user_id")) == explicit:
                name = str(record.get("user_name") or "")
            return explicit, name
        if record is None:
            return "", ""
        return str(record.get("user_id") or ""), str(user_name or record.get("user_name") or "")

    def tool_request(
        self,
        *,
        user_id: Any = "",
        user_name: str = "",
        game: str = "",
        raw_args: str = "",
    ) -> GameRequest | None:
        """构造工具通道请求；认不出用户时返回 None（由调用方回引导文案）。"""
        uid, name = self.resolve_user(user_id, user_name)
        if not uid:
            return None
        record = self.latest_interaction() or {}
        assert self.service is not None
        assert self.config is not None
        return GameRequest(
            runtime=self,
            service=self.service,
            config=self.config,
            command_ctx=None,
            args=raw_args.split() if raw_args else [],
            raw_args=raw_args,
            user_id=int(uid) if str(uid).isdigit() else 0,
            user_name=name,
            kind=str(record.get("kind") or "group"),
            conversation_id=str(record.get("conversation_id") or ""),
        )

    NEED_IDENTITY_HINT = (
        "无法确定是哪个用户（工具调用没有携带会话信息）。"
        "请让用户先发一条消息（例如 /mg 积分 或直接说「签到」）再调用本工具，"
        "或者把用户的 QQ 号作为 user_id 参数传进来。"
    )

    # ── 交互路径（事实 + 提示词）─────────────────────────────────

    def tool_hint(self, game_id: str) -> str:
        game = self.game_by_id(game_id)
        if game is None:
            names: list[str] = []
            for candidate in self.games:
                names.append(f"{TOOL_PREFIX}__{candidate.tool_names[0]}")
            return (
                f'{TOOL_PREFIX}__help(game="bottle")（或 chengyu / checkin / fortune）'
                + ("、" + "、".join(names) if names else "")
            )
        names = [f'{TOOL_PREFIX}__help(game="{game_id}")']
        names.extend(f"{TOOL_PREFIX}__{name}" for name in game.tool_names)
        return "、".join(names)

    def interaction_background(
        self,
        *,
        game: str,
        request: GameRequest | None = None,
        situation: str,
        hint: str,
    ) -> str:
        """命令通道交互路径的「事实 + 提示词」（由主管线生成回复）。"""
        who = ""
        game_id = self._game_id_for_label(game)
        if request is not None:
            who = (
                f"会话：{request.kind} {request.conversation_id}；"
                f"用户：{request.user_name or request.user_id}（QQ {request.user_id}）\n"
            )
        packages = "、".join(preactivate_for(game_id))
        return (
            f"【小游戏·{game}｜需要你（AI）组织回复】\n"
            f"{who}"
            f"事实：{situation}\n"
            f"接下来请你这样回应：{hint}\n"
            f"可用工具：{self.tool_hint(game_id)}\n"
            f"（若工具表里暂时没有它们，先调用 skills__load_tools 加载 {packages}。）\n"
            "不要复述本条状态说明，直接用你自己的话对用户说。"
        )

    def _game_id_for_label(self, label: str) -> str:
        for game in self.games:
            if game.name == label or game.id == label:
                return game.id
        for game in build_games():
            if game.name == label or game.id == label:
                return game.id
        return ""

    # ── 命令面 ──────────────────────────────────────────────────

    def register_commands(self, ctx: Any) -> None:
        registrar = getattr(ctx, "app_commands", None)
        if registrar is None or not getattr(registrar, "available", False):
            return
        runtime = self

        @registrar.register(
            "mg",
            description="NeoBot 小游戏：漂流瓶 / 成语接龙 / 签到与积分 / 抽签",
            usage="[游戏|stop|rank|积分|help] [参数]",
            aliases=("游戏",),
            params=(
                ("游戏", "玩法名或别名，如 瓶 / 漂流瓶 / 成语接龙 / 签到 / 抽签"),
                ("stop", "结束当前会话的进行中一局（发起者或次级管理员）"),
                ("rank", "积分排行榜，可跟页码"),
                ("积分", "查看自己的积分（只读）"),
                ("help", "查看玩法规则，如 /mg help 瓶"),
            ),
        )
        async def _mg_command(command_ctx: Any) -> str | None:
            return await runtime.handle_command(command_ctx)

    async def handle_command(self, command_ctx: Any) -> str | None:
        raw = str(getattr(command_ctx, "raw_args", "") or "").strip()
        user_id = int(getattr(command_ctx, "user_id", 0) or 0)
        kind = str(getattr(command_ctx, "kind", "") or "group")
        conv_id = str(getattr(command_ctx, "conv_id", "") or "")
        user_name = _sender_name(getattr(command_ctx, "message", None))
        self.remember_interaction(
            user_id=user_id,
            user_name=user_name,
            kind=kind,
            conversation_id=conv_id,
        )
        assert self.service is not None and self.config is not None

        if not raw:
            return self.menu_text()
        parts = raw.split(maxsplit=1)
        head = parts[0]
        rest = parts[1].strip() if len(parts) > 1 else ""
        key = head.casefold()

        if key in ("stop", "结束", "停止"):
            return await self.stop_command(command_ctx, rest=rest)
        if key in ("rank", "排行", "排行榜", "榜单"):
            return await self.rank_command(
                command_ctx, rest=rest, conversation_id=conv_id
            )
        if key in ("积分", "points", "分"):
            return await self.points_text(user_id)
        if key in ("help", "帮助", "?"):
            return self.help_command(rest)

        game = find_game(self.games, head)
        request = self.command_request(
            command_ctx,
            user_id=user_id,
            user_name=user_name,
            kind=kind,
            conversation_id=conv_id,
            game=game.id if game is not None else "",
        )
        if game is None:
            return self.natural_language_fallback(request, raw=raw)
        self.remember_interaction(
            user_id=user_id,
            user_name=user_name,
            kind=kind,
            conversation_id=conv_id,
            game=game.id,
        )
        return await self.run_game(request, game, raw_args=rest)

    def command_request(
        self,
        command_ctx: Any,
        *,
        user_id: int,
        user_name: str,
        kind: str,
        conversation_id: str,
        game: str = "",
        raw_args: str = "",
    ) -> GameRequest:
        assert self.service is not None and self.config is not None
        return GameRequest(
            runtime=self,
            service=self.service,
            config=self.config,
            command_ctx=command_ctx,
            args=raw_args.split() if raw_args else [],
            raw_args=raw_args,
            user_id=int(user_id or 0),
            user_name=user_name,
            kind=kind,
            conversation_id=str(conversation_id or ""),
        )

    async def run_game(self, request: GameRequest, game: Game, *, raw_args: str) -> str | None:
        request.raw_args = raw_args
        request.args = raw_args.split() if raw_args else []
        return await game.run(request)

    def natural_language_fallback(self, request: GameRequest, *, raw: str) -> str:
        """未知玩法名 / 自然语言表达意图：交 agent 追问（不回固定错误文案）。"""
        request.want_sync_reply()
        return self.interaction_background(
            game="小游戏",
            request=request,
            situation=(
                f"用户发来了 /mg {raw}，但这不是已启用的玩法名或子命令。"
                "这可能只是自然语言意图（例如「我想玩漂流瓶」）。"
            ),
            hint=(
                "先向用户确认他想玩哪一个：漂流瓶 / 成语接龙 / 签到 / 抽签；"
                "确认后调用 minigame__help(game=...) 看规则，或用对应的命令引导他继续。"
            ),
        )

    async def stop_command(self, command_ctx: Any, *, rest: str) -> str:
        game: Any = self.game_by_id("chengyu")
        if game is None:
            return "当前没有可结束的小游戏会话（成语接龙玩法未启用）。"
        request = self.command_request(
            command_ctx,
            user_id=int(getattr(command_ctx, "user_id", 0) or 0),
            user_name=_sender_name(getattr(command_ctx, "message", None)),
            kind=str(getattr(command_ctx, "kind", "") or "group"),
            conversation_id=str(getattr(command_ctx, "conv_id", "") or ""),
            game="chengyu",
        )
        result = await game.stop(request)
        return result or "本局已结束。"

    async def points_text(self, user_id: Any) -> str:
        assert self.service is not None
        profile = await self.service.get_profile(user_id)
        streak = await self.service.streak(user_id)
        return format_points_text(score=int(profile.get("score") or 0), streak=streak)

    async def rank_command(
        self, command_ctx: Any, *, rest: str, conversation_id: str
    ) -> str:
        assert self.service is not None
        token = rest.split()[0] if rest.strip() else ""
        if (token and not token.isdigit()) or (token.isdigit() and int(token) < 1):
            # 格式错误 / 页码非法 -> agent 交互路径（不回固定错误文案）
            request = self.command_request(
                command_ctx,
                user_id=int(getattr(command_ctx, "user_id", 0) or 0),
                user_name=_sender_name(getattr(command_ctx, "message", None)),
                kind=str(getattr(command_ctx, "kind", "") or "group"),
                conversation_id=conversation_id,
                raw_args=rest,
            )
            return self.rank_format_fallback(request, token=token)
        page = int(token) if token else 1
        data = await self.service.leaderboard(page=page, page_size=RANK_PAGE_SIZE)
        rows = list(data.get("rows") or [])
        if not rows:
            return "排行榜还没有数据：先玩一局（漂流瓶 / 成语接龙 / 签到）就会有记录了。"
        lines = [
            f"【积分排行榜 · 第 {data['page']} 页】"
            f"（共 {data['total']} 位玩家，每页 {data['page_size']} 条）"
        ]
        offset = (int(data["page"]) - 1) * int(data["page_size"])
        for index, row in enumerate(rows, start=offset + 1):
            lines.append(
                f"{index}. {row['user_id']} — {int(row['score'])} 分"
                f"（场次 {int(row['plays'])}，最高 {int(row['best_score']) }）"
            )
        group_rows = await self.service.group_leaderboard(conversation_id, limit=5)
        if group_rows:
            lines.append("")
            lines.append("【本群榜】")
            for index, row in enumerate(group_rows, start=1):
                lines.append(f"{index}. {row['user_id']} — {int(row['score'])} 分")
        lines.append("")
        lines.append("用 /mg rank <页码> 翻页；积分只读，本期没有消费渠道。")
        return "\n".join(lines)

    def rank_format_fallback(self, request: GameRequest, *, token: str) -> str:
        """页码非法：交 agent 追问（置 sync_reply），不回固定错误文案。"""
        request.want_sync_reply()
        return self.interaction_background(
            game="小游戏",
            request=request,
            situation=(
                f"用户执行了 /mg rank，但页码不是 1 及以上的整数（收到的是「{token}」），"
                "排行榜没有渲染。"
            ),
            hint=(
                "用你自己的话请用户给出一个合法的页码（从 1 开始），"
                "然后重新执行 /mg rank <页码>。"
            ),
        )

    def help_command(self, rest: str) -> str:
        token = rest.split()[0] if rest.strip() else ""
        if not token:
            lines = [self.menu_text(), "", "各玩法规则（/mg help <游戏> 可单独查看）"]
            for candidate in self.games:
                lines.append("")
                lines.append(candidate.help_text())
            return "\n".join(lines)
        game = find_game(self.games, token)
        if game is None:
            available = "、".join(f"{game.name}" for game in self.games) or "（无）"
            return f"没有找到玩法「{token}」。可用玩法：{available}"
        return game.help_text()

    def menu_text(self) -> str:
        lines = ["【NeoBot 小游戏】可用玩法："]
        for game in self.games:
            alias = "/".join(game.aliases[:2]) if game.aliases else game.id
            lines.append(f"- {game.name}（/mg {alias}）：{game.summary}")
        if not self.games:
            lines.append("- 当前没有启用任何玩法（检查插件配置 enabled_games）。")
        lines.append("")
        lines.append(MENU_FOOTER)
        return "\n".join(lines)

    # ── 关键词 / 意图入口（R14 / D11）─────────────────────────────

    def match_keyword(self, text: str) -> str:
        """按最长关键词优先匹配玩法 id；无命中返回空串。"""
        value = str(text or "")
        best = ""
        hit = ""
        for keyword, game_id in KEYWORDS.items():
            if keyword in value and len(keyword) > len(best):
                best = keyword
                hit = game_id
        return hit

    def _event_identity(self, event: Any) -> tuple[int, str, str, str]:
        """从事件里取出（user_id, user_name, kind, conversation_id）。"""
        user_id = 0
        conversation_id = ""
        kind = "group"
        if isinstance(event, dict):
            user_id = int(event.get("user_id") or 0)
            if event.get("group_id") is not None:
                conversation_id = str(event.get("group_id"))
            else:
                kind = "private"
                conversation_id = str(event.get("user_id") or "")
        return user_id, _sender_name(event), kind, conversation_id

    def on_keyword(self, ctx: Any = None, event: Any = None) -> str:
        """插件消息处理器：命中关键词 -> 进入 agent 交互路径，**不执行游戏动作**。

        通过 ctx.agent_reply(...) 把控制权交回主回复管线（与命令 sync_reply 同一
        通路），并**按玩法**预激活该玩法的技能包，使对应的 minigame__<tool> 在
        本轮模型调用里就能直接调用。返回的引导块同时用于日志与测试断言。
        """
        text = _event_text(event)
        if text.strip().startswith("/"):
            return ""
        game_id = self.match_keyword(text)
        if not game_id or not self.enabled(game_id):
            return ""
        user_id, user_name, kind, conversation_id = self._event_identity(event)
        self.remember_interaction(
            user_id=user_id,
            user_name=user_name,
            kind=kind,
            conversation_id=conversation_id,
            game=game_id,
        )
        self._keyword_hits.append(game_id)
        guidance = self.keyword_guidance(
            game_id=game_id,
            user_id=user_id,
            user_name=user_name,
            text=text.strip(),
        )
        self.emit_intent(ctx, background=guidance, game_id=game_id)
        return guidance

    def keyword_guidance(
        self, *, game_id: str, user_id: int, user_name: str, text: str
    ) -> str:
        """命中关键词后的引导块：写明两个分支（先确认 / 直接执行）。"""
        game = self.game_by_id(game_id)
        name = game.name if game is not None else game_id
        packages = "、".join(preactivate_for(game_id))
        return (
            f"【小游戏·{name}｜关键词入口】\n"
            f"用户：{user_name or user_id}（QQ {user_id}）说：{text}\n"
            f"事实：用户提到了「{name}」，程序**没有执行任何游戏动作**；"
            "本轮已按玩法预激活该玩法的工具，你可以直接调用。\n"
            "请按下面两种情况分别处理：\n"
            f"1) 如果用户只是**顺口提到 / 想玩但没说清**（例如「想玩{name}」），"
            "先用你自己的话**询问确认**（要做什么、参数是什么），**不要**直接执行游戏动作；\n"
            "2) 如果用户**已经给出明确诉求、只是不是命令格式**（例如「帮我匿名丢一个瓶子：今天也要开心」），"
            "**直接调用**对应工具执行，再用你自己的话自然回报结果。\n"
            f"可用工具：{self.tool_hint(game_id)}\n"
            f"（若工具表里暂时没有它们，先调用 skills__load_tools 加载 {packages}。）\n"
            "不要复述本条状态说明。"
        )

    def emit_intent(self, ctx: Any, *, background: str, game_id: str) -> bool:
        """登记「交主管线 + 按玩法预激活技能包」意图（失败不影响消息路径）。"""
        if ctx is None:
            return False
        recorder = getattr(ctx, "agent_reply", None)
        if not callable(recorder):
            return False
        try:
            recorder(str(background or ""), preactivate=preactivate_for(game_id))
            return True
        except Exception:  # pragma: no cover - 意图登记失败只是这次不生效
            return False

    def on_command_intent(self, ctx: Any = None, event: Any = None) -> str:
        """命令入口的意图：只声明预激活的技能包（背景由命令结果提供）。

        命令消息由本体 CommandService 处理；本处理器在事件分发阶段运行，因此可以
        在命令结果触发回复管线**之前**声明「本轮要预激活哪个玩法包」，让
        /mg 瓶（缺参数）这类交互路径里的模型立刻能调用工具。
        """
        text = _event_text(event).strip()
        match = _MG_COMMAND_RE.match(text)
        if match is None:
            return ""
        rest = match.group(1).strip()
        head = rest.split()[0] if rest else ""
        game = find_game(self.games, head) if head else None
        game_id = game.id if game is not None else ""
        self.emit_intent(ctx, background="", game_id=game_id)
        names = "、".join(preactivate_for(game_id)) if game_id else skill_name_for(PACKAGE_BASE)
        return f"预激活 {names}"


_instance = MinigamePlugin()


def _runtime() -> MinigamePlugin:
    return _instance


# ── agent 工具（每个玩法都有说明 + 可调用工具，R15）───────────────
# 工具最终名 = {plugin}__{local} = minigame__<local>。
# user_id / user_name 是**可选**参数：省略时用最近一次交互（命令或关键词入口
# 记录）来认人 —— 插件工具没有入站事件，这是唯一可靠的认人方式。


@plugin.tool(
    "bottle_write",
    package="bottle",
    description=(
        "把一句话装进漂流瓶丢进全局瓶池。content 是正文（去空白后 1-500 字，"
        "禁止纯链接，支持 Markdown）；anonymous=true 表示匿名（不显示 QQ 与昵称、"
        "昵称位固定「神秘的人」，但头像照常显示）。瓶子发出后不可查询、不可撤回。"
    ),
)
async def _tool_bottle_write(
    content: str,
    anonymous: bool = False,
    user_id: str = "",
    user_name: str = "",
) -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("bottle")
    if game is None:
        return "小游戏未启用「漂流瓶」玩法（插件配置 enabled_games 不含 bottle）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="bottle")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.write(request, anonymous=bool(anonymous), content=str(content or ""))
    return result or "已发瓶。"


@plugin.tool(
    "bottle_pick",
    package="bottle",
    description=(
        "从全局瓶池随机捞一个别人丢的漂流瓶。会自动排除自己，以及你最近 3 次"
        "捞到过的发送者；因排除而无瓶可捞时会回落普通随机并在结果里说明。"
        "每日捞瓶有上限，捞取没有冷却。"
    ),
)
async def _tool_bottle_pick(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("bottle")
    if game is None:
        return "小游戏未启用「漂流瓶」玩法（插件配置 enabled_games 不含 bottle）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="bottle")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.pick(request)
    return result or "已捞取。"


@plugin.tool(
    "checkin",
    package="checkin",
    description=(
        "每日签到：由程序随机给 1-10 积分（连续签到每天附加 +1，上限 +5）。"
        "同一自然日重复签到**不加分**，只会返回既有结果；断签后连续天数归零，"
        "不提供补签。签到结果请由你用自然语言转述给用户。"
    ),
)
async def _tool_checkin(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("checkin")
    if game is None:
        return "小游戏未启用「签到」玩法（插件配置 enabled_games 不含 checkin）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="checkin")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.do_checkin(request)
    return result or "已签到。"


@plugin.tool(
    "fortune",
    package="fortune",
    description=(
        "抽今日运势（每天一次，由程序随机并落库）。当天已抽过不会重抽，只返回"
        "同一结果。默认五档：大吉 / 吉 / 中吉 / 小吉 / 平；管理员可配置加入"
        "小凶 / 凶。抽签不附带积分；请由你用自然语言把这个结果讲给用户。"
    ),
)
async def _tool_fortune(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("fortune")
    if game is None:
        return "小游戏未启用「抽签」玩法（插件配置 enabled_games 不含 fortune）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="fortune")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.draw(request)
    return result or "已抽签。"


@plugin.tool(
    "points",
    package=PACKAGE_BASE,
    description=(
        "查看用户的积分与连续签到天数。积分是**只读**的：本期没有任何消费、"
        "兑换或解锁渠道，也不影响本体功能。"
    ),
)
async def _tool_points(user_id: str = "", user_name: str = "") -> str:
    runtime = _runtime()
    resolved, _name = runtime.resolve_user(user_id, user_name)
    if not resolved or runtime.service is None:
        return runtime.NEED_IDENTITY_HINT
    return await runtime.points_text(resolved)


@plugin.tool(
    "help",
    package=PACKAGE_BASE,
    description=(
        "查看某个小游戏的规则与边界。game 取 bottle / chengyu / checkin / fortune"
        "（也接受中文名，如 漂流瓶 / 成语接龙 / 签到 / 抽签）；留空返回全部玩法说明。"
    ),
)
async def _tool_help(game: str = "") -> str:
    runtime = _runtime()
    return runtime.help_command(str(game or ""))


@plugin.tool(
    "chengyu_submit",
    package="chengyu",
    description=(
        "成语接龙记一步：**不校验内容**（是否算成语、接不接得上、是否重复都由你判断），"
        "只把 word 记入本局流水、计一步、按配置 +1 分，并返回进度（第 k/N 条）。"
        "单局最多 10 步、每条 60 秒，用满步数或超时即结束本局；达成目标 N 额外 +N。"
    ),
)
async def _tool_chengyu_submit(
    word: str, user_id: str = "", user_name: str = ""
) -> str:
    runtime = _runtime()
    game: Any = runtime.game_by_id("chengyu")
    if game is None:
        return "小游戏未启用「成语接龙」玩法（插件配置 enabled_games 不含 chengyu）。"
    request = runtime.tool_request(user_id=user_id, user_name=user_name, game="chengyu")
    if request is None:
        return runtime.NEED_IDENTITY_HINT
    result = await game.submit(request, str(word if word is not None else ""))
    return result or "已记录。"


# ── 关键词 / 意图入口（插件消息处理器；不拦截 AI 回复）────────────
# R14 / D11：入口实现放在插件消息处理器里，不改造本体启动期关键词快照。
# 命中后经 ctx.agent_reply(background, preactivate=[...]) 把控制权交回主回复
# 管线，并**按玩法**预激活对应技能包（见 neobot_modloader.agent_intent）。

#: 小游戏命令文本（含 /游戏 别名）
_MG_COMMAND_RE = re.compile(r"^/(?:mg|游戏)\s*(.*)$", re.IGNORECASE | re.DOTALL)


def _keyword_rule(event: dict[str, Any]) -> bool:
    """命令消息不参与关键词入口（/mg ... 有自己的命令路径）。"""
    text = _event_text(event)
    return bool(text.strip()) and not text.strip().startswith("/")


def _command_rule(event: dict[str, Any]) -> bool:
    """只对本插件的命令文本登记「预激活」意图（不消费、不改写消息）。"""
    return _MG_COMMAND_RE.match(_event_text(event).strip()) is not None


@plugin.message(
    keywords=tuple(KEYWORDS),
    rule=_keyword_rule,
    priority=10,
)
async def _minigame_keyword_entry(ctx: Any, event: dict[str, Any]) -> str:
    return _instance.on_keyword(ctx, event)


@plugin.message(
    rule=_command_rule,
    priority=9,
)
async def _minigame_command_intent_entry(ctx: Any, event: dict[str, Any]) -> str:
    """命令入口的预激活声明（背景仍由本体命令结果提供）。"""
    return _instance.on_command_intent(ctx, event)


# ── 生命周期 ──────────────────────────────────────────────────


@plugin.on_load
async def _minigame_load(ctx: Any) -> None:
    await _instance.load(ctx)


@plugin.on_shutdown
async def _minigame_shutdown() -> None:
    await _instance.unload()


__all__ = [
    "ALL_GAME_IDS",
    "INTERACTION_TTL_SECONDS",
    "KEYWORDS",
    "MENU_FOOTER",
    "MinigamePlugin",
    "RANK_PAGE_SIZE",
    "TOOL_PREFIX",
    "create_database",
    "database",
    "plugin",
]

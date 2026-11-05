"""插件状态与交互上下文：生命周期、认人、工具请求与提示词背景。"""

from __future__ import annotations

import random
from typing import Any
from neobot_app.message.fast_reply_keywords import register_reply_trigger_keywords
from neobot_app.message.fast_reply_keywords import unregister_reply_trigger_keywords
from ..avatars import AvatarProvider
from ..config import ALL_GAME_IDS
from ..config import MinigameConfig
from ..games import Game
from ..games import GameRequest
from ..games import build_games
from ..service import MinigameService
from ..themes import register_minigame_themes
from ..themes import unregister_minigame_themes

from .constants import INTERACTION_TTL_SECONDS, KEYWORDS, TOOL_PREFIX
from .registration import database as default_database
from .registration import plugin, preactivate_for


class _PluginStateMixin:
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
            database=database if database is not None else default_database,
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

    async def remember_user_name(self, user_id: Any, user_name: str) -> bool:
        """把昵称落进 mg_profile（榜单优先显示昵称）：尽力而为，失败不抛。"""
        service = self.service
        if service is None:
            return False
        try:
            return bool(await service.remember_user_name(user_id, user_name))
        except Exception as exc:  # pragma: no cover - 昵称只是展示信息
            message = f"记录小游戏昵称失败（已忽略）: {exc}"
            if self._logger is not None:
                self._logger.warning(message)
            return False

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

"""命令入口：/mg 注册、解析、直接执行与自然语言回落。"""

from __future__ import annotations

from typing import Any
from ..games import Game
from ..games import GameRequest
from ..games import find_game
from ..games.checkin import format_points_text
from ..service import MinigameService

from .utils import _sender_name


class _PluginCommandsMixin:
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
        # 昵称落库：榜单卡片优先显示昵称，取不到才回落掩码（issue #85）
        await self.remember_user_name(user_id, user_name)
        assert self.service is not None and self.config is not None

        if not raw:
            return await self.menu_card(command_ctx)
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
            return await self.points_card(command_ctx, user_id)
        if key in ("help", "帮助", "?"):
            return await self.help_card(command_ctx, rest)

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

    # ── 积分对外接口（其它插件经插件能力调用；见文件末尾的 @plugin.capability）──

    def require_service(self) -> MinigameService:
        """取本插件的服务层；未加载时给出可读错误（而不是 AssertionError）。"""
        service = self.service
        if service is None:
            raise RuntimeError("小游戏插件尚未加载，积分接口不可用")
        return service

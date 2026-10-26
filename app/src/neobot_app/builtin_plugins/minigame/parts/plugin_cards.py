"""卡片渲染与发送：主题选择、菜单 / 积分 / 帮助卡片。"""

from __future__ import annotations

from typing import Any
from ..games.checkin import READONLY_NOTICE
from ..games.checkin import format_points_text
from ..themes import resolve_theme

from .constants import MENU_FOOTER


class _PluginCardsMixin:
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

    # ── 命令卡片（复用本体 commands/card.py 的三级口径）─────────────

    async def _send_command_card(
        self,
        command_ctx: Any,
        *,
        title: str,
        blocks: list[dict[str, Any]],
        fallback_text: str,
        subtitle: str = "",
        footer: str = "",
        filename: str,
    ) -> str | None:
        """出图成功返回 None（已发送）；渲染不可用则回等价纯文本。

        小游戏插件不自己截图：走本体 `commands/card.py`，与 /help、/status 同一套
        「HTML 卡片 → 发图 → 纯文本」降级，超时/异常一律不抛给用户。
        """
        from neobot_app.commands import card as card_module

        return await card_module.send_card(
            command_ctx,
            title=title,
            subtitle=subtitle,
            blocks=blocks,
            footer=footer,
            fallback_text=fallback_text,
            filename=filename,
        )

    async def menu_card(self, command_ctx: Any) -> str | None:
        rows = []
        for game in self.games:
            alias = "/".join(game.aliases[:2]) if game.aliases else game.id
            rows.append([game.name, game.summary, f"/mg {alias}"])
        blocks: list[dict[str, Any]] = []
        if rows:
            blocks.append(
                {
                    "kind": "rows",
                    "columns": ["玩法", "说明", "用法"],
                    "widths": ["16%", "50%", "34%"],
                    "rows": rows,
                }
            )
        else:
            blocks.append(
                {"kind": "note", "text": "当前没有启用任何玩法（检查插件配置 enabled_games）。"}
            )
        return await self._send_command_card(
            command_ctx,
            title="NeoBot 小游戏",
            subtitle=f"共 {len(rows)} 个玩法",
            blocks=blocks,
            footer=MENU_FOOTER,
            fallback_text=self.menu_text(),
            filename="mg_menu.png",
        )

    async def points_card(self, command_ctx: Any, user_id: Any) -> str | None:
        assert self.service is not None
        profile = await self.service.get_profile(user_id)
        streak = await self.service.streak(user_id)
        score = int(profile.get("score") or 0)
        text = format_points_text(score=score, streak=streak)
        blocks = [
            {
                "kind": "stats",
                "cols": 2,
                "items": [
                    ("积分", str(score), "ok"),
                    ("连续签到", f"{int(streak)} 天"),
                ],
            },
            {"kind": "note", "text": READONLY_NOTICE},
        ]
        return await self._send_command_card(
            command_ctx,
            title="我的积分",
            blocks=blocks,
            fallback_text=text,
            filename="mg_points.png",
        )

    async def help_card(self, command_ctx: Any, rest: str) -> str | None:
        if not str(rest or "").strip():
            # 无参数时 help_command 会先复述一遍玩法菜单再堆所有规则（三千像素高的卡）：
            # 菜单卡已经能表达这一屏，这里直接复用，规则请用 /mg help <玩法> 单独看。
            return await self.menu_card(command_ctx)
        text = self.help_command(rest)
        lines = [line for line in text.splitlines() if line.strip()]
        # note 块的换行会被 HTML 折叠，因此逐行成块；过长时截断并指向文本版
        shown = lines[:18]
        blocks = [{"kind": "note", "text": line} for line in shown]
        if len(lines) > len(shown):
            blocks.append(
                {"kind": "note", "text": f"…还有 {len(lines) - len(shown)} 行，完整规则见 /mg help 的文本回复"}
            )
        return await self._send_command_card(
            command_ctx,
            title="玩法规则",
            subtitle=str(rest or "").strip() or "全部玩法",
            blocks=blocks,
            fallback_text=text,
            filename="mg_help.png",
        )

    @staticmethod
    def _rank_player_label(row: Any, *, fallback_index: int) -> str:
        """榜单里的玩家标识：**昵称优先，取不到回落掩码**（前 2 后 2）。

        命令回复对全群可见：完整 QQ 号一律不下发（issue #85）。昵称来自
        `mg_profile.user_name`（每次 /mg 命令刷一次），从没用过命令的玩家连掩码
        都不成串，退化成 `玩家 #N`。
        """
        if not isinstance(row, dict):
            return f"玩家 #{fallback_index}"
        name = str(row.get("user_name") or "").strip()
        if name:
            return name
        uid = str(row.get("user_id") or "").strip()
        return f"{uid[:2]}****{uid[-2:]}" if len(uid) > 4 else f"玩家 #{fallback_index}"

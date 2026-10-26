"""排行榜 / 规则 / 菜单的纯文本形态。"""

from __future__ import annotations

from typing import Any
from ..games import GameRequest
from ..games import find_game

from .constants import MENU_FOOTER, RANK_PAGE_SIZE
from .utils import _sender_name


class _PluginHelpMixin:
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
        # 榜单对全群可见：玩家标识只给掩码，不下发完整 QQ 号（issue #85 同口径）
        page_info = (
            f"第 {data['page']} 页 · 共 {data['total']} 位玩家 · 每页 {data['page_size']} 条"
        )
        lines = [f"【积分排行榜 · {page_info}】"]
        offset = (int(data["page"]) - 1) * int(data["page_size"])
        rank_rows: list[list[str]] = []
        for index, row in enumerate(rows, start=offset + 1):
            player = self._rank_player_label(row, fallback_index=index)
            rank_rows.append(
                [
                    str(index),
                    player,
                    f"{int(row['score'])} 分",
                    f"场次 {int(row['plays'])} / 最高 {int(row['best_score'])}",
                ]
            )
            lines.append(
                f"{index}. {player} — {int(row['score'])} 分"
                f"（场次 {int(row['plays'])}，最高 {int(row['best_score'])}）"
            )
        group_rows = await self.service.group_leaderboard(conversation_id, limit=5)
        if group_rows:
            lines.append("")
            lines.append("【本群榜】")
            for index, row in enumerate(group_rows, start=1):
                lines.append(
                    f"{index}. {self._rank_player_label(row, fallback_index=index)}"
                    f" — {int(row['score'])} 分"
                )
        lines.append("")
        lines.append("用 /mg rank <页码> 翻页；积分只读，本期没有消费渠道。")

        blocks: list[dict[str, Any]] = [
            {
                "kind": "rows",
                "columns": ["名次", "玩家", "积分", "战绩"],
                "widths": ["12%", "28%", "20%", "40%"],
                "rows": rank_rows,
            }
        ]
        if group_rows:
            blocks.append(
                {
                    "kind": "rows",
                    "title": "本群榜",
                    "columns": ["名次", "玩家", "积分"],
                    "widths": ["16%", "44%", "40%"],
                    "rows": [
                        [
                            str(index),
                            self._rank_player_label(row, fallback_index=index),
                            f"{int(row['score'])} 分",
                        ]
                        for index, row in enumerate(group_rows, start=1)
                    ],
                }
            )
        blocks.append(
            {
                "kind": "note",
                "text": (
                    "玩家显示昵称；取不到昵称的显示掩码（前 2 后 2）—— 榜单不下发完整 QQ 号。"
                    "用 /mg rank <页码> 翻页。"
                ),
            }
        )
        return await self._send_command_card(
            command_ctx,
            title="积分排行榜",
            subtitle=page_info,
            blocks=blocks,
            fallback_text="\n".join(lines),
            filename="mg_rank.png",
        )

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

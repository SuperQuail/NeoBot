"""签到与积分玩法（spec(5) §4.7 / R27-R29）。

- 每日一次；分数由**程序随机**（默认 1-10）；
- 连续签到每天 +1 附加，上限 +5；
- 同一自然日重复签到**不加分**，把既有结果告诉 agent；
- 断签连续天数归零、**不提供补签**、**不主动提醒**；
- 统一积分账户（mg_profile.score），本期**无任何消费渠道**，只提供查看。

按 §4.7 的要求，签到**程序不发固定文案**：handler 置 ctx.sync_reply=True，
把「本次得了多少分 / 已经是第几天 / 当前总分」交给 agent 组织回复。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..art import checkin_art
from ..themes import default_theme
from . import Game, GameRequest

HELP_TOKENS = ("帮助", "help", "规则", "?")

#: 卡片文件名
CARD_FILENAME = "checkin.png"

#: 只读提示（命令与工具都出现，A34 的表断言据此确认没有消费入口）
READONLY_NOTICE = "积分本期只提供查看：不能消费、不能兑换、不影响任何其它功能。"


@dataclass
class CheckinCard:
    title: str
    subtitle: str
    #: 有仪式感的三块指标：(标签, 值, 色调)
    stats: list[tuple[str, str, str]] = field(default_factory=list)
    #: 明细行（连续天数 / 明细）
    details: list[tuple[str, str]] = field(default_factory=list)
    #: 日历页与点阵需要的程序数据
    day: str = ""
    streak: int = 0
    already: bool = False
    footer: str = READONLY_NOTICE


def build_card_html(card: CheckinCard, *, theme: str = "") -> str:
    """签到卡片：日历页 + 打卡印章 + 连续天数点阵 + 三块指标。"""
    from neobot_app.runtime.html_card import inject_slot, render_card_html

    blocks: list[dict[str, Any]] = [
        {"kind": "slot", "name": "checkin-art"},
    ]
    if card.stats:
        blocks.append(
            {"kind": "stats", "cols": min(3, len(card.stats)), "items": list(card.stats)}
        )
    if card.details:
        blocks.append(
            {
                "kind": "kv",
                "title": "连续与明细",
                "items": [list(row) for row in card.details],
            }
        )
    blocks.append({"kind": "note", "text": READONLY_NOTICE, "tone": "muted"})
    html = render_card_html(
        title=card.title,
        subtitle=card.subtitle,
        blocks=blocks,
        footer=card.footer,
        theme=theme or default_theme("checkin"),
    )
    return inject_slot(
        html,
        "checkin-art",
        checkin_art(day=card.day, streak=card.streak, already=card.already),
    )


def build_card_text(card: CheckinCard) -> str:
    lines = [card.title]
    if card.subtitle:
        lines.append(card.subtitle)
    for label, value, _tone in card.stats:
        lines.append(f"{label}：{value}")
    for label, value in card.details:
        lines.append(f"{label}：{value}")
    lines.append(READONLY_NOTICE)
    return "\n".join(lines)


def format_points_text(*, score: int, streak: int) -> str:
    """确定性查询文案（/mg 积分 与工具 minigame__points 共用）。"""
    return f"当前积分：{int(score)}（连续签到 {int(streak)} 天）。{READONLY_NOTICE}"


class CheckinGame(Game):
    id = "checkin"
    name = "签到"
    aliases = ("打卡", "checkin", "每日签到")
    summary = "每日签到领积分（连续签到有附加分，积分只读）"
    tool_names = ("checkin", "points")

    def describe(self) -> str:
        return (
            "签到与积分：每天可以向 agent 说「签到」（或发 /mg 签到）领一次积分。\n"
            "- 命令入口：/mg 签到、/mg 积分\n"
            "- 工具入口：minigame__checkin()、minigame__points()\n"
            "积分由程序随机（默认 1-10）；连续签到每天附加 +1，上限 +5；"
            "同一自然日重复签到**不加分**（重复调用只返回既有结果）。\n"
            "断签后连续天数归零，**不提供补签**，也**不会主动提醒**签到。\n"
            "积分是统一账户，本期**只读**：不能消费、不能兑换、不影响任何其它功能。\n"
            "签到后由你（AI）用自己的话回应，程序不发固定文案。"
        )

    def help_text(self, *, mode: str = "") -> str:
        return (
            "【签到与积分】\n"
            "签到：/mg 签到（每天一次；重复签到不加分，只告诉你今天已经签过）\n"
            "查询：/mg 积分（或让 agent 调用 minigame__points）\n"
            "规则：\n"
            "- 每次签到由程序随机给 1-10 积分（可配置）；\n"
            "- 连续签到每天附加 +1，最多 +5；\n"
            "- 断签后连续天数归零，**不提供补签**，也不会主动提醒；\n"
            f"- {READONLY_NOTICE}"
        )

    async def run(self, request: GameRequest) -> str | None:
        args = list(request.args or [])
        head = args[0].strip() if args else ""
        if head in HELP_TOKENS:
            return self.help_text()
        return await self.do_checkin(request)

    async def do_checkin(self, request: GameRequest) -> str | None:
        service = request.service
        result = await service.checkin(request.user_id)
        already = bool(result.get("already"))
        streak = int(result.get("streak") or 0)
        score = int(result.get("score") or 0)
        total = int(result.get("total") or 0)
        if already:
            subtitle = "今天已经签过啦，重复签到不加分"
            stats = [
                ("当日获得", f"{score} 分", "accent"),
                ("连续签到", f"{streak} 天", "ok"),
                ("当前总分", f"{total}", "muted"),
            ]
            details = [("今日签到", "已完成（本次未重复加分）")]
            situation = (
                f"用户今天已经签过到了：当日签到获得 {score} 分，连续签到 {streak} 天，"
                f"当前总分 {total}。**本次重复签到没有加分，也没有写库**。"
            )
            hint = "用你自己的话温和地告诉他今天已经签过了，并把连续天数 / 总分顺带说一下。"
        else:
            bonus = int(result.get("bonus") or 0)
            base = int(result.get("base") or 0)
            subtitle = "签到成功"
            stats = [
                ("本次得分", f"+{score} 分", "accent"),
                ("连续奖励", (f"+{bonus} 分" if bonus else "已达上限"), "ok"),
                ("当前总分", f"{total}", "warn"),
            ]
            details = [
                ("本次签到", f"{base} 分" + (f" + 连续附加 {bonus} 分" if bonus else "")),
                ("连续签到", f"{streak} 天"),
            ]
            situation = (
                f"签到成功：随机 {base} 分"
                + (f" + 连续签到附加 {bonus} 分" if bonus else "")
                + f" = {score} 分，连续签到 {streak} 天，当前总分 {total}。"
            )
            hint = (
                "用你自己的话祝贺他签到成功（可以只提总分与连续天数），"
                "不要复述本条说明，也不要承诺任何积分消费 / 兑换。"
            )
        card = CheckinCard(
            title="每日签到",
            subtitle=subtitle,
            stats=stats,
            details=details,
            day=str(result.get("day") or ""),
            streak=streak,
            already=already,
            footer=READONLY_NOTICE,
        )
        if request.command_ctx is None:
            return build_card_text(card)
        theme = request.runtime.pick_card_theme(
            self.id, cache_key=f"{request.user_id}:{result.get('day') or ''}"
        )
        png = await request.runtime.render_card(build_card_html(card, theme=theme))
        if png:
            await request.runtime.send_card(request.command_ctx, png, filename=CARD_FILENAME)
        # §4.7：程序不发固定文案 —— 事实交主管线，由 agent 组织回复
        request.want_sync_reply()
        return request.runtime.interaction_background(
            game=self.name, request=request, situation=situation, hint=hint
        )


__all__ = [
    "CARD_FILENAME",
    "CheckinCard",
    "CheckinGame",
    "READONLY_NOTICE",
    "build_card_html",
    "build_card_text",
    "format_points_text",
]


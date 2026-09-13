"""抽签 / 今日运势玩法（spec(5) §4.8 / R30-R32 / D7 主题 fortune）。

- **每日一次**由**程序**随机并落库（mg_fortune 的 user_id + day 联合主键即幂等）；
- 默认五档（大吉 / 吉 / 中吉 / 小吉 / 平）；fortune_include_bad_luck=true 时七档；
- 产出渲染图 + 文本描述；文本描述**告知 agent**、由 agent 自己回答（程序不发固定文案）；
- 已抽过不重抽：要求再发时读库重渲染**同一结果**并重发图；
- **不附带积分**。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..art import fortune_art
from ..themes import default_theme
from . import Game, GameRequest

HELP_TOKENS = ("帮助", "help", "规则", "?")

#: 卡片文件名
CARD_FILENAME = "fortune.png"


@dataclass(frozen=True)
class FortuneLevel:
    key: str
    label: str
    weight: int
    text: str


#: 默认五档（权重写在插件常量里：只有「是否含凶兆」可配，见 §4.8）
FORTUNE_LEVELS: tuple[FortuneLevel, ...] = (
    FortuneLevel("great", "大吉", 5, "诸事顺遂，适合把搁置已久的事拿起来做。"),
    FortuneLevel("good", "吉", 15, "顺风局，按既定计划推进就好。"),
    FortuneLevel("middle", "中吉", 25, "平稳的一天，小惊喜藏在细节里。"),
    FortuneLevel("small", "小吉", 30, "略有起伏，但整体向好。"),
    FortuneLevel("flat", "平", 25, "无事发生，正好适合休整。"),
)

#: 凶兆档位（fortune_include_bad_luck = true 时才加入）
BAD_LUCK_LEVELS: tuple[FortuneLevel, ...] = (
    FortuneLevel("small_bad", "小凶", 8, "小事容易出岔子，慢一点、多确认一遍。"),
    FortuneLevel("bad", "凶", 3, "今天不宜勉强推进，先照顾好自己。"),
)

#: 全部可抽档位（key -> level）
FORTUNE_TABLE: dict[str, FortuneLevel] = {
    level.key: level for level in FORTUNE_LEVELS + BAD_LUCK_LEVELS
}


def level_table(*, include_bad_luck: bool) -> tuple[FortuneLevel, ...]:
    return FORTUNE_LEVELS + BAD_LUCK_LEVELS if include_bad_luck else FORTUNE_LEVELS


def level_for(key: str) -> FortuneLevel:
    """按落库的 result_key 取档位（未知 key 回落「平」，绝不抛异常）。"""
    return FORTUNE_TABLE.get(str(key or ""), FORTUNE_LEVELS[-1])


def pick_level(rng: Any, *, include_bad_luck: bool) -> FortuneLevel:
    table = level_table(include_bad_luck=include_bad_luck)
    total = sum(level.weight for level in table)
    point = rng.random() * total
    acc = 0.0
    for level in table:
        acc += level.weight
        if point < acc:
            return level
    return table[-1]


#: 档位 -> 卡片色调（stats 的 tone）
LEVEL_TONES: dict[str, str] = {
    "great": "accent",
    "good": "accent",
    "middle": "ok",
    "small": "ok",
    "flat": "muted",
    "small_bad": "warn",
    "bad": "danger",
}


@dataclass
class FortuneCard:
    title: str
    subtitle: str
    rows: list[tuple[str, str]] = field(default_factory=list)
    #: 落库的档位 key（决定竹签配色与色调）
    level_key: str = ""
    #: 竹签上方的程序说明（只放日期等程序文本，绝不放用户输入）
    caption: str = ""
    footer: str = "今日运势每天只抽一次；不附带积分"


def build_card_html(card: FortuneCard, *, theme: str = "") -> str:
    """抽签卡片：真竹签（竹节 / 斜切签头 / 竖向艺术体文字）+ 签筒 + 签架。

    竹签上的字只可能是内置档位常量（art.safe_level_label 会再过滤一次），
    caption 也只用程序产出的日期，因此美术片段里不含任何用户输入。
    """
    from neobot_app.runtime.html_card import inject_slot, render_card_html

    tone = LEVEL_TONES.get(str(card.level_key or "").strip(), "")
    stats: list[list[str]] = []
    items: list[list[str]] = []
    for label, value in card.rows:
        if label == "运势":
            stats.append([label, value, tone])
        else:
            items.append([label, value])
    blocks: list[dict[str, Any]] = [
        {"kind": "slot", "name": "fortune-art"},
    ]
    if stats:
        blocks.append({"kind": "stats", "cols": min(3, len(stats)), "items": stats})
    if items:
        blocks.append({"kind": "kv", "items": items})
    blocks.append({"kind": "note", "text": card.footer, "tone": "muted"})
    html = render_card_html(
        title=card.title,
        subtitle=card.subtitle,
        blocks=blocks,
        footer="",
        theme=theme or default_theme("fortune"),
    )
    return inject_slot(
        html,
        "fortune-art",
        fortune_art(
            label=stats[0][1] if stats else "",
            key=card.level_key,
            caption=card.caption,
        ),
    )


def build_card_text(card: FortuneCard) -> str:
    lines = [card.title]
    if card.subtitle:
        lines.append(card.subtitle)
    for label, value in card.rows:
        lines.append(f"{label}：{value}")
    lines.append(card.footer)
    return "\n".join(lines)


class FortuneGame(Game):
    id = "fortune"
    name = "抽签"
    aliases = ("今日运势", "运势", "fortune", "抽个签")
    summary = "每天抽一次今日运势（默认五档，可配置含凶兆）"
    tool_names = ("fortune",)

    def describe(self) -> str:
        return (
            "抽签（今日运势）：每天**一次**由程序随机并落库，产出运势渲染图 + 文本描述。\n"
            "- 命令入口：/mg 抽签（当天已抽过则重发同一结果，不重抽）\n"
            "- 工具入口：minigame__fortune()\n"
            "默认五档：大吉 / 吉 / 中吉 / 小吉 / 平；配置 fortune_include_bad_luck=true 时"
            "扩展为七档（加 小凶 / 凶）。\n"
            "**程序不发固定文案**：把档位与中性描述告诉用户这件事由你（AI）来组织语言。\n"
            "抽签**不附带积分**；同一天再次请求只会读库重发同一结果。"
        )

    def help_text(self, *, mode: str = "") -> str:
        return (
            "【抽签 · 今日运势】\n"
            "抽签：/mg 抽签（每天一次）\n"
            "规则：\n"
            "- 每天由程序随机抽一次并记录，当天再抽只会重发同一结果（不重抽）；\n"
            "- 默认五档：大吉 / 吉 / 中吉 / 小吉 / 平；管理员可配置加入 小凶 / 凶；\n"
            "- 抽签**不附带积分**，只是图个乐；\n"
            "- 结果文案由 AI 组织，程序只提供档位与中性描述。"
        )

    async def run(self, request: GameRequest) -> str | None:
        args = list(request.args or [])
        head = args[0].strip() if args else ""
        if head in HELP_TOKENS:
            return self.help_text()
        return await self.draw(request)

    async def draw(self, request: GameRequest) -> str | None:
        service = request.service
        config = request.config
        user_id = request.user_id
        existing = await service.get_fortune(user_id)
        if existing is not None:
            level = level_for(str(existing.get("result_key") or ""))
            result_text = str(existing.get("result_text") or level.text)
            reused = True
        else:
            include_bad = bool(getattr(config, "fortune_include_bad_luck", False))
            level = pick_level(request.runtime.rng(), include_bad_luck=include_bad)
            row = await service.draw_fortune(
                user_id, result_key=level.key, result_text=level.text
            )
            level = level_for(str(row.get("result_key") or level.key))
            result_text = str(row.get("result_text") or level.text)
            reused = False

        today = service.today()
        card = FortuneCard(
            title="今日运势",
            subtitle=f"{today} · {request.user_name or request.user_id}",
            rows=[
                ("运势", level.label),
                ("签文", result_text),
                ("日期", today),
            ],
            level_key=level.key,
            caption="今日一签",
            footer="今日运势每天只抽一次；不附带积分",
        )
        if request.command_ctx is None:
            return build_card_text(card)
        # 同一天同一用户重发时沿用同一主题：视觉上确实是「同一张签」
        theme = request.runtime.pick_card_theme(
            self.id, cache_key=f"{user_id}:{today}"
        )
        png = await request.runtime.render_card(build_card_html(card, theme=theme))
        if png:
            await request.runtime.send_card(
                request.command_ctx, png, filename=CARD_FILENAME
            )
        # §4.8：文本描述告知 agent，由 agent 自己回答
        request.want_sync_reply()
        situation = (
            f"用户在 {today} 的今日运势是「{level.label}」，中性描述：{result_text}。"
            + ("（这是当天**已经抽过**的结果，本次只是重发同一张图，没有重抽）" if reused else "（本次为当天首次抽签，已落库）")
            + " 抽签**不产生任何积分变动**。"
        )
        hint = (
            "用你自己的话把这次运势讲给用户听（可自由发挥，不要复述本条说明），"
            "语气轻松，不要承诺任何积分或奖励。"
        )
        return request.runtime.interaction_background(
            game=self.name, request=request, situation=situation, hint=hint
        )


__all__ = [
    "BAD_LUCK_LEVELS",
    "CARD_FILENAME",
    "LEVEL_TONES",
    "FORTUNE_LEVELS",
    "FORTUNE_TABLE",
    "FortuneCard",
    "FortuneGame",
    "FortuneLevel",
    "build_card_html",
    "build_card_text",
    "level_for",
    "level_table",
    "pick_level",
]

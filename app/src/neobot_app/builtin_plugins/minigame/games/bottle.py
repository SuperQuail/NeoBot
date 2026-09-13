"""漂流瓶玩法（spec(5) §4.5 / R17-R24 / D12）。

规则要点（全部有测试守住）：

- 发瓶两种模式：普通（QQ + 昵称 + 头像）/ 匿名（不显示 QQ、昵称位固定「神秘的人」、
  **头像照常显示**），两种模式**共用**每日发送上限；
- 捞瓶排除自己 + 自己最近 3 次捞取过的发送者，因此无瓶可捞时回落普通随机并提示；
- 只做软删除（status=picked + picked_at / picked_by），不回池、不物理删除、无查询入口；
- 永不按时间转档；池满时**随机**挑一条既有 pooled 转 expired 归档；
- 正文去空白后 1-500 字、禁止纯链接、支持 Markdown（先 HTML 转义再渲染）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..art import bottle_avatar, bottle_note, bottle_scene
from ..avatars import (
    AVATAR_CSS,
    AVATAR_MARKER,
    with_style,
)
from ..themes import default_theme
from ..service import (
    BOTTLE_PICK_DAILY_LIMIT,
    BOTTLE_PICK_SCORE,
    BOTTLE_SEND_DAILY_LIMIT,
    BOTTLE_SEND_SCORE,
    DAILY_BOTTLE_PICK,
    DAILY_BOTTLE_SEND,
)
from . import (
    CONTENT_MARKER,
    MARKDOWN_CSS,
    Game,
    GameRequest,
    is_pure_link,
    render_markdown_fragment,
)


def split_head(request: GameRequest) -> tuple[str, str]:
    """把「游戏名之后的原始文本」切成（首个子命令, 其余原文）。

    优先用 raw_args（保留正文里的连续空格），没有时才回落到空格切分的 args。
    """
    raw = str(request.raw_args or "").strip()
    if not raw:
        args = list(request.args or [])
        return (args[0].strip() if args else ""), " ".join(args[1:]).strip()
    parts = raw.split(maxsplit=1)
    return parts[0], (parts[1].strip() if len(parts) > 1 else "")

ANONYMOUS_NAME = "神秘的人"

#: 发瓶的子命令
WRITE_TOKENS = ("丢", "发", "扔", "write", "send")
ANONYMOUS_TOKENS = ("匿名", "anonymous", "anon")
PICK_TOKENS = ("捞", "pick", "捞一个")
HELP_TOKENS = ("帮助", "help", "规则", "?")

#: 卡片文件名
CARD_FILENAME = "bottle.png"


@dataclass
class BottleCard:
    """一张卡片所需的全部数据（HTML 与纯文本共用同一份，信息等价）。"""

    title: str
    subtitle: str
    sender_label: str
    sender_id_label: str
    content: str
    avatar_user_id: str
    avatar_name: str
    anonymous: bool
    visibility: str
    extra_rows: list[tuple[str, str]] = field(default_factory=list)
    footer: str = ""


def visibility_notice(*, anonymous: bool) -> str:
    """按模式写明可见范围与「发出后不可查询、不可撤回」。"""
    if anonymous:
        return (
            "可见范围：只显示头像与「神秘的人」，不显示 QQ 号与昵称；"
            "发出后不可查询、不可撤回。"
        )
    return (
        "可见范围：QQ 号、昵称与头像会随瓶子一起展示；发出后不可查询、不可撤回。"
    )


#: 走「指标卡片」呈现的瓶子信息标签（其余行留在键值表里）
STAT_LABELS: tuple[str, ...] = ("模式", "今日发瓶", "今日捞瓶", "本次积分")

#: 指标色调：模式 = 主题色，额度 = 弱化，积分 = 成功色，提示 = 警示色
STAT_TONES: dict[str, str] = {
    "模式": "accent",
    "今日发瓶": "muted",
    "今日捞瓶": "muted",
    "本次积分": "ok",
    "提示": "warn",
}


def build_card_html(
    card: BottleCard,
    *,
    avatars: Any,
    theme: str = "",
) -> str:
    """渲染漂流瓶卡片（自包含 HTML）。

    美术（海面场景 / 头像舱窗 / 纸条正文）由本插件用 SVG 生成，经 slot 与 marker
    注入；正文先 escape 再 Markdown，因此片段里永远不含用户输入。
    """
    from neobot_app.runtime.html_card import inject_marker, inject_slot, render_card_html

    blocks: list[dict[str, Any]] = [
        {"kind": "slot", "name": "bottle-art"},
        {"kind": "marker", "text": AVATAR_MARKER},
        {"kind": "heading", "text": "瓶中信"},
        {"kind": "marker", "text": CONTENT_MARKER},
    ]
    stats: list[list[str]] = []
    hints: list[str] = []
    items: list[list[str]] = [["发送者", card.sender_label]]
    if card.sender_id_label:
        items.append(["QQ", card.sender_id_label])
    for label, value in card.extra_rows:
        if label in STAT_LABELS:
            stats.append([label, value, STAT_TONES.get(label, "")])
        elif label == "提示":
            hints.append(str(value))
        else:
            items.append([label, value])
    items.append(["可见范围", card.visibility])
    if stats:
        blocks.append({"kind": "stats", "cols": min(3, len(stats)), "items": stats})
    blocks.append({"kind": "kv", "title": "瓶子信息", "items": items})
    for hint in hints:
        blocks.append({"kind": "note", "text": hint, "tone": "warn"})

    html = render_card_html(
        title=card.title,
        subtitle=card.subtitle,
        blocks=blocks,
        footer=card.footer,
        theme=theme or default_theme("bottle"),
    )
    html = with_style(html, AVATAR_CSS + MARKDOWN_CSS)
    html = inject_slot(html, "bottle-art", bottle_scene(anonymous=card.anonymous))
    avatar_html = avatars.html(
        card.avatar_user_id, card.avatar_name, anonymous=card.anonymous
    )
    html = inject_marker(
        html,
        AVATAR_MARKER,
        bottle_avatar(avatar_html, anonymous=card.anonymous, label=card.sender_label),
    )
    html = inject_marker(
        html, CONTENT_MARKER, bottle_note(render_markdown_fragment(card.content))
    )
    return html


def build_card_text(card: BottleCard) -> str:
    """与图片版**信息等价**的纯文本卡片（渲染不可用时的降级）。"""
    lines = [card.title]
    if card.subtitle:
        lines.append(card.subtitle)
    lines.append(f"发送者：{card.sender_label}")
    if card.sender_id_label:
        lines.append(f"QQ：{card.sender_id_label}")
    for label, value in card.extra_rows:
        lines.append(f"{label}：{value}")
    lines.append(f"可见范围：{card.visibility}")
    lines.append("")
    lines.append(card.content)
    if card.footer:
        lines.append("")
        lines.append(card.footer)
    return "\n".join(lines)


class BottleGame(Game):
    id = "bottle"
    name = "漂流瓶"
    aliases = ("瓶", "bottle", "漂流瓶")
    summary = "丢一个瓶子 / 捞一个瓶子（支持匿名，发出后不可查询）"
    tool_names = ("bottle_write", "bottle_pick")

    # ── R15：agent 说明与帮助 ───────────────────────────────────

    def describe(self) -> str:
        return (
            "漂流瓶：把想说的话装进瓶子丢进**全局**瓶池，别人可以随机捞到。\n"
            "- 命令入口：/mg 瓶 丢 <正文>、/mg 瓶 匿名 <正文>、/mg 瓶 捞、/mg 瓶 帮助\n"
            "- 工具入口：minigame__bottle_write(content, anonymous)、minigame__bottle_pick()\n"
            "两种发送模式共用每日发送上限（各 5 次 / 日，发瓶与捞瓶分别计），捞取无冷却。\n"
            "普通模式展示 QQ 号 + 昵称 + 头像；匿名模式不显示 QQ 与昵称（昵称位固定「神秘的人」），"
            "但**头像照常显示**。\n"
            "瓶子发出后不可查询、不可撤回；正文去空白后 1-500 字，禁止纯链接，支持 Markdown。"
        )

    def help_text(self, *, mode: str = "") -> str:
        return (
            "【漂流瓶】\n"
            "发瓶：/mg 瓶 丢 <正文>（普通）/ /mg 瓶 匿名 <正文>（匿名）\n"
            "捞瓶：/mg 瓶 捞（随机抽一个别人丢的瓶子）\n"
            "规则：\n"
            f"- 每日上限：发瓶 {BOTTLE_SEND_DAILY_LIMIT} 次 + 捞瓶 {BOTTLE_PICK_DAILY_LIMIT} 次，"
            "两者**分别计**；捞取没有冷却。\n"
            "- 捞瓶会排除自己，也会排除你最近 3 次捞到过的发送者；若因此无瓶可捞会回落普通随机并提示。\n"
            f"- 普通模式（{visibility_notice(anonymous=False)}）\n"
            f"- 匿名模式（{visibility_notice(anonymous=True)}）\n"
            "- 正文去空白后 1-500 字，禁止纯链接，支持 Markdown（粗体 / 列表 / 代码块）。\n"
            "- 不做敏感词过滤；瓶池是全局的（跨会话、跨群）。\n"
            "- 池满时会随机把一条待捞瓶转档归档（不按时间、不删除）。"
        )

    # ── 命令入口 ────────────────────────────────────────────────

    async def run(self, request: GameRequest) -> str | None:
        head, rest = split_head(request)

        if head in HELP_TOKENS:
            return self.help_text()
        if head in PICK_TOKENS:
            return await self.pick(request)
        if head in WRITE_TOKENS:
            return await self.write(request, anonymous=False, content=rest)
        if head in ANONYMOUS_TOKENS:
            return await self.write(request, anonymous=True, content=rest)
        if not head:
            return self.need_agent(
                request,
                situation="用户点名了漂流瓶，但没有说明要「丢」还是「捞」，也没有给出正文。",
                hint=(
                    "先自然地问清意图：是想丢一个瓶子（可选匿名），还是想捞一个瓶子？"
                    "需要的话调用 minigame__help(game=\"bottle\") 查规则。"
                ),
            )
        return self.need_agent(
            request,
            situation=f"用户输入的漂流瓶子命令无法识别（原话：{head}）。",
            hint=(
                "用你自己的话告诉用户「丢 / 匿名 / 捞 / 帮助」的用法，"
                "并顺势邀请他继续玩漂流瓶。"
            ),
        )

    # ── 发瓶 ────────────────────────────────────────────────────

    async def write(
        self, request: GameRequest, *, anonymous: bool, content: str
    ) -> str | None:
        service = request.service
        config = request.config
        topic = "匿名" if anonymous else "普通"
        limit = int(getattr(config, "bottle_content_max_chars", 500) or 500)
        text = str(content or "").strip()

        if not text:
            return self.need_agent(
                request,
                situation=f"用户选择{topic}发瓶但没有给出正文，**未写入瓶池**。",
                hint=(
                    "引导用户把想说的话补上（去空白后 1-"
                    f"{limit} 字，支持 Markdown），然后用 "
                    "minigame__bottle_write(content=..., anonymous="
                    f"{'true' if anonymous else 'false'}) 帮他发瓶。"
                ),
            )
        if len(text) > limit:
            return self.need_agent(
                request,
                situation=(
                    f"正文 {len(text)} 字超过上限 {limit} 字，**未写入瓶池**。"
                ),
                hint="用你自己的话请用户压缩到上限以内（可以说说超了多少字）。",
            )
        if is_pure_link(text):
            return self.need_agent(
                request,
                situation="正文是纯链接（分隔后每一段都是 URL），**未写入瓶池**。",
                hint="用你自己的话说明「纯链接的瓶子不能丢」，请用户补充一句人话或改写正文。",
            )

        plays = await service.daily_plays(request.user_id, DAILY_BOTTLE_SEND)
        if plays >= BOTTLE_SEND_DAILY_LIMIT:
            return self.need_agent(
                request,
                situation=(
                    f"用户今天已经发过 {plays} 个瓶子，达到每日上限 "
                    f"{BOTTLE_SEND_DAILY_LIMIT}，**本次未写入瓶池**。"
                ),
                hint="用你自己的话告诉他今天的发瓶额度用完了（明天再来说），可以先去捞几个瓶子。",
            )

        avatars = getattr(request.runtime, "avatars", None)
        if avatars is not None:
            await avatars.refresh(request.user_id)
            avatar_path = avatars.path(request.user_id)
        else:  # pragma: no cover - 运行期一定有
            avatar_path = ""
        sender_id = str(request.user_id)
        await service.add_bottle(
            sender_id=sender_id,
            sender_name=request.user_name or sender_id,
            sender_avatar=avatar_path,
            content=text,
            anonymous=anonymous,
            meta={"mode": "anonymous" if anonymous else "normal", "conversation": request.conversation_id},
        )
        await service.bump_daily(request.user_id, DAILY_BOTTLE_SEND)
        profile = await service.add_score(
            request.user_id, BOTTLE_SEND_SCORE, play=True
        )
        await service.add_record(
            user_id=request.user_id,
            game_id=DAILY_BOTTLE_SEND,
            score=BOTTLE_SEND_SCORE,
            conversation_id=request.conversation_id,
        )
        card = BottleCard(
            title="漂流瓶已投出",
            subtitle="它已经漂到全局瓶池，等有缘人捞起",
            sender_label=ANONYMOUS_NAME if anonymous else (request.user_name or sender_id),
            sender_id_label="" if anonymous else sender_id,
            content=text,
            avatar_user_id=sender_id,
            avatar_name=request.user_name or sender_id,
            anonymous=anonymous,
            visibility=visibility_notice(anonymous=anonymous),
            extra_rows=[
                ("模式", topic),
                ("今日发瓶", f"{plays + 1}/{BOTTLE_SEND_DAILY_LIMIT}"),
                ("本次积分", f"+{BOTTLE_SEND_SCORE}（当前 {int(profile['score'])}）"),
            ],
            footer="瓶子发出后不可查询、不可撤回",
        )
        if request.command_ctx is None:
            return build_card_text(card)
        return await self.deliver_card(request, card)

    # ── 捞瓶 ────────────────────────────────────────────────────

    async def pick(self, request: GameRequest) -> str | None:
        service = request.service
        plays = await service.daily_plays(request.user_id, DAILY_BOTTLE_PICK)
        if plays >= BOTTLE_PICK_DAILY_LIMIT:
            return self.need_agent(
                request,
                situation=(
                    f"用户今天已经捞过 {plays} 次瓶子，达到每日上限 "
                    f"{BOTTLE_PICK_DAILY_LIMIT}，**本次没有捞取也没有写库**。"
                ),
                hint="用你自己的话告诉他今天的捞瓶额度用完了（明天再来），可以先去丢一个瓶子。",
            )

        excluded = await service.recent_picked_senders(request.user_id)
        outcome = await service.pick_bottle(
            user_id=request.user_id, exclude_senders=excluded
        )
        bottle = outcome.get("bottle")
        if bottle is None:
            return self.need_agent(
                request,
                situation="瓶池里现在没有任何可以捞的瓶子（或剩下的瓶子都被排除规则挡掉了），**未写库**。",
                hint="用你自己的话说明现在是空池，并邀请他先丢一个瓶子（可以匿名）。",
            )

        await service.bump_daily(request.user_id, DAILY_BOTTLE_PICK)
        profile = await service.add_score(
            request.user_id, BOTTLE_PICK_SCORE, play=True
        )
        await service.add_record(
            user_id=request.user_id,
            game_id=DAILY_BOTTLE_PICK,
            score=BOTTLE_PICK_SCORE,
            conversation_id=request.conversation_id,
        )
        anonymous = bool(bottle.get("anonymous"))
        sender_id = str(bottle.get("sender_id") or "")
        sender_name = str(bottle.get("sender_name") or sender_id)
        extra = [
            ("模式", "匿名" if anonymous else "普通"),
            ("今日捞瓶", f"{plays + 1}/{BOTTLE_PICK_DAILY_LIMIT}"),
            ("本次积分", f"+{BOTTLE_PICK_SCORE}（当前 {int(profile['score'])}）"),
        ]
        if outcome.get("used_fallback"):
            extra.append(
                (
                    "提示",
                    f"最近 {len(excluded)} 位发送者的瓶子都被排除，已回落普通随机",
                )
            )
        card = BottleCard(
            title="捞到一个漂流瓶",
            subtitle="来自全局瓶池的随机一个瓶子",
            sender_label=ANONYMOUS_NAME if anonymous else sender_name,
            sender_id_label="" if anonymous else sender_id,
            content=str(bottle.get("content") or ""),
            avatar_user_id=sender_id,
            avatar_name=sender_name,
            anonymous=anonymous,
            visibility=visibility_notice(anonymous=anonymous),
            extra_rows=extra,
            footer="瓶子已归档（软删除），不会再被任何人捞到；不可查询、不可撤回",
        )
        if request.command_ctx is None:
            return build_card_text(card)
        return await self.deliver_card(request, card)

    # ── 交付 ────────────────────────────────────────────────────

    async def deliver_card(self, request: GameRequest, card: BottleCard) -> str | None:
        """命令通道：渲染并发图；渲染不可用时回等价纯文本。"""
        avatars = getattr(request.runtime, "avatars", None)
        theme = request.runtime.pick_card_theme(self.id)
        html = build_card_html(card, avatars=avatars, theme=theme)
        png = await request.runtime.render_card(html)
        if png:
            sent = await request.runtime.send_card(
                request.command_ctx, png, filename=CARD_FILENAME
            )
            if sent:
                return None
        return build_card_text(card)

    def need_agent(self, request: GameRequest, *, situation: str, hint: str) -> str:
        """把「事实 + 提示词」交主管线；工具通道则只回事实给模型。"""
        if request.command_ctx is None:
            return f"{situation}\n{hint}"
        request.want_sync_reply()
        return request.runtime.interaction_background(
            game=self.name, request=request, situation=situation, hint=hint
        )


__all__ = [
    "ANONYMOUS_NAME",
    "STAT_LABELS",
    "STAT_TONES",
    "BottleCard",
    "BottleGame",
    "build_card_html",
    "build_card_text",
    "visibility_notice",
]

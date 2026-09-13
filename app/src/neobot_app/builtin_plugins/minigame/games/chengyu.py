"""成语接龙玩法（spec(5) §4.6 / R25-R26 / D14）。

程序只做三件事：**随机目标 N（3-10）**、**步数与时限护栏**、**计分与流水**；
「这算不算成语 / 接不接得上 / 是否重复」一律交 AI 判定 —— 这是 R12「不把玩法
判定写进程序」的核心落地。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..art import chengyu_progress, chengyu_scroll
from ..themes import default_theme
from . import Game, GameRequest
from .bottle import split_head

#: 每条提交的积分
CHENGYU_STEP_SCORE = 1

#: 卡片文件名
CARD_FILENAME = "chengyu.png"

#: 卷轴上的程序状态文字（只可能是这几个常量之一，不含用户输入）
STATUS_START = "开局"
STATUS_PLAYING = "接龙中"
STATUS_PENDING = "待判定"
STATUS_DONE = "本局结束"

#: 卡片页脚（同样是程序常量，不含用户输入）
FOOTER_PLAYING = "是否算成语、接不接得上、是否重复由 AI 判定；达成目标额外加分"
FOOTER_PENDING = "这一步是否算数由 AI 判定，判定通过才会记入本局"
FOOTER_CLOSED = "本局已结束；超时或未达成不扣分"

#: 达成目标 N 的额外奖励 = N
CHENGYU_WIN_BONUS_RATIO = 1

#: describe() 里引用的默认护栏（实际取值以插件配置为准）
DEFAULT_MAX_STEPS = 10
DEFAULT_STEP_TIMEOUT_SECONDS = 60

HELP_TOKENS = ("帮助", "help", "规则", "?")
STOP_TOKENS = ("stop", "结束", "停止", "退出")

#: 用于 mg_record.game_id 的玩法 id（服务层只用它做聚合）
GAME_ID = "chengyu"


@dataclass
class ChengyuSession:
    """一个会话内的进行中局面（进程内状态；护栏由程序给）。"""

    conversation_id: str
    target: int
    max_steps: int
    step_timeout_seconds: float
    started_by: int
    started_at: float
    last_submit_at: float
    words: list[str] = field(default_factory=list)
    participants: set[str] = field(default_factory=set)
    finished: bool = False

    @property
    def steps(self) -> int:
        return len(self.words)

    def expired(self, now: float) -> bool:
        return (now - self.last_submit_at) > float(self.step_timeout_seconds)

    @property
    def progress(self) -> str:
        return f"第 {self.steps}/{self.target} 条"



#: 档位 -> 卡片色调（stats 的 tone）
TONE_OK = "ok"
TONE_MUTED = "muted"


@dataclass
class ChengyuCard:
    """成语接龙卡片所需的全部数据（HTML 与纯文本共用同一份）。"""

    title: str
    subtitle: str
    target: int
    steps: int
    max_steps: int
    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS
    status: str = STATUS_PLAYING
    words: list[str] = field(default_factory=list)
    word_pending: str = ""
    footer: str = ""


def build_card_html(card: ChengyuCard, *, theme: str = "") -> str:
    """渲染成语接龙卡片：卷轴 + 毛笔 + 印章 + 进度节点链。

    words（用户提交的词）只进 rows 单元格，由渲染器 escape；美术片段里没有用户输入。
    """
    from neobot_app.runtime.html_card import inject_slot, render_card_html

    target = max(1, int(card.target or 1))
    steps = max(0, int(card.steps or 0))
    max_steps = max(1, int(card.max_steps or 1))
    blocks: list[dict[str, Any]] = [
        {"kind": "slot", "name": "chengyu-art"},
        {"kind": "slot", "name": "chengyu-progress"},
        {
            "kind": "stats",
            "cols": 3,
            "items": [
                ["目标条数", f"{target} 条", "accent"],
                ["已接", f"{steps} 条", TONE_OK],
                ["剩余步数", f"{max(max_steps - steps, 0)} 步", TONE_MUTED],
            ],
        },
    ]
    if card.words:
        recent = list(card.words)[-6:]
        offset = len(card.words) - len(recent)
        blocks.append(
            {
                "kind": "rows",
                "title": "本局词录",
                "columns": ["#", "词"],
                "widths": ["48px", "auto"],
                "rows": [
                    [str(offset + index + 1), word] for index, word in enumerate(recent)
                ],
            }
        )
    detail: list[list[str]] = [
        ["每条时限", f"{int(card.step_timeout_seconds)} 秒"],
        ["单局步数", f"最多 {max_steps} 步"],
        ["达成奖励", f"额外 +{target} 分"],
    ]
    if card.word_pending:
        detail.append(["待判定", card.word_pending])
    blocks.append({"kind": "kv", "title": "本局规则", "items": detail})
    html = render_card_html(
        title=card.title,
        subtitle=card.subtitle,
        blocks=blocks,
        footer=card.footer,
        theme=theme or default_theme("chengyu"),
    )
    html = inject_slot(html, "chengyu-art", chengyu_scroll(status=card.status))
    html = inject_slot(
        html,
        "chengyu-progress",
        chengyu_progress(steps=steps, target=target, max_steps=max_steps),
    )
    return html


def build_card_text(card: ChengyuCard) -> str:
    """与图片版信息等价的纯文本卡片（渲染不可用时的降级）。"""
    lines = [card.title]
    if card.subtitle:
        lines.append(card.subtitle)
    lines.append(f"进度：第 {int(card.steps)}/{int(card.target)} 条（{card.status}）")
    lines.append(
        f"单局最多 {int(card.max_steps)} 步、每条 {int(card.step_timeout_seconds)} 秒；"
        f"达成目标额外 +{int(card.target)} 分"
    )
    if card.word_pending:
        lines.append(f"待判定：{card.word_pending}")
    if card.words:
        lines.append("本局词录：" + " → ".join(str(word) for word in card.words[-6:]))
    if card.footer:
        lines.append(card.footer)
    return "\n".join(lines)


class ChengyuGame(Game):
    id = "chengyu"
    name = "成语接龙"
    aliases = ("接龙", "chengyu", "成语")
    summary = "程序给目标条数与时限，规则判定交 AI 的多人接龙"
    tool_names = ("chengyu_submit",)

    # ── R15：agent 说明与帮助 ───────────────────────────────────

    def describe(self) -> str:
        return (
            "成语接龙：程序随机给一个目标条数 N（默认 3-10）作为胜利条件，"
            "**是否算成语、是否接得上、是否重复全部由你（AI）判定**。\n"
            "- 命令入口：/mg 成语接龙 开始（或 /mg 接龙）、/mg 成语接龙 <词>、"
            "/mg 成语接龙 帮助、/mg stop\n"
            "- 工具入口：minigame__chengyu_submit(word) —— **不校验内容**，"
            "只把该词记入本局流水、计一步、加 1 分，并返回进度（第 k/N 条）\n"
            f"护栏由程序提供：每条 {60} 秒内必须有人提交，单局最多 10 步（用满即结束）。\n"
            "同一会话一局，群内多人可参与，谁先提交谁得分；达成 N 额外 +N；"
            "超时或未达成**不扣分**。"
        )

    def help_text(self, *, mode: str = "") -> str:
        return (
            "【成语接龙】\n"
            "开始：/mg 成语接龙（或 /mg 接龙）—— 程序随机给出目标条数 N\n"
            "提交：直接把你想到的成语发出来，由 AI 判断是否接得上，"
            "再由 AI 调用 minigame__chengyu_submit(word) 记分\n"
            "结束：/mg stop（发起者或次级管理员）\n"
            "规则：\n"
            "- 程序只提供护栏：每条 60 秒、单局最多 10 步；用满步数或超时即结束本局。\n"
            "- 是否算成语、是否接得上、是否重复**全部由 AI 判断**，程序不做词库校验。\n"
            "- 每条 +1 分；达成目标 N 额外 +N；超时 / 未达成不扣分。\n"
            "- 同一会话一局，群内多人可参与，谁先提交谁得分。"
        )

    # ── 会话管理 ────────────────────────────────────────────────

    def sessions(self, request: GameRequest) -> dict[str, ChengyuSession]:
        return request.runtime.chengyu_sessions

    def active_session(self, request: GameRequest, conversation_id: str) -> ChengyuSession | None:
        session = self.sessions(request).get(str(conversation_id))
        if session is None:
            return None
        if session.finished:
            return None
        if session.expired(request.runtime.monotonic()):
            self.close_session(request, session, reason="timeout")
            return None
        return session

    def close_session(
        self, request: GameRequest, session: ChengyuSession, *, reason: str
    ) -> ChengyuSession:
        session.finished = True
        self.sessions(request).pop(session.conversation_id, None)
        request.runtime.note_session_closed(session, reason=reason)
        return session

    # ── 卡片 ────────────────────────────────────────────────────

    def session_card(
        self,
        session: ChengyuSession,
        *,
        status: str,
        word_pending: str = "",
        footer: str = "",
    ) -> ChengyuCard:
        """把一局会话整理成卡片数据（进度第 k/N 条即来自这里）。"""
        return ChengyuCard(
            title=self.name,
            subtitle=f"{session.progress} · {status}",
            target=int(session.target),
            steps=int(session.steps),
            max_steps=int(session.max_steps),
            step_timeout_seconds=float(session.step_timeout_seconds),
            status=status,
            words=list(session.words),
            word_pending=str(word_pending or ""),
            footer=footer,
        )

    async def deliver_card(self, request: GameRequest, card: ChengyuCard) -> str | None:
        """命令通道：渲染并发图；渲染不可用时回等价纯文本。"""
        if request.command_ctx is None:
            return build_card_text(card)
        theme = request.runtime.pick_card_theme(self.id)
        png = await request.runtime.render_card(build_card_html(card, theme=theme))
        if png and await request.runtime.send_card(
            request.command_ctx, png, filename=CARD_FILENAME
        ):
            return None
        return build_card_text(card)

    # ── 命令入口 ────────────────────────────────────────────────

    async def run(self, request: GameRequest) -> str | None:
        head, _rest = split_head(request)

        if head in HELP_TOKENS:
            return self.help_text()
        if head in STOP_TOKENS:
            return await self.stop(request)
        conversation_id = str(request.conversation_id)
        session = self.active_session(request, conversation_id)
        if head:
            # 用户直接报了一个词：判定交给 AI，程序只提示它去调用工具
            if session is None:
                session = self.start_session(request)
            await self.deliver_card(
                request,
                self.session_card(
                    session,
                    status=STATUS_PENDING,
                    word_pending=head,
                    footer=FOOTER_PENDING,
                ),
            )
            return self.need_agent(
                request,
                situation=(
                    f"用户在成语接龙第 {session.steps}/{session.target} 条处提交了「{head}」，"
                    "本局最多 " + str(session.max_steps) + " 步、每条 "
                    + str(int(session.step_timeout_seconds)) + " 秒。"
                ),
                hint=(
                    "请你判断这个词是否算成语、是否接得上上一条（没有上一条时以它开头即可）、"
                    "是否在本局重复过；判定通过就调用 "
                    "minigame__chengyu_submit(word=\"" + head + "\") 记分，"
                    "不通过就用你自己的话引导用户换一个。"
                ),
            )
        if session is None:
            session = self.start_session(request)
            await self.deliver_card(
                request,
                self.session_card(session, status=STATUS_START, footer=FOOTER_PLAYING),
            )
            return self.need_agent(
                request,
                situation=(
                    f"用户开始了新的一局成语接龙：目标 {session.target} 条，"
                    f"单局最多 {session.max_steps} 步，每条 {int(session.step_timeout_seconds)} 秒。"
                ),
                hint=(
                    "由你（AI）开场：说明这局要接 "
                    + str(session.target)
                    + " 条、限时与步数，并给出第一个成语或邀请用户先说一个；"
                    "用户每报一个词，你判定后调用 minigame__chengyu_submit(word=...) 记分。"
                ),
            )
        await self.deliver_card(
            request,
            self.session_card(session, status=STATUS_PLAYING, footer=FOOTER_PLAYING),
        )
        return self.need_agent(
            request,
            situation=(
                f"成语接龙已经进行中（{session.progress}，已用 {session.steps}/{session.max_steps} 步）。"
            ),
            hint="用你自己的话告诉用户当前进度，并邀请他继续接下去。",
        )

    def start_session(self, request: GameRequest) -> ChengyuSession:
        config = request.config
        low = int(getattr(config, "chengyu_target_min", 3))
        high = int(getattr(config, "chengyu_target_max", 10))
        if high < low:
            low, high = high, low
        target = int(request.runtime.rng().randint(low, high))
        now = request.runtime.monotonic()
        session = ChengyuSession(
            conversation_id=str(request.conversation_id),
            target=target,
            max_steps=int(getattr(config, "chengyu_max_steps", 10)),
            step_timeout_seconds=float(getattr(config, "chengyu_step_timeout_seconds", 60)),
            started_by=int(request.user_id or 0),
            started_at=now,
            last_submit_at=now,
        )
        self.sessions(request)[session.conversation_id] = session
        return session

    async def stop(self, request: GameRequest) -> str | None:
        """结束当前会话局：仅发起者或次级管理员。"""
        conversation_id = str(request.conversation_id)
        session = self.active_session(request, conversation_id)
        if session is None:
            return "当前会话没有进行中的成语接龙。"
        if not self.can_stop(request, session):
            return "只有本局发起者或次级管理员可以结束这一局。"
        self.close_session(request, session, reason="stopped")
        await self.deliver_card(
            request,
            self.session_card(session, status=STATUS_DONE, footer=FOOTER_CLOSED),
        )
        return (
            f"本局成语接龙已结束（{session.steps}/{session.target} 条，"
            f"已用 {session.steps}/{session.max_steps} 步）。"
        )

    def can_stop(self, request: GameRequest, session: ChengyuSession) -> bool:
        if int(request.user_id or 0) == int(session.started_by or 0):
            return True
        ctx = request.command_ctx
        service = getattr(ctx, "service", None) if ctx is not None else None
        permissions = getattr(service, "permissions", None)
        checker = getattr(permissions, "can", None)
        if not callable(checker):
            # 工具通道 / 无权限服务：允许（由调用方即 agent 决定，不额外设门槛）
            return ctx is None
        try:
            from neobot_app.commands.model import PERM_SUB_ADMIN

            return bool(checker(int(request.user_id or 0), PERM_SUB_ADMIN))
        except Exception:
            return False

    # ── 提交（工具通道）────────────────────────────────────────

    async def submit(self, request: GameRequest, word: str) -> str | None:
        """记一步：**不校验内容**，只记流水 / 计步 / 加分 / 返回进度。"""
        conversation_id = str(request.conversation_id)
        session = self.active_session(request, conversation_id)
        if session is None:
            return (
                "当前没有进行中的成语接龙，先让用户发 /mg 成语接龙（或对我说「成语接龙」）开一局。"
            )
        word = str(word if word is not None else "")
        runtime = request.runtime
        service = request.service
        session.words.append(word)
        session.participants.add(str(request.user_id))
        session.last_submit_at = runtime.monotonic()

        profile = await service.add_score(request.user_id, CHENGYU_STEP_SCORE, play=True)
        await service.add_record(
            user_id=request.user_id,
            game_id=GAME_ID,
            score=CHENGYU_STEP_SCORE,
            conversation_id=conversation_id,
        )
        progress = session.progress
        reached = session.steps >= session.target
        exhausted = session.steps >= session.max_steps

        if reached or exhausted:
            bonus = 0
            win = reached
            if reached:
                bonus = int(session.target) * CHENGYU_WIN_BONUS_RATIO
                profile = await service.add_score(request.user_id, bonus, win=True)
                await service.add_record(
                    user_id=request.user_id,
                    game_id=GAME_ID,
                    score=bonus,
                    conversation_id=conversation_id,
                )
            self.close_session(
                request, session, reason="reached" if reached else "steps_exhausted"
            )
            if win:
                return (
                    f"已记录「{word}」，进度 {progress}，达成目标！额外 +{bonus} 分，"
                    f"本局结束，你当前总分 {int(profile['score'])}。"
                )
            return (
                f"已记录「{word}」，进度 {progress}，单局 {session.max_steps} 步已经用满，"
                f"本局结束（未达成目标，不扣分）。"
            )
        return (
            f"已记录「{word}」，进度 {progress}（本局最多 {session.max_steps} 步、"
            f"每条 {int(session.step_timeout_seconds)} 秒），当前总分 {int(profile['score'])}。"
        )

    def need_agent(self, request: GameRequest, *, situation: str, hint: str) -> str:
        if request.command_ctx is None:
            return f"{situation}\n{hint}"
        request.want_sync_reply()
        return request.runtime.interaction_background(
            game=self.name, request=request, situation=situation, hint=hint
        )


__all__ = [
    "CARD_FILENAME",
    "CHENGYU_STEP_SCORE",
    "CHENGYU_WIN_BONUS_RATIO",
    "FOOTER_CLOSED",
    "FOOTER_PENDING",
    "FOOTER_PLAYING",
    "STATUS_DONE",
    "STATUS_PENDING",
    "STATUS_PLAYING",
    "STATUS_START",
    "ChengyuCard",
    "ChengyuGame",
    "ChengyuSession",
    "GAME_ID",
    "HELP_TOKENS",
    "STOP_TOKENS",
    "build_card_html",
    "build_card_text",
]

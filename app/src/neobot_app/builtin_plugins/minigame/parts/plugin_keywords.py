"""关键词与意图入口：匹配、引导词、预激活声明。"""

from __future__ import annotations

from typing import Any
from ..games import find_game

from .constants import KEYWORDS, PACKAGE_BASE, _MG_COMMAND_RE
from .registration import preactivate_for, skill_name_for
from .utils import _event_text, _sender_name


class _PluginKeywordsMixin:
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
